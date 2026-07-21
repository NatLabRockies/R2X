"""Utility functions for getter operations, particularly multiband conversions."""

from __future__ import annotations

import contextlib
import json
import math
import pathlib
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from infrasys.cost_curves import CostCurve, FuelCurve
from infrasys.function_data import LinearFunctionData, PiecewiseLinearData, QuadraticFunctionData, XYCoords
from infrasys.value_curves import AverageRateCurve, IncrementalCurve, InputOutputCurve
from loguru import logger
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSPropertyValue,
    PLEXOSRegion,
    PLEXOSReserve,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_sienna.models import (
    ACBus,
    Area,
    DCBus,
    EnergyReservoirStorage,
    HydroPumpTurbine,
    HydroReservoir,
    HydroTurbine,
    LoadZone,
    PhaseShiftingTransformer,
    TapTransformer,
    Transformer2W,
    TransmissionInterface,
    VariableReserve,
)
from r2x_sienna.models.enums import ACBusTypes
from r2x_sienna.units import get_magnitude

if TYPE_CHECKING:
    from r2x_core import PluginContext

InputOutputCurveValue = InputOutputCurve[LinearFunctionData | QuadraticFunctionData | PiecewiseLinearData]

_SIENNA_TRANSFORMER_TYPES = (Transformer2W, TapTransformer, PhaseShiftingTransformer)
_ISO_RTO_POLYGONS: dict[str, list] | None = None
_ISO_RTO_CONFIG_DIR = pathlib.Path(__file__).parent / "config" / "iso-rto-coordinates"


def _chunked_setup_target_and_child_tables(
    tgt_metadata: Any,
    src_associations: Any,
    uuid_map: dict,
) -> tuple[list[tuple], dict[str, str]]:
    """Chunked drop-in for r2x_core's _setup_target_and_child_tables."""
    from uuid import UUID as _UUID

    uuid_to_type = {str(uuid): type(comp).__name__ for uuid, comp in uuid_map.items()}

    tgt_metadata.execute("DROP TABLE IF EXISTS target_components")
    tgt_metadata.execute("CREATE TEMP TABLE target_components (uuid TEXT PRIMARY KEY, type TEXT)")
    tgt_metadata.executemany("INSERT INTO target_components VALUES (?, ?)", list(uuid_to_type.items()))

    target_uuids = list(uuid_to_type.keys())

    if not target_uuids:
        tgt_metadata.execute("DROP TABLE IF EXISTS child_mapping")
        tgt_metadata.execute(
            "CREATE TEMP TABLE child_mapping (child_uuid TEXT, parent_uuid TEXT, parent_type TEXT)"
        )
        return [], uuid_to_type

    _chunk_size = 900
    child_parent_rows: list[tuple] = []
    for i in range(0, len(target_uuids), _chunk_size):
        chunk = target_uuids[i : i + _chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        child_parent_rows.extend(
            src_associations.execute(
                f"""
                SELECT component_uuid, attached_component_uuid
                FROM component_associations
                WHERE attached_component_uuid IN ({placeholders})
                """,
                chunk,
            ).fetchall()
        )

    child_remapping = [
        (child_uuid, parent_uuid, type(uuid_map[_UUID(parent_uuid)]).__name__)
        for child_uuid, parent_uuid in child_parent_rows
        if parent_uuid in uuid_to_type
    ]

    tgt_metadata.execute("DROP TABLE IF EXISTS child_mapping")
    tgt_metadata.execute(
        "CREATE TEMP TABLE child_mapping (child_uuid TEXT, parent_uuid TEXT, parent_type TEXT)"
    )
    if child_remapping:
        tgt_metadata.executemany("INSERT INTO child_mapping VALUES (?, ?, ?)", child_remapping)

    return child_remapping, uuid_to_type


def _write_descriptions_to_db(system: Any, db: Any) -> None:
    """Write ext["description"] from each translated component to t_object.description."""
    from r2x_plexos.exporter import PLEXOS_TYPE_MAP_INVERTED

    updates: list[tuple[str, str, int]] = []
    for comp_type in system.get_component_types():
        for comp in system.get_components(comp_type):
            desc = (getattr(comp, "ext", None) or {}).get("description")
            if not desc:
                continue
            comp_name: str = getattr(comp, "name", "") or ""
            if not comp_name:
                continue
            class_enum = PLEXOS_TYPE_MAP_INVERTED.get(type(comp))
            if class_enum is None:
                continue
            updates.append((str(desc), comp_name, db.get_class_id(class_enum)))

    if updates:
        db._db.executemany(
            "UPDATE t_object SET description=? WHERE name=? AND class_id=?",
            updates,
        )
        logger.debug("Wrote description to {} t_object rows", len(updates))


def apply_chunking_patch() -> None:
    """Apply SQLite IN-clause chunking fix to r2x_core.time_series (idempotent).

    r2x_core's _setup_target_and_child_tables issues a single IN-clause query
    with all target UUIDs, which exceeds SQLite's 999-parameter limit on large
    systems. This replaces it with a chunked equivalent.
    """
    import r2x_core.time_series as _ts

    if cast(Any, _ts)._setup_target_and_child_tables is _chunked_setup_target_and_child_tables:
        return
    cast(Any, _ts)._setup_target_and_child_tables = _chunked_setup_target_and_child_tables
    logger.debug("Applied chunked _setup_target_and_child_tables to r2x_core.time_series")


def apply_description_export_patch() -> None:
    """Wrap PLEXOSExporter.prepare_export to also persist descriptions (idempotent).

    The exporter's bulk object insert omits the description column. This wraps
    prepare_export so that after objects are inserted, ext["description"] values
    are written back to t_object.description via a batch UPDATE.
    """
    import r2x_plexos.exporter as _exp

    if getattr(cast(Any, _exp.PLEXOSExporter).prepare_export, "_description_patched", False):
        return

    _original = _exp.PLEXOSExporter.prepare_export

    def _wrapped(self: Any) -> Any:
        result = _original(self)
        system = getattr(self, "system", None)
        db = getattr(self, "db", None)
        if system is not None and db is not None:
            try:
                _write_descriptions_to_db(system, db)
            except Exception as _err:
                logger.warning("Could not write descriptions to t_object: {}", _err)
        return result

    cast(Any, _wrapped)._description_patched = True
    cast(Any, _exp.PLEXOSExporter).prepare_export = _wrapped
    logger.debug("Applied description-to-t_object patch to PLEXOSExporter.prepare_export")


def _source_system(context: PluginContext) -> Any:
    return cast(Any, context.source_system)


def _target_system(context: PluginContext) -> Any:
    return cast(Any, context.target_system)


def _ensure_membership(
    context: PluginContext,
    parent_object: Any,
    child_object: Any,
    collection: CollectionEnum,
) -> None:
    """Create and add a membership between parent and child objects.

    Parameters
    ----------
    context : PluginContext
        The translation context containing the target system
    parent_object : Any
        The parent object in the membership relationship
    child_object : Any
        The child object in the membership relationship
    collection : CollectionEnum
        The collection type for the membership
    """
    parent_key = getattr(parent_object, "uuid", None) or id(parent_object)
    child_key = getattr(child_object, "uuid", None) or id(child_object)
    membership_key = (collection, parent_key, child_key)

    membership_cache = context._cache.setdefault("membership_key_cache", set())
    if membership_key in membership_cache:
        return

    membership = PLEXOSMembership(
        parent_object=parent_object,
        child_object=child_object,
        collection=collection,
    )
    # Register on both endpoints so downstream consumers can discover memberships
    # regardless of traversal direction.
    _target_system(context).add_supplemental_attribute(parent_object, membership)
    _target_system(context).add_supplemental_attribute(child_object, membership)
    membership_cache.add(membership_key)


def _bus_name_to_area_and_zone(context: PluginContext) -> dict[str, tuple[str | None, str | None]]:
    """Build a single-pass index: bus_name -> (area_name, zone_name)."""

    cached = context._cache.get("bus_name_to_area_and_zone")
    if cached is not None:
        return cached

    result: dict[str, tuple[str | None, str | None]] = {}
    for bus in _source_system(context).get_components(ACBus):
        area = getattr(bus, "area", None)
        area_name: str | None = None
        if isinstance(area, Area):
            ext = getattr(area, "ext", None)
            arname = (ext or {}).get("ARNAME") if isinstance(ext, dict) else None
            area_name = str(arname) if arname else area.name
        elif area:
            area_name = str(area)

        load_zone = getattr(bus, "load_zone", None)
        zone_name: str | None = None
        if load_zone:
            if isinstance(load_zone, LoadZone):
                zone_name = load_zone.name
            elif hasattr(load_zone, "name") and load_zone.name:
                zone_name = str(load_zone.name)
            elif isinstance(load_zone, str):
                zone_name = load_zone
            else:
                zone_name = str(load_zone)
        result[bus.name] = (area_name, zone_name)

    context._cache["bus_name_to_area_and_zone"] = result
    return result


def _bus_to_area_name(bus: Any) -> str | None:
    """Resolve canonical area name for a source bus."""
    area = getattr(bus, "area", None)
    if isinstance(area, Area):
        ext = getattr(area, "ext", None)
        arname = (ext or {}).get("ARNAME") if isinstance(ext, dict) else None
        return str(arname) if arname else area.name
    if area:
        return str(area)
    return None


def _load_iso_rto_polygons() -> dict[str, list]:
    """Load ISO/RTO GeoJSON MultiPolygon boundaries from config directory (module-level cache)."""
    global _ISO_RTO_POLYGONS
    if _ISO_RTO_POLYGONS is not None:
        return _ISO_RTO_POLYGONS
    result: dict[str, list] = {}
    for path in sorted(_ISO_RTO_CONFIG_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:
            logger.warning("Could not load ISO/RTO coordinate file: {}", path)
            continue
        if data.get("type") == "MultiPolygon":
            result[path.stem] = data["coordinates"]
    _ISO_RTO_POLYGONS = result
    return result


def _ray_cast_point_in_ring(lon: float, lat: float, ring: list) -> bool:
    """Ray-casting test: return True if (lon, lat) is inside the polygon ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _point_in_multipolygon(lon: float, lat: float, polygons: list) -> bool:
    """Return True if (lon, lat) is inside any polygon in a GeoJSON MultiPolygon.

    Each element of *polygons* is a GeoJSON polygon: a list where index 0 is
    the outer ring and subsequent indices are holes (inner rings).
    """
    for polygon in polygons:
        outer_ring = polygon[0]
        if _ray_cast_point_in_ring(lon, lat, outer_ring):
            in_hole = any(_ray_cast_point_in_ring(lon, lat, hole) for hole in polygon[1:])
            if not in_hole:
                return True
    return False


def _get_bus_coordinates(bus: Any, context: PluginContext) -> tuple[float, float] | None:
    """Return (longitude, latitude) for *bus* via its supplemental GeographicInfo attribute."""
    try:
        from r2x_sienna.models import GeographicInfo

        attrs = _source_system(context).get_supplemental_attributes_with_component(bus, GeographicInfo)
        for attr in attrs:
            geo = getattr(attr, "geo_json", None)
            if geo is not None:
                coords = getattr(geo, "coordinates", None)
                if coords and len(coords) >= 2:
                    return float(coords[0]), float(coords[1])
    except Exception:
        pass
    return None


def _count_iso_rto_for_buses(buses: list[Any], context: PluginContext) -> dict[str, int]:
    """Return a count of buses per ISO/RTO for the given bus list.

    Performs a ray-casting point-in-polygon test using each bus's geographic
    coordinates from its supplemental :class:`GeographicInfo` attribute against
    the GeoJSON MultiPolygon boundaries in ``config/iso-rto-coordinates/``.

    Returns a mapping ``{iso_name: bus_count}``; buses with no usable coordinates
    or whose location falls outside all ISO/RTO boundaries are omitted.
    """
    iso_rto_polygons = _load_iso_rto_polygons()
    if not iso_rto_polygons:
        return {}

    iso_counts: dict[str, int] = {}
    for bus in buses:
        coords = _get_bus_coordinates(bus, context)
        if coords is None:
            continue
        lon, lat = coords
        for iso_name, polygons in iso_rto_polygons.items():
            if _point_in_multipolygon(lon, lat, polygons):
                iso_counts[iso_name] = iso_counts.get(iso_name, 0) + 1
                break  # each bus belongs to at most one ISO/RTO
    return iso_counts


def _resolve_iso_rto_for_buses(buses: list[Any], context: PluginContext) -> str | None:
    """Return the single ISO/RTO that contains the most buses, or ``None``.

    Used for zone categorisation where exactly one ISO/RTO label is needed.
    """
    iso_counts = _count_iso_rto_for_buses(buses, context)
    if not iso_counts:
        return None
    return max(iso_counts, key=iso_counts.__getitem__)


def _resolve_iso_rto_description_for_buses(buses: list[Any], context: PluginContext) -> str | None:
    """Return a comma-separated string listing every ISO/RTO that contains at least one bus.

    When a region's buses span multiple ISO/RTOs the names are sorted
    alphabetically and joined with ``', '`` (e.g. ``'ercot, miso'``).
    Returns ``None`` when no bus falls inside any ISO/RTO boundary
    (e.g. Canadian utilities whose coordinates are outside all boundaries).
    """
    iso_counts = _count_iso_rto_for_buses(buses, context)
    if not iso_counts:
        return None
    return ", ".join(sorted(iso_counts))


def _attach_reservoir_time_series_to_storage(
    context: PluginContext,
    storage_name: str,
    target_storage: Any,
) -> None:
    """Attach time series from source HydroReservoir to translated PLEXOS storage."""
    base_name = storage_name[:-5] if storage_name.endswith(("_head", "_tail")) else storage_name

    source_reservoir = None
    for r in _source_system(context).get_components(HydroReservoir):
        if r.name == base_name:
            source_reservoir = r
            break
    if source_reservoir is None:
        for r in _source_system(context).get_components(HydroReservoir):
            if base_name in r.name:
                source_reservoir = r
                break
    if source_reservoir is None:
        logger.warning("No source HydroReservoir found for '{}', skipping time series attachment.", base_name)
        return

    if not _source_system(context).time_series.has_time_series(source_reservoir):
        return

    import numpy as np
    from infrasys import SingleTimeSeries

    # Resolve max_mw for scaling max_active_power:
    # 1) NARIS_Pmax from reservoir ext (direct MW value)
    # 2) Fallback: matching HydroTurbine active_power_limits.max * base_power
    max_mw = 0.0
    ext = getattr(source_reservoir, "ext", None)
    naris_pmax = ext.get("NARIS_Pmax") if isinstance(ext, dict) else None
    if naris_pmax is not None:
        max_mw = abs(float(naris_pmax))
    else:
        turbine_base = base_name[: -len("_Reservoir")] if base_name.endswith("_Reservoir") else base_name
        for turbine_type in (HydroPumpTurbine, HydroTurbine):
            for t in _source_system(context).get_components(turbine_type):
                t_base = t.name[: -len("_Turbine")] if t.name.endswith("_Turbine") else t.name
                if t_base == turbine_base:
                    limits = getattr(t, "active_power_limits", None)
                    if limits is not None:
                        max_val = (
                            limits.get("max") if isinstance(limits, dict) else getattr(limits, "max", None)
                        )
                        if max_val is not None:
                            mag = get_magnitude(max_val)
                            raw = (
                                float(mag)
                                if mag is not None
                                else float(max_val)
                                if isinstance(max_val, int | float)
                                else None
                            )
                            if raw is not None:
                                max_mw = abs(raw) * resolve_base_power(t)
                    break
            if max_mw > 0.0:
                break

    for typed_ts in _source_system(context).list_time_series(source_reservoir):
        ts_name = "natural_inflow" if typed_ts.name == "inflow" else typed_ts.name
        ts_features = getattr(typed_ts, "features", {})
        if not _target_system(context).has_time_series(
            target_storage,
            name=ts_name,
            time_series_type=SingleTimeSeries,
            **ts_features,
        ):
            data = np.asarray(typed_ts.data)
            if typed_ts.name == "max_active_power":
                if max_mw > 0.0:
                    data = data * max_mw
                else:
                    logger.warning(
                        "Could not resolve max_mw for reservoir '{}', attaching unscaled max_active_power.",
                        base_name,
                    )
            fresh_ts = SingleTimeSeries.from_array(
                data=data,
                name=ts_name,
                initial_timestamp=typed_ts.initial_timestamp,
                resolution=typed_ts.resolution,
            )
            _target_system(context).add_time_series(fresh_ts, target_storage, **ts_features)
            logger.debug("Attached time series {} to storage {}", ts_name, storage_name)


def ensure_region_node_memberships(context: PluginContext) -> None:
    """Create Region->Node memberships for all regions and their nodes.

    Area maps to PLEXOSRegion, so regions are looked up by area_name.
    """
    regions_by_name = {r.name: r for r in _target_system(context).get_components(PLEXOSRegion)}
    source_buses = list(_source_system(context).get_components(ACBus))
    source_buses_by_uuid = {str(getattr(bus, "uuid", "")): bus for bus in source_buses}
    source_buses_by_name = {bus.name: bus for bus in source_buses}

    region_nodes_by_name: dict[str, list[PLEXOSNode]] = {name: [] for name in regions_by_name}

    total_memberships = 0
    for node in _target_system(context).get_components(PLEXOSNode):
        source_bus = source_buses_by_uuid.get(str(getattr(node, "uuid", "")))
        if source_bus is None:
            source_bus = source_buses_by_name.get(node.name)

        area_name = _bus_to_area_name(source_bus) if source_bus is not None else None
        if area_name is None:
            continue
        region = regions_by_name.get(area_name)
        if region is not None:
            _ensure_membership(context, node, region, CollectionEnum.Region)
            region_nodes = region_nodes_by_name.setdefault(area_name, [])
            if node not in region_nodes:
                region_nodes.append(node)
            total_memberships += 1

    context._cache["region_nodes_by_name"] = region_nodes_by_name

    logger.info("Total {} Region-Node memberships created.", total_memberships)


def ensure_reference_node_memberships(context: PluginContext) -> None:
    """Create exactly one Region->Node ReferenceNode membership per translated region.

    Selection priority per region:
    1) Any node whose source bus is REF/SLACK
    2) Fallback to highest node voltage, then highest load participation factor
    """

    def _as_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    regions_by_name = {r.name: r for r in _target_system(context).get_components(PLEXOSRegion)}
    nodes_by_region = cast(dict[str, list[PLEXOSNode]], context._cache.get("region_nodes_by_name", {}))
    if not nodes_by_region:
        ensure_region_node_memberships(context)
        nodes_by_region = cast(dict[str, list[PLEXOSNode]], context._cache.get("region_nodes_by_name", {}))

    # If some regions still have no node associations, recover from existing
    # supplemental Region memberships attached to the region endpoint.
    for region_name, region in regions_by_name.items():
        if nodes_by_region.get(region_name):
            continue

        recovered_nodes: list[PLEXOSNode] = []
        for membership in _target_system(context).get_supplemental_attributes_with_component(
            region,
            PLEXOSMembership,
        ):
            if membership.collection != CollectionEnum.Region:
                continue

            if membership.parent_object == region and isinstance(membership.child_object, PLEXOSNode):
                recovered_nodes.append(membership.child_object)
            elif membership.child_object == region and isinstance(membership.parent_object, PLEXOSNode):
                recovered_nodes.append(membership.parent_object)

        if recovered_nodes:
            nodes_by_region[region_name] = recovered_nodes

    all_nodes = list(_target_system(context).get_components(PLEXOSNode))

    ref_node_names: set[str] = set()
    ref_node_uuids: set[str] = set()
    for bus in _source_system(context).get_components(ACBus):
        bustype = getattr(bus, "bustype", None)
        bustype_name = getattr(bustype, "name", str(bustype)).upper() if bustype is not None else ""
        if bustype not in {ACBusTypes.REF, ACBusTypes.SLACK} and bustype_name not in {"REF", "SLACK"}:
            continue

        ref_node_names.add(bus.name)
        ref_node_uuids.add(str(getattr(bus, "uuid", "")))

    total_memberships = 0
    for region_name, region in regions_by_name.items():
        region_nodes = nodes_by_region.get(region_name, [])
        if not region_nodes and not all_nodes:
            continue

        slack_nodes = [
            node
            for node in region_nodes
            if (
                node.name in ref_node_names
                or str(getattr(node, "uuid", "")) in ref_node_uuids
                or bool(getattr(node, "is_slack_bus", 0))
            )
        ]
        candidate_nodes = slack_nodes if slack_nodes else region_nodes
        used_global_fallback = False
        if not candidate_nodes:
            candidate_nodes = all_nodes
            used_global_fallback = True

        chosen = max(
            candidate_nodes,
            key=lambda node: (
                _as_float(getattr(node, "voltage", 0.0)),
                _as_float(getattr(node, "load_participation_factor", 0.0)),
                node.name,
            ),
        )

        _ensure_membership(context, region, chosen, CollectionEnum.ReferenceNode)
        total_memberships += 1

        if used_global_fallback:
            logger.warning(
                "No nodes were associated with region '{}'; using global fallback reference node '{}'.",
                region_name,
                chosen.name,
            )
        elif not slack_nodes:
            logger.debug(
                "No REF/SLACK bus found for region '{}'; using fallback reference node '{}'.",
                region_name,
                chosen.name,
            )

    logger.info("Total {} ReferenceNode Region->Node memberships created.", total_memberships)


def _extract_base_name(name: str) -> str:
    for suffix in ("_Turbine", "_Reservoir_head", "_Reservoir_tail", "_Reservoir", "_head", "_tail"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def ensure_head_storage_generator_membership(context: PluginContext) -> None:
    """Create HeadStorage memberships between generators and head storages.

    Drives linkage from HydroReservoir.downstream_turbines (and ext["plants"] as fallback)
    to avoid relying on name conventions. Also attaches time series to all head storages.
    """
    from r2x_sienna_to_plexos.getters import _build_generator_display_name_index

    display_name_index = _build_generator_display_name_index(context)
    generators_by_name = {g.name: g for g in _target_system(context).get_components(PLEXOSGenerator)}
    storages_by_name = {s.name: s for s in _target_system(context).get_components(PLEXOSStorage)}

    # Attach time series to ALL head storages regardless of membership
    for storage in _target_system(context).get_components(PLEXOSStorage):
        if storage.name.endswith("_head"):
            _attach_reservoir_time_series_to_storage(context, storage.name, storage)

    total_memberships = 0
    # Iterate over HydroReservoir.downstream_turbines
    for reservoir in _source_system(context).get_components(HydroReservoir):
        ext = getattr(reservoir, "ext", None)
        base = None
        if isinstance(ext, dict):
            plant_name = ext.get("plant_name")
            if plant_name:
                base = str(plant_name)
        if base is None:
            rname = reservoir.name
            for suffix in ("_head", "_tail"):
                if rname.endswith(suffix):
                    rname = rname[: -len(suffix)]
                    break
            base = rname

        storage_name = f"{base}_head"
        target_storage = storages_by_name.get(storage_name)
        if target_storage is None:
            logger.debug(
                "No PLEXOSStorage '{}' found for HydroReservoir '{}', skipping.", storage_name, reservoir.name
            )
            continue

        turbines = list(getattr(reservoir, "downstream_turbines", None) or [])
        if not turbines and isinstance(ext, dict):
            all_turbines = {t.name: t for t in _source_system(context).get_components(HydroPumpTurbine)}
            turbines = [
                all_turbines[pid]
                for pid in (ext.get("plants") or [])
                if isinstance(pid, str) and pid in all_turbines
            ]

        for turbine in turbines:
            tname = getattr(turbine, "name", None)
            if not tname:
                continue
            target_gen_name = display_name_index.get(tname, tname)
            target_gen = generators_by_name.get(target_gen_name)
            if target_gen is None:
                logger.debug("No PLEXOSGenerator found for HydroPumpTurbine '{}', skipping.", tname)
                continue
            _ensure_membership(context, target_gen, target_storage, CollectionEnum.HeadStorage)
            total_memberships += 1

    # Also support source models that expose reservoir links on HydroPumpTurbine.reservoirs.
    for turbine in _source_system(context).get_components(HydroPumpTurbine):
        tname = getattr(turbine, "name", None)
        if not tname:
            continue
        target_gen_name = display_name_index.get(tname, tname)
        target_gen = generators_by_name.get(target_gen_name)
        if target_gen is None:
            continue

        for reservoir in getattr(turbine, "reservoirs", None) or []:
            location = getattr(getattr(reservoir, "reservoir_location", None), "value", None)
            if str(location).upper() != "HEAD":
                continue

            rname = getattr(reservoir, "name", None)
            if not rname:
                continue
            storage_name = rname if str(rname).endswith("_head") else f"{rname}_head"
            target_storage = storages_by_name.get(storage_name)
            if target_storage is None:
                continue
            _ensure_membership(context, target_gen, target_storage, CollectionEnum.HeadStorage)
            total_memberships += 1

    # Fallback: For all generators and storages with matching _head names, ensure membership exists
    for gen_name, gen in generators_by_name.items():
        if gen_name.endswith("_head"):
            storage = storages_by_name.get(gen_name)
            if storage is not None:
                memberships = _target_system(context).get_supplemental_attributes_with_component(
                    gen, PLEXOSMembership
                )
                if not any(
                    m.collection == CollectionEnum.HeadStorage and m.child_object == storage
                    for m in memberships
                ):
                    _ensure_membership(context, gen, storage, CollectionEnum.HeadStorage)
                    total_memberships += 1
    logger.info("Total {} HeadStorage-Generator memberships created (including fallback).", total_memberships)


def ensure_tail_storage_generator_membership(context: PluginContext) -> None:
    """Create TailStorage memberships between generators and tail storages.

    Drives linkage from HydroReservoir.downstream_turbines (and ext["plants"] as fallback)
    to avoid relying on name conventions. Also attaches time series to all tail storages.
    """
    from r2x_sienna_to_plexos.getters import _build_generator_display_name_index

    display_name_index = _build_generator_display_name_index(context)
    generators_by_name = {g.name: g for g in _target_system(context).get_components(PLEXOSGenerator)}
    storages_by_name = {s.name: s for s in _target_system(context).get_components(PLEXOSStorage)}

    # Attach time series to ALL tail storages regardless of membership
    for storage in _target_system(context).get_components(PLEXOSStorage):
        if storage.name.endswith("_tail"):
            _attach_reservoir_time_series_to_storage(context, storage.name, storage)

    total_memberships = 0
    # Iterate over HydroReservoir.downstream_turbines
    for reservoir in _source_system(context).get_components(HydroReservoir):
        ext = getattr(reservoir, "ext", None)
        base = None
        if isinstance(ext, dict):
            plant_name = ext.get("plant_name")
            if plant_name:
                base = str(plant_name)
        if base is None:
            rname = reservoir.name
            for suffix in ("_head", "_tail"):
                if rname.endswith(suffix):
                    rname = rname[: -len(suffix)]
                    break
            base = rname

        storage_name = f"{base}_tail"
        target_storage = storages_by_name.get(storage_name)
        if target_storage is None:
            logger.debug(
                "No PLEXOSStorage '{}' found for HydroReservoir '{}', skipping.", storage_name, reservoir.name
            )
            continue

        turbines = list(getattr(reservoir, "downstream_turbines", None) or [])
        if not turbines and isinstance(ext, dict):
            all_turbines = {t.name: t for t in _source_system(context).get_components(HydroPumpTurbine)}
            turbines = [
                all_turbines[pid]
                for pid in (ext.get("plants") or [])
                if isinstance(pid, str) and pid in all_turbines
            ]

        for turbine in turbines:
            tname = getattr(turbine, "name", None)
            if not tname:
                continue
            target_gen_name = display_name_index.get(tname, tname)
            target_gen = generators_by_name.get(target_gen_name)
            if target_gen is None:
                logger.debug("No PLEXOSGenerator found for HydroPumpTurbine '{}', skipping.", tname)
                continue
            _ensure_membership(context, target_gen, target_storage, CollectionEnum.TailStorage)
            total_memberships += 1

    # Also support source models that expose reservoir links on HydroPumpTurbine.reservoirs.
    for turbine in _source_system(context).get_components(HydroPumpTurbine):
        tname = getattr(turbine, "name", None)
        if not tname:
            continue
        target_gen_name = display_name_index.get(tname, tname)
        target_gen = generators_by_name.get(target_gen_name)
        if target_gen is None:
            continue

        for reservoir in getattr(turbine, "reservoirs", None) or []:
            location = getattr(getattr(reservoir, "reservoir_location", None), "value", None)
            if str(location).upper() != "TAIL":
                continue

            rname = getattr(reservoir, "name", None)
            if not rname:
                continue
            storage_name = rname if str(rname).endswith("_tail") else f"{rname}_tail"
            target_storage = storages_by_name.get(storage_name)
            if target_storage is None:
                continue
            _ensure_membership(context, target_gen, target_storage, CollectionEnum.TailStorage)
            total_memberships += 1

    # Fallback: For all generators and storages with matching _tail names, ensure membership exists
    for gen_name, gen in generators_by_name.items():
        if gen_name.endswith("_tail"):
            storage = storages_by_name.get(gen_name)
            if storage is not None:
                memberships = _target_system(context).get_supplemental_attributes_with_component(
                    gen, PLEXOSMembership
                )
                if not any(
                    m.collection == CollectionEnum.TailStorage and m.child_object == storage
                    for m in memberships
                ):
                    _ensure_membership(context, gen, storage, CollectionEnum.TailStorage)
                    total_memberships += 1
    logger.info("Total {} TailStorage-Generator memberships created (including fallback).", total_memberships)


def ensure_source_conflicts_resolved(context: PluginContext) -> None:
    """Remove PLEXOSGenerators for available=False source generators that are replaced by Source components.

    When a source generator (e.g. ThermalStandard) has ``available=False`` and a
    ``Source`` component with the same name also exists in the source system, the
    PLEXOSGenerator created from the unavailable generator is removed from the
    target.  The PLEXOSGenerator created from the ``Source`` component takes
    precedence.
    """
    from r2x_sienna.models import Source

    from r2x_sienna_to_plexos.getters import _build_generator_display_name_index
    from r2x_sienna_to_plexos.getters_mappings import SOURCE_GENERATOR_TYPES

    source_system = _source_system(context)
    target_system = _target_system(context)

    # Collect all Source component names.
    source_names = {s.name for s in source_system.get_components(Source)}
    if not source_names:
        return

    display_name_index = _build_generator_display_name_index(context)

    # Build a name → list-of-generators map for the target (duplicate names are allowed).
    target_gens_by_name: dict[str, list[Any]] = {}
    for g in target_system.get_components(PLEXOSGenerator):
        target_gens_by_name.setdefault(g.name, []).append(g)

    removed = 0
    for gen_type in SOURCE_GENERATOR_TYPES:
        if gen_type is Source:
            continue
        for gen in source_system.get_components(gen_type):
            if gen.name not in source_names:
                continue
            if getattr(gen, "available", True):
                continue
            # This generator is available=False AND a Source with the same name exists.
            target_name = display_name_index.get(gen.name, gen.name)
            candidates = target_gens_by_name.get(target_name, [])
            for target_gen in list(candidates):
                ext = getattr(target_gen, "ext", {}) or {}
                if ext.get("sienna_type") != "Source":
                    target_system.remove_component(target_gen)
                    candidates.remove(target_gen)
                    removed += 1
                    logger.debug(
                        "Removed PLEXOSGenerator '{}' (available=False, superseded by Source).",
                        target_name,
                    )

    if removed:
        logger.info("Source conflict resolution removed {} PLEXOSGenerator(s).", removed)


def ensure_generator_node_memberships(context: PluginContext) -> None:
    """Ensure every translated generator has a node membership based on its source bus."""
    from r2x_sienna_to_plexos.getters import _build_generator_display_name_index
    from r2x_sienna_to_plexos.getters_mappings import SOURCE_GENERATOR_TYPES

    source_generators: dict[str, Any] = {}
    for gen_type in SOURCE_GENERATOR_TYPES:
        for gen in _source_system(context).get_components(gen_type):
            source_generators[gen.name] = gen

    display_name_index = _build_generator_display_name_index(context)
    target_generators = {g.name: g for g in _target_system(context).get_components(PLEXOSGenerator)}
    nodes_by_name = {n.name: n for n in _target_system(context).get_components(PLEXOSNode)}

    total_memberships = 0
    cached: set[tuple[str, str]] = set()
    for name, source_gen in source_generators.items():
        target_name = display_name_index.get(name, name)
        target_gen = target_generators.get(target_name)
        if target_gen is None:
            continue
        bus = getattr(source_gen, "bus", None)
        if bus is None:
            continue
        node = nodes_by_name.get(bus.name)
        if node is not None:
            key = (target_name, node.name)
            if key in cached:
                continue
            cached.add(key)
            _ensure_membership(context, target_gen, node, CollectionEnum.Nodes)
            total_memberships += 1

    logger.info("Total {} Generator-Node memberships created.", total_memberships)


def ensure_generator_time_series(context: PluginContext) -> None:
    """Attach time series from every source generator to its translated PLEXOSGenerator."""
    from r2x_sienna_to_plexos.getters import (
        _attach_generator_time_series,
        _build_generator_display_name_index,
    )

    from .getters_mappings import SOURCE_GENERATOR_TYPES

    display_name_index = _build_generator_display_name_index(context)
    target_generators = {g.name: g for g in _target_system(context).get_components(PLEXOSGenerator)}

    total = 0
    for gen_type in SOURCE_GENERATOR_TYPES:
        for source_gen in _source_system(context).get_components(gen_type):
            target_name = display_name_index.get(source_gen.name, source_gen.name)
            target_gen = target_generators.get(target_name)
            if target_gen is None:
                continue
            _attach_generator_time_series(context, source_gen.name, target_gen)
            _attach_hydro_reservoir_inflow_to_generator_budget(context, source_gen, target_gen)
            total += 1
    logger.info("Ensured time series for {} generators.", total)


def _attach_hydro_reservoir_inflow_to_generator_budget(
    context: PluginContext,
    source_generator: Any,
    target_generator: Any,
) -> None:
    """Attach HydroReservoir inflow to generator as max_energy_day for non-pumped HydroTurbine units."""
    if isinstance(source_generator, HydroPumpTurbine) or not isinstance(source_generator, HydroTurbine):
        return

    pump_load = getattr(source_generator, "rating", None)
    if pump_load is not None:
        magnitude = get_magnitude(pump_load)
        raw = (
            float(magnitude)
            if magnitude is not None
            else float(pump_load)
            if isinstance(pump_load, int | float)
            else 0.0
        )
        if not math.isclose(raw * resolve_base_power(source_generator), 0.0, abs_tol=1e-9):
            return

    from infrasys import SingleTimeSeries

    from r2x_sienna_to_plexos.getters import _build_reservoir_by_turbine_index

    source_reservoir = _build_reservoir_by_turbine_index(context).get(source_generator.name)
    if source_reservoir is None or not _source_system(context).time_series.has_time_series(source_reservoir):
        return

    for metadata in _source_system(context).time_series.list_time_series_metadata(source_reservoir):
        if metadata.name not in {"inflow", "natural_inflow"}:
            continue
        features = getattr(metadata, "features", {}) or {}
        if _target_system(context).has_time_series(
            target_generator,
            name="max_energy_day",
            time_series_type=SingleTimeSeries,
            **features,
        ):
            continue

        ts_list = _source_system(context).list_time_series(
            source_reservoir,
            name=metadata.name,
            **features,
        )
        if not ts_list:
            continue

        typed_source_ts = ts_list[0]
        ts_copy = deepcopy(typed_source_ts)
        ts_copy.name = "max_energy_day"
        _target_system(context).add_time_series(ts_copy, target_generator, **features)


def ensure_reserve_time_series(context: PluginContext) -> None:
    """Attach reserve time series from source VariableReserve to translated PLEXOSReserve."""

    def _normalize_series_name(name: Any) -> str:
        return str(name or "").strip().lower().replace("-", "_").replace(" ", "_")

    def _freeze_features(features: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((str(key), repr(value)) for key, value in features.items()))

    source_reserves = {r.name: r for r in _source_system(context).get_components(VariableReserve)}
    base = getattr(getattr(context, "source_system", None), "base_power", None)
    try:
        system_base = float(base) if base is not None else 100.0
    except (TypeError, ValueError):
        system_base = 100.0

    total = 0
    seen: set[tuple[str, str, type[Any], tuple[tuple[str, str], ...]]] = set()
    for reserve in _target_system(context).get_components(PLEXOSReserve):
        source_reserve = source_reserves.get(reserve.name)
        if source_reserve is None:
            continue

        if not _source_system(context).time_series.has_time_series(source_reserve):
            continue

        for metadata in _source_system(context).time_series.list_time_series_metadata(source_reserve):
            features = getattr(metadata, "features", {}) or {}
            ts_list = _source_system(context).list_time_series(
                source_reserve,
                name=metadata.name,
                **features,
            )
            if not ts_list:
                continue

            typed_source_ts = ts_list[0]
            source_names = {
                _normalize_series_name(getattr(metadata, "name", None)),
                _normalize_series_name(getattr(typed_source_ts, "name", None)),
            }
            ts_name = (
                "min_provision" if {"requirement", "min_provision"} & source_names else typed_source_ts.name
            )

            ts_copy_any = deepcopy(typed_source_ts)
            ts_copy_any.name = ts_name

            # Reserve requirement is represented in p.u. in Sienna; PLEXOS min_provision expects MW.
            if ts_name == "min_provision":
                try:
                    ts_copy_any.data = ts_copy_any.data * system_base
                except TypeError:
                    ts_copy_any.data = [float(value) * system_base for value in ts_copy_any.data]

            seen_key = (reserve.name, ts_name, type(typed_source_ts), _freeze_features(features))
            if seen_key in seen:
                continue

            if _target_system(context).has_time_series(
                reserve,
                name=ts_name,
                time_series_type=type(typed_source_ts),
                **features,
            ):
                continue

            _target_system(context).add_time_series(ts_copy_any, reserve, **features)
            seen.add(seen_key)
            total += 1

    logger.info("Ensured reserve time series for {} associations.", total)


def ensure_battery_node_memberships(context: PluginContext) -> None:
    """Ensure every translated battery has a node membership based on its source bus."""
    target_batteries = {b.name: b for b in _target_system(context).get_components(PLEXOSBattery)}
    nodes_by_name = {n.name: n for n in _target_system(context).get_components(PLEXOSNode)}

    total_memberships = 0
    for battery in _source_system(context).get_components(EnergyReservoirStorage):
        target_battery = target_batteries.get(battery.name)
        if target_battery is None:
            continue
        bus = getattr(battery, "bus", None)
        if bus is None:
            continue
        node = nodes_by_name.get(bus.name)
        if node is not None:
            _ensure_membership(context, target_battery, node, CollectionEnum.Nodes)
            total_memberships += 1

    logger.info("Total {} Battery-Node memberships created.", total_memberships)


def ensure_reserve_generator_memberships(context: PluginContext) -> None:
    """Create Reserve->Generator memberships by finding which generators provide each reserve service."""
    from r2x_sienna_to_plexos.getters import _build_generator_display_name_index
    from r2x_sienna_to_plexos.getters_mappings import SOURCE_GENERATOR_TYPES

    reserves_by_name = {r.name: r for r in _target_system(context).get_components(PLEXOSReserve)}
    generators_by_name = {g.name: g for g in _target_system(context).get_components(PLEXOSGenerator)}
    display_name_index = _build_generator_display_name_index(context)

    reserve_to_generators: dict[str, list[Any]] = {}
    for gen_type in SOURCE_GENERATOR_TYPES:
        for gen in _source_system(context).get_components(gen_type):
            for service in getattr(gen, "services", None) or []:
                sname = getattr(service, "name", None)
                if sname and sname in reserves_by_name:
                    reserve_to_generators.setdefault(sname, []).append(gen)

    total_memberships = 0
    for reserve_name, target_reserve in reserves_by_name.items():
        for source_gen in reserve_to_generators.get(reserve_name, []):
            target_name = display_name_index.get(source_gen.name, source_gen.name)
            target_gen = generators_by_name.get(target_name)
            if target_gen is not None:
                _ensure_membership(context, target_reserve, target_gen, CollectionEnum.Generators)
                total_memberships += 1

    logger.info("Total {} Reserve-Generator memberships created.", total_memberships)


def ensure_reserve_battery_memberships(context: PluginContext) -> None:
    """Create Reserve->Battery memberships by checking the services of each source battery."""
    reserves_by_name = {r.name: r for r in _target_system(context).get_components(PLEXOSReserve)}
    batteries_by_name = {b.name: b for b in _target_system(context).get_components(PLEXOSBattery)}

    total_memberships = 0
    for source_battery in _source_system(context).get_components(EnergyReservoirStorage):
        target_battery = batteries_by_name.get(source_battery.name)
        if target_battery is None:
            continue
        for service in getattr(source_battery, "services", None) or []:
            if not isinstance(service, VariableReserve):
                continue
            target_reserve = reserves_by_name.get(service.name)
            if target_reserve is not None:
                _ensure_membership(context, target_reserve, target_battery, CollectionEnum.Batteries)
                total_memberships += 1

    logger.info("Total {} Reserve-Battery memberships created.", total_memberships)


def ensure_transformer_node_memberships(context: PluginContext) -> None:
    """Create Transformer->Node memberships (both from and to) for all transformers."""
    source_transformers_by_name: dict[str, Any] = {}
    for tf_type in _SIENNA_TRANSFORMER_TYPES:
        for tf in _source_system(context).get_components(tf_type):
            source_transformers_by_name[tf.name.strip()] = tf

    nodes_by_name = {n.name: n for n in _target_system(context).get_components(PLEXOSNode)}

    total_memberships = 0
    for transformer in _target_system(context).get_components(PLEXOSTransformer):
        source_tf = source_transformers_by_name.get(transformer.name)
        if source_tf is None or not hasattr(source_tf, "arc"):
            continue

        arc = source_tf.arc
        from_name = arc.from_to.name if hasattr(arc.from_to, "name") else str(arc.from_to)
        from_node = nodes_by_name.get(from_name)
        if from_node is not None:
            _ensure_membership(context, transformer, from_node, CollectionEnum.NodeFrom)
            total_memberships += 1

        to_name = arc.to_from.name if hasattr(arc.to_from, "name") else str(arc.to_from)
        to_node = nodes_by_name.get(to_name)
        if to_node is not None:
            _ensure_membership(context, transformer, to_node, CollectionEnum.NodeTo)
            total_memberships += 1

    logger.info("Total {} Transformer-Node memberships created.", total_memberships)


def ensure_line_node_memberships(context: PluginContext) -> None:
    """Create Line->Node memberships (both NodeFrom and NodeTo) for all translated lines.

    Mirrors ``ensure_transformer_node_memberships`` for PLEXOSLine objects.
    The rules.json membership rules attempt the same thing via the getter
    mechanism but fail silently when the source line or target node cannot be
    resolved; this function provides a reliable post-processing fallback.

    For HVDC lines whose arc endpoints are ``DCBus`` objects (which have no
    corresponding ``PLEXOSNode`` from the normal ACBus translation), this
    function creates minimal ``PLEXOSNode`` objects and assigns them to the
    appropriate region so that PLEXOS validation passes.
    """
    from r2x_sienna_to_plexos.getters_mappings import SOURCE_LINE_TYPES

    source_lines_by_name: dict[str, Any] = {}
    for line_type in SOURCE_LINE_TYPES:
        for ln in _source_system(context).get_components(line_type):
            source_lines_by_name[ln.name.strip()] = ln

    target_sys = _target_system(context)
    nodes_by_name = {n.name: n for n in target_sys.get_components(PLEXOSNode)}
    regions_by_name = {r.name: r for r in target_sys.get_components(PLEXOSRegion)}

    def _get_or_create_node(bus: Any) -> PLEXOSNode | None:
        """Return existing PLEXOSNode or create one for a DCBus endpoint."""
        bus_name = bus.name if hasattr(bus, "name") else str(bus)
        node = nodes_by_name.get(bus_name)
        if node is not None:
            return node
        if isinstance(bus, DCBus):
            node = PLEXOSNode(name=bus_name, category="dc-node")
            target_sys.add_component(node)
            nodes_by_name[bus_name] = node
            # Assign to region using the same area-name resolution as ACBus nodes
            area_name = _bus_to_area_name(bus)
            if area_name:
                region = regions_by_name.get(area_name)
                if region is not None:
                    _ensure_membership(context, node, region, CollectionEnum.Region)
            logger.debug("Created PLEXOSNode '{}' for DCBus endpoint.", bus_name)
            return node
        return None

    total_memberships = 0
    for target_line in target_sys.get_components(PLEXOSLine):
        source_line = source_lines_by_name.get(target_line.name)
        if source_line is None or not hasattr(source_line, "arc"):
            continue

        arc = source_line.arc
        from_node = _get_or_create_node(arc.from_to)
        if from_node is not None:
            _ensure_membership(context, target_line, from_node, CollectionEnum.NodeFrom)
            total_memberships += 1

        to_node = _get_or_create_node(arc.to_from)
        if to_node is not None:
            _ensure_membership(context, target_line, to_node, CollectionEnum.NodeTo)
            total_memberships += 1

    logger.info("Total {} Line-Node memberships created.", total_memberships)


def ensure_interface_line_memberships(context: PluginContext) -> None:
    """Create Interface->Line memberships for all interfaces and their lines."""
    source_interfaces_by_name = {
        i.name: i for i in _source_system(context).get_components(TransmissionInterface)
    }
    lines_by_name = {ln.name: ln for ln in _target_system(context).get_components(PLEXOSLine)}

    total_memberships = 0
    for interface in _target_system(context).get_components(PLEXOSInterface):
        source_intf = source_interfaces_by_name.get(interface.name)
        if source_intf is None:
            continue
        for line_name in getattr(source_intf, "direction_mapping", None) or {}:
            line = lines_by_name.get(line_name)
            if line is not None:
                _ensure_membership(context, interface, line, CollectionEnum.Lines)
                total_memberships += 1

    logger.info("Total {} Interface-Line memberships created.", total_memberships)


def ensure_pumped_hydro_storages_created(context: PluginContext) -> None:
    """Synthesize head/tail PLEXOSStorage entries for pumped-hydro generators missing them.

    Pumped-hydro generators in PLEXOS need both a head and a tail storage so
    the pump/generator pair can move energy between reservoirs and perform
    arbitrage. When the source Sienna system has no reservoirs attached to a
    pumped-hydro turbine (common for ReEDS-style aggregated systems), create
    minimal ``PLEXOSStorage`` entries with ``units=1`` and ``max_volume`` /
    ``initial_volume`` derived from the generator's ``max_capacity``, and
    attach the corresponding ``HeadStorage`` / ``TailStorage`` memberships.
    """
    target_system = _target_system(context)
    storages_by_name = {s.name: s for s in target_system.get_components(PLEXOSStorage)}

    created_storages = 0
    created_memberships = 0
    for gen in target_system.get_components(PLEXOSGenerator):
        if getattr(gen, "category", None) != "pumped-hydro":
            continue

        memberships = target_system.get_supplemental_attributes_with_component(gen, PLEXOSMembership)
        has_head = any(
            m.collection == CollectionEnum.HeadStorage and m.parent_object == gen for m in memberships
        )
        has_tail = any(
            m.collection == CollectionEnum.TailStorage and m.parent_object == gen for m in memberships
        )

        if has_head and has_tail:
            continue

        # ``max_capacity`` is in MW; PLEXOS storage volumes are in GWh. Size
        # the synthesized reservoir for a typical pumped-hydro duration so the
        # generator can run at full output for that many hours before the
        # head storage empties (or the tail fills). Initial volume is half-full
        # so the unit can both pump and generate immediately.
        pumped_hydro_duration_hours = 10.0
        max_capacity_mw = float(getattr(gen, "max_capacity", 0.0) or 0.0)
        if max_capacity_mw > 0.0:
            max_volume = round(max_capacity_mw * pumped_hydro_duration_hours / 1000.0, 4)
        else:
            max_volume = 1.0  # GWh fallback for degenerate sources
        initial_volume = round(max_volume * 0.5, 4)

        for suffix, collection, already_present in (
            ("_head", CollectionEnum.HeadStorage, has_head),
            ("_tail", CollectionEnum.TailStorage, has_tail),
        ):
            if already_present:
                continue
            storage_name = f"{gen.name}{suffix}"
            storage = storages_by_name.get(storage_name)
            if storage is None:
                storage = PLEXOSStorage(
                    name=storage_name,
                    category="head" if suffix == "_head" else "tail",
                    units=1,
                    max_volume=max_volume,
                    initial_volume=initial_volume,
                )
                target_system.add_component(storage)
                storages_by_name[storage_name] = storage
                created_storages += 1
            _ensure_membership(context, gen, storage, collection)
            created_memberships += 1

    logger.info(
        "Synthesized {} pumped-hydro storages and {} memberships for generators missing reservoirs.",
        created_storages,
        created_memberships,
    )


def ensure_pumped_hydro_storage_memberships(context: PluginContext) -> None:
    """Create Generator->Storage memberships for pumped hydro generators."""
    storages_by_name = {s.name: s for s in _target_system(context).get_components(PLEXOSStorage)}

    total_memberships = 0
    for gen in _target_system(context).get_components(PLEXOSGenerator):
        if gen.name.endswith("_head"):
            storage = storages_by_name.get(gen.name)
            if storage is not None:
                _ensure_membership(context, gen, storage, CollectionEnum.HeadStorage)
                total_memberships += 1
        elif gen.name.endswith("_tail"):
            storage = storages_by_name.get(gen.name)
            if storage is not None:
                _ensure_membership(context, gen, storage, CollectionEnum.TailStorage)
                total_memberships += 1

    logger.info("Total {} Pumped Hydro Generator-Storage memberships created.", total_memberships)


def normalize_value_curve(curve: Any) -> InputOutputCurveValue | None:
    """Normalize value curve to InputOutputCurve format.

    Converts IncrementalCurve and AverageRateCurve to InputOutputCurve.
    Returns None if conversion fails or curve is not a compatible type.

    Parameters
    ----------
    curve : Any
        A value curve object to normalize

    Returns
    -------
    InputOutputCurve | None
        Normalized curve, or None if normalization fails
    """
    if isinstance(curve, Mapping):
        function_data = curve.get("function_data")
        if not isinstance(function_data, Mapping):
            return None

        def _as_float(value: Any, default: float = 0.0) -> float:
            magnitude = get_magnitude(value)
            if magnitude is not None:
                return float(magnitude)
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        fd: LinearFunctionData | QuadraticFunctionData | PiecewiseLinearData
        if "points" in function_data:
            points_raw = function_data.get("points") or []
            points: list[XYCoords] = []
            for point in points_raw:
                if isinstance(point, Mapping):
                    x = _as_float(point.get("x"))
                    y = _as_float(point.get("y"))
                elif isinstance(point, tuple | list) and len(point) >= 2:
                    x = _as_float(point[0])
                    y = _as_float(point[1])
                else:
                    continue
                points.append(XYCoords(x=x, y=y))
            if not points:
                return None
            fd = PiecewiseLinearData(points=points)
        elif "x_coords" in function_data and "y_coords" in function_data:
            x_raw = function_data.get("x_coords") or []
            y_raw = function_data.get("y_coords") or []
            if not isinstance(x_raw, list) or not isinstance(y_raw, list) or len(x_raw) < 2:
                return None

            x_values = [_as_float(value) for value in x_raw]
            y_values = [_as_float(value) for value in y_raw]
            points: list[XYCoords] = []

            # Case 1: y-coordinates are explicit point values.
            if len(y_values) == len(x_values):
                points = [XYCoords(x=x, y=y) for x, y in zip(x_values, y_values, strict=False)]

            # Case 2: y-coordinates are segment slopes with one value per interval.
            elif len(y_values) == len(x_values) - 1:
                cumulative_y = 0.0
                points.append(XYCoords(x=x_values[0], y=0.0))
                for idx, slope in enumerate(y_values, start=1):
                    dx = x_values[idx] - x_values[idx - 1]
                    if dx <= 0:
                        continue
                    cumulative_y += slope * dx
                    points.append(XYCoords(x=x_values[idx], y=cumulative_y))

            if len(points) < 2:
                return None
            fd = PiecewiseLinearData(points=points)
        elif "quadratic_term" in function_data or "cubic_term" in function_data:
            kwargs: dict[str, Any] = {
                "proportional_term": _as_float(function_data.get("proportional_term")),
                "constant_term": _as_float(function_data.get("constant_term")),
                "quadratic_term": _as_float(function_data.get("quadratic_term")),
            }
            if "cubic_term" in function_data:
                kwargs["cubic_term"] = _as_float(function_data.get("cubic_term"))
            fd = QuadraticFunctionData(**kwargs)
        else:
            fd = LinearFunctionData(
                proportional_term=_as_float(function_data.get("proportional_term")),
                constant_term=_as_float(function_data.get("constant_term")),
            )

        return InputOutputCurve(
            function_data=fd,
            input_at_zero=curve.get("input_at_zero"),
        )

    if isinstance(curve, InputOutputCurve):
        return curve
    if isinstance(curve, IncrementalCurve | AverageRateCurve):
        try:
            return curve.to_input_output()
        except Exception:
            return None
    return None


def extract_piecewise_segments(points: list[XYCoords]) -> tuple[list[float], list[float]]:
    """Extract load points and slopes from piecewise linear points.

    Converts a list of XYCoords points into load points (x-coordinates) and
    slopes (y-differences divided by x-differences).

    Parameters
    ----------
    points : list[XYCoords]
        List of XYCoords points defining segments of a piecewise linear curve

    Returns
    -------
    tuple[list[float], list[float]]
        Tuple of (load_points, slopes) where:
        - load_points: x-coordinates where slope changes
        - slopes: incremental slopes for each segment
    """
    load_points: list[float] = []
    slopes: list[float] = []
    if not points:
        return load_points, slopes
    previous = points[0]
    for current in points[1:]:
        dx = current.x - previous.x
        if dx <= 0:
            previous = current
            continue
        slopes.append(float((current.y - previous.y) / dx))
        load_points.append(float(current.x))
        previous = current
    return load_points, slopes


def resolve_base_power(component: Any) -> float:
    """Resolve base power from component.

    Attempts to extract base power from component's base_power or _system_base
    attributes. Returns 1.0 if neither is available.

    Parameters
    ----------
    component : Any
        Component object with potential base_power or _system_base attribute

    Returns
    -------
    float
        Base power value, defaults to 1.0
    """
    base = get_magnitude(getattr(component, "base_power", None))
    if base is None:
        raw = getattr(component, "_system_base", None)
        if isinstance(raw, int | float):
            base = float(raw)
        elif raw is not None:
            base = get_magnitude(raw)
    return float(base) if base is not None else 1.0


def compute_heat_rate_data(component: Any) -> dict[str, Any]:
    """Compute heat rate data from component operation cost.

    Extracts heat rate information from a component's operation cost and
    converts it to a dictionary with heat_rate, heat_rate_base, load_point,
    and heat_rate_incr keys depending on the cost curve type.

    Parameters
    ----------
    component : Any
        Component with operation_cost attribute

    Returns
    -------
    dict[str, Any]
        Dictionary with heat rate data, may contain:
        - heat_rate: Linear heat rate
        - heat_rate_base: Constant term for quadratic curve
        - heat_rate_incr: Quadratic coefficient or multiband values
        - load_point: Load points for multiband curves
    """
    cost = getattr(component, "operation_cost", None)
    variable = None
    if cost is not None:
        if isinstance(cost, Mapping):
            variable = cost.get("variable")
        if variable is None:
            variable = getattr(cost, "variable", None)

    curve_source = None
    if isinstance(variable, Mapping):
        curve_source = variable.get("value_curve")
    elif isinstance(variable, FuelCurve):
        curve_source = variable.value_curve
    else:
        return {}

    curve = normalize_value_curve(curve_source)
    if curve is None or curve.function_data is None:
        return {}
    data: dict[str, Any] = {}
    fd = curve.function_data
    if isinstance(fd, LinearFunctionData):
        data["heat_rate"] = float(fd.proportional_term)
        data["heat_rate_base"] = float(fd.constant_term)
        data["heat_rate_incr"] = float(fd.proportional_term)
    elif isinstance(fd, QuadraticFunctionData):
        data["heat_rate_base"] = float(fd.constant_term)
        data["heat_rate"] = float(fd.proportional_term)
        data["heat_rate_incr"] = float(fd.proportional_term)
        data["heat_rate_incr2"] = float(fd.quadratic_term)
        cubic = getattr(fd, "cubic_term", None)
        if cubic is not None:
            data["heat_rate_incr3"] = float(cubic)
    elif isinstance(fd, PiecewiseLinearData):
        initial_input = (
            curve_source.get("initial_input")
            if isinstance(curve_source, Mapping)
            else getattr(curve_source, "initial_input", None)
        )
        if initial_input is not None:
            data["heat_rate_base"] = round(float(initial_input) / 1000, 3)
            data["heat_rate"] = data["heat_rate_base"]
        load_points, slopes = extract_piecewise_segments(fd.points)
        if load_points and slopes:
            load_prop, heat_prop = create_multiband_heat_rate(load_points, slopes)
            data["load_point"] = load_prop
            data["heat_rate_incr"] = heat_prop
    return data


def compute_markup_data(component: Any) -> dict[str, Any]:
    """Compute markup data from component operation cost.

    Extracts markup/VOM cost information from a component's operation cost and
    converts it to a dictionary with mark_up, mark_up_point keys depending on
    the cost curve type.

    Parameters
    ----------
    component : Any
        Component with operation_cost attribute

    Returns
    -------
    dict[str, Any]
        Dictionary with markup data, may contain:
        - mark_up: Linear markup value or multiband markup values
        - mark_up_point: Load points for multiband markup curves
    """
    cost = getattr(component, "operation_cost", None)
    variable = getattr(cost, "variable", None) if cost else None
    if not isinstance(variable, CostCurve):
        return {}
    curve = normalize_value_curve(variable.vom_cost)
    if curve is None or curve.function_data is None:
        return {}
    data: dict[str, Any] = {}
    fd = curve.function_data

    if isinstance(fd, LinearFunctionData | QuadraticFunctionData):
        data["mark_up"] = float(fd.proportional_term)
    elif isinstance(fd, PiecewiseLinearData):
        load_points, slopes = extract_piecewise_segments(fd.points)
        if load_points and slopes:
            point_prop, mark_prop = create_multiband_markup(load_points, slopes)
            data["mark_up_point"] = point_prop
            data["mark_up"] = mark_prop
    return data


def coerce_value(value: Any, default: float = 0.0) -> Any:
    """Coerce value to appropriate type.

    Returns the value as-is if it's a PLEXOSPropertyValue, otherwise converts
    to float or returns the default.

    Parameters
    ----------
    value : Any
        Value to coerce
    default : float, optional
        Default value if value is None, by default 0.0

    Returns
    -------
    Any
        Coerced value
    """
    if value is None:
        return default
    if isinstance(value, PLEXOSPropertyValue):
        return value
    return float(value)


def create_multiband_heat_rate(
    load_points: list[float],
    slopes: list[float],
) -> tuple[PLEXOSPropertyValue, PLEXOSPropertyValue]:
    """Create multiband heat rate properties from piecewise linear segments.

    Converts piecewise linear fuel curve data into PLEXOS multiband format.
    Each segment becomes a band with its corresponding load point and heat rate slope.

    Parameters
    ----------
    load_points : list[float]
        List of load points (x-coordinates) where slope changes occur.
        Expected to be in ascending order and represent the upper limit of each band.
    slopes : list[float]
        List of slope values (incremental heat rates) for each band.
        Length should equal length of load_points.

    Returns
    -------
    tuple[PLEXOSPropertyValue, PLEXOSPropertyValue]
        A tuple of (load_point_property, heat_rate_property) where:
        - load_point_property: PLEXOSPropertyValue with band-indexed load points
        - heat_rate_property: PLEXOSPropertyValue with band-indexed heat rate slopes

    Examples
    --------
    For a piecewise linear fuel curve with 2 segments:
    - Segment 1: 0-60 MW at 12 MBTU/MWh
    - Segment 2: 60-120 MW at 13 MBTU/MWh

    >>> load_pts = [60.0, 120.0]
    >>> rates = [12.0, 13.0]
    >>> load_prop, heat_prop = create_multiband_heat_rate(load_pts, rates)
    >>> load_prop.get_bands()
    [1, 2]
    >>> heat_prop.get_bands()
    [1, 2]
    """
    load_point_property = PLEXOSPropertyValue()
    heat_rate_property = PLEXOSPropertyValue()

    for band_num, (lp, slope) in enumerate(zip(load_points, slopes, strict=False), start=1):
        load_point_property.add_entry(value=float(lp), band=band_num)
        heat_rate_property.add_entry(value=float(slope), band=band_num)
    return load_point_property, heat_rate_property


def create_multiband_markup(
    load_points: list[float],
    slopes: list[float],
) -> tuple[PLEXOSPropertyValue, PLEXOSPropertyValue]:
    """Create multiband markup properties from piecewise linear segments.

    Converts piecewise linear VOM cost curve data into PLEXOS multiband format.
    Each segment becomes a band with its corresponding load point and markup value.

    Parameters
    ----------
    load_points : list[float]
        List of load points (x-coordinates) where cost slope changes occur.
        Expected to be in ascending order and represent the upper limit of each band.
    slopes : list[float]
        List of slope values (incremental VOM costs) for each band.
        Length should equal length of load_points.

    Returns
    -------
    tuple[PLEXOSPropertyValue, PLEXOSPropertyValue]
        A tuple of (markup_point_property, markup_property) where:
        - markup_point_property: PLEXOSPropertyValue with band-indexed load points
        - markup_property: PLEXOSPropertyValue with band-indexed markup values

    Examples
    --------
    For a piecewise linear VOM cost curve with 2 segments:
    - Segment 1: 0-40 MW at $13/MWh
    - Segment 2: 40-80 MW at $16/MWh

    >>> load_pts = [40.0, 80.0]
    >>> costs = [13.0, 16.0]
    >>> point_prop, markup_prop = create_multiband_markup(load_pts, costs)
    >>> point_prop.get_bands()
    [1, 2]
    >>> markup_prop.get_bands()
    [1, 2]
    """
    markup_point_property = PLEXOSPropertyValue()
    markup_property = PLEXOSPropertyValue()

    for band_num, (lp, slope) in enumerate(zip(load_points, slopes, strict=False), start=1):
        markup_point_property.add_entry(value=float(lp), band=band_num)
        markup_property.add_entry(value=float(slope), band=band_num)
    return markup_point_property, markup_property


def ensure_zone_consolidation(context: PluginContext) -> None:
    """Consolidate all per-LoadZone PLEXOSZones into one canonical zone per ISO/RTO.

    After ``apply_rules_to_context`` each source ``LoadZone`` has been translated
    into its own ``PLEXOSZone`` (e.g. "p1", "p2", …).  This step merges them:

    * Zones whose ``category`` was resolved to an ISO/RTO name (e.g. ``'ercot'``)
      are grouped together; one new canonical ``PLEXOSZone`` is created with
      ``name == category`` (e.g. ``PLEXOSZone(name='ercot', category='ercot')``).
    * Zones that fell back to the ``'zones'`` category (no geographic data) are
      folded into the dominant ISO/RTO group for the system.
    * All ``PLEXOSNode → Zone`` memberships that reference the old per-LoadZone
      zones are replaced with memberships to the canonical zone.
    * The individual per-LoadZone zones are removed from the target system.
    """
    target_sys = _target_system(context)
    all_zones = list(target_sys.get_components(PLEXOSZone))
    if not all_zones:
        return

    # Partition zones by category (ISO/RTO name vs generic 'zones' fallback)
    iso_groups: dict[str, list[PLEXOSZone]] = defaultdict(list)
    fallback: list[PLEXOSZone] = []
    for zone in all_zones:
        cat = getattr(zone, "category", None) or "zones"
        if cat == "zones":
            fallback.append(zone)
        else:
            iso_groups[cat].append(zone)

    if not iso_groups:
        logger.warning("Zone consolidation: no ISO/RTO zones detected; skipping.")
        return

    # Fold fallback ('zones') entries into the dominant ISO/RTO group
    dominant_iso = max(iso_groups, key=lambda k: len(iso_groups[k]))
    if fallback:
        logger.info(
            "Zone consolidation: mapping {} 'zones' fallback zone(s) to dominant ISO/RTO '{}'.",
            len(fallback),
            dominant_iso,
        )
        iso_groups[dominant_iso].extend(fallback)

    def _zone_uuid(obj: Any) -> str:
        return str(getattr(obj, "uuid", id(obj)))

    for iso_name, zones in iso_groups.items():
        # Build UUID set for fast membership lookup
        zone_uuids_to_replace: set[str] = {_zone_uuid(z) for z in zones}

        # Create the single canonical zone named after the ISO/RTO
        canonical = PLEXOSZone(name=iso_name, category=iso_name, units=1)
        try:
            target_sys.add_component(canonical)
        except Exception:
            # A zone named iso_name may already be in the system (e.g. a LoadZone
            # happened to be named the same as the ISO/RTO).
            existing = next(
                (z for z in target_sys.get_components(PLEXOSZone) if getattr(z, "name", "") == iso_name),
                None,
            )
            if existing is not None and _zone_uuid(existing) not in zone_uuids_to_replace:
                canonical = existing
            else:
                # Last resort: keep the first zone in the group as-is
                canonical = zones[0]
                zone_uuids_to_replace.discard(_zone_uuid(canonical))

        canonical_uuid = _zone_uuid(canonical)

        # Remap PLEXOSNode→Zone memberships that reference any old zone.
        # Use remove_supplemental_attribute (removes from ALL attached endpoints) so both
        # the node-side and zone-side registrations are cleaned up before we remove the zone.
        for node in list(target_sys.get_components(PLEXOSNode)):
            memberships = list(target_sys.get_supplemental_attributes_with_component(node, PLEXOSMembership))
            for membership in memberships:
                if membership.collection != CollectionEnum.Zone:
                    continue
                child = membership.child_object
                if _zone_uuid(child) not in zone_uuids_to_replace:
                    continue
                # Remove from both endpoints at once, then add canonical membership
                with contextlib.suppress(Exception):
                    target_sys.remove_supplemental_attribute(membership)
                _ensure_membership(context, node, canonical, CollectionEnum.Zone)

        # Remove the individual per-LoadZone zones from the target system.
        # All their memberships have already been cleaned up above.
        for zone in zones:
            if _zone_uuid(zone) == canonical_uuid:
                continue  # don't remove the zone we just designated as canonical
            # Purge any remaining supplemental attributes (e.g. zone-side membership
            # registrations not reached in the node loop above) before removal.
            try:
                remaining_sas = list(target_sys.get_supplemental_attributes_with_component(zone))
                for sa in remaining_sas:
                    with contextlib.suppress(Exception):
                        target_sys.remove_supplemental_attribute(sa)
            except Exception:
                pass
            try:
                target_sys.remove_component(zone, cascade_down=True, force=True)
            except Exception as exc:
                logger.warning(
                    "Zone consolidation: could not remove zone '{}': {}",
                    getattr(zone, "name", "?"),
                    exc,
                )

    logger.info(
        "Zone consolidation complete: {} canonical zone(s) created: {}.",
        len(iso_groups),
        list(iso_groups),
    )
