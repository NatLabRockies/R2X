"""Getter functions for rules."""

from __future__ import annotations

import json
import math

# Add this near the top, after imports
from collections import defaultdict
from copy import deepcopy
from importlib.resources import files
from typing import Any

from infrasys.cost_curves import FuelCurve
from loguru import logger
from plexosdb.enums import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_sienna.models import (
    ACBus,
    Area,
    DiscreteControlledACBranch,
    EnergyReservoirStorage,
    HydroDispatch,
    HydroPumpTurbine,
    HydroReservoir,
    HydroTurbine,
    Line,
    LoadZone,
    MonitoredLine,
    PhaseShiftingTransformer,
    PhaseShiftingTransformer3W,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    StandardLoad,
    TapTransformer,
    ThermalMultiStart,
    ThermalStandard,
    Transformer2W,
    Transformer3W,
    TransmissionInterface,
    TwoTerminalGenericHVDCLine,
    TwoTerminalLCCLine,
    TwoTerminalVSCLine,
    VariableReserve,
)
from r2x_sienna.models.enums import ReserveType
from r2x_sienna.models.getters import (
    get_max_active_power as sienna_get_max_active_power,
)
from r2x_sienna.models.named_tuples import FromTo_ToFrom
from r2x_sienna.units import get_magnitude  # type: ignore[import-untyped]

from r2x_core import Err, Ok, PluginContext, Result
from r2x_core.getters import getter
from r2x_sienna_to_plexos.getters_utils import (
    _attach_reservoir_time_series_to_storage,
    coerce_value,
    compute_heat_rate_data,
    compute_markup_data,
    resolve_base_power,
)

from .getters_mappings import (
    GEN_TYPE_STRING_MAP,
    REEDS_COMPONENT_SUBSTRINGS,
    SOURCE_GENERATOR_TYPES,
    SOURCE_LINE_TYPES,
)


def _resolve_generator_category(source_component: Any, context: PluginContext) -> str | None:
    """Resolve category via ext gen_type_string, ReEDS name patterns, or prime_mover mapping."""
    # Get name from ext dict
    ext = getattr(source_component, "ext", None)
    if isinstance(ext, dict):
        gen_type = ext.get("gen_type_string", "").lower().strip()
        if gen_type and gen_type not in ("unknown", "other", "", "unidentified"):
            return GEN_TYPE_STRING_MAP.get(gen_type, gen_type)

    # ReEDS name pattern
    name = (getattr(source_component, "name", "") or "").lower()
    if name.startswith("reeds"):
        for substr, tech in REEDS_COMPONENT_SUBSTRINGS:
            if substr in name:
                return tech

    if name.startswith("zonal2nodal_"):
        suffix = name[len("zonal2nodal_") :]
        defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
        with defaults_path.open() as f:
            _z2n_defaults = json.load(f)
        reeds_cats = sorted(_z2n_defaults.get("reeds_defaults", {}).keys(), key=len, reverse=True)
        for cat in reeds_cats:
            if suffix == cat or suffix.startswith(cat + "_"):
                return cat

    # Nuclear plant name matching — check component name and plant_name from ext
    nuclear_names = _build_nuclear_plant_name_set(context)
    candidate_names = [name]
    if isinstance(ext, dict):
        plant_name = ext.get("plant_name")
        if plant_name:
            candidate_names.append(str(plant_name).lower())
    for candidate in candidate_names:
        if candidate:
            for nuclear_name in nuclear_names:
                if nuclear_name in candidate or candidate in nuclear_name:
                    return "nuclear"

    # Oil plant name matching — check component name and plant_name from ext
    oil_names = _build_oil_plant_name_set(context)
    for candidate in candidate_names:  # candidate_names was already built for nuclear check
        if candidate:
            for oil_name in oil_names:
                if oil_name in candidate or candidate in oil_name:
                    return "oil"

    # Get it from defaults as prime mover mapping if available
    prime_mover = getattr(source_component, "prime_mover_type", None)
    fuel = getattr(source_component, "fuel", None)

    if prime_mover is None and isinstance(ext, dict):
        prime_mover = ext.get("prime_mover")

    pm_fuel_map: dict[str, list[str]] = (
        getattr(getattr(context, "config", None), "prime_mover_mapping", None) or {}
    )

    if prime_mover is not None:
        pm_str = prime_mover.name if hasattr(prime_mover, "name") else str(prime_mover).upper()

        if pm_fuel_map:
            if fuel is not None:
                fuel_str = fuel.name if hasattr(fuel, "name") else str(fuel).upper()
                techs = pm_fuel_map.get(f"{pm_str}_{fuel_str}")
                if techs:
                    return techs[0]
            pm_only = pm_fuel_map.get(f"{pm_str}_")
            if pm_only:
                return pm_only[0]

        defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
        with defaults_path.open() as f:
            defaults_data = json.load(f)
        pm_types: dict[str, str] = defaults_data.get("prime_mover_types", {})
        tech = pm_types.get(pm_str)
        if tech:
            return tech

    return None


def _build_target_storage_name_index(context: PluginContext) -> dict[str, Any]:
    """Build PLEXOSStorage names index, cached."""
    cached = context._cache.get("target_storage_name_index")
    if cached is not None:
        return cached
    result = {s.name.lower(): s for s in context.target_system.get_components(PLEXOSStorage)}
    context._cache["target_storage_name_index"] = result
    return result


def _build_source_reserve_name_index(context: PluginContext) -> dict[str, Any]:
    """Build VariableReserve names index, cached."""
    cached = context._cache.get("source_reserve_name_index")
    if cached is not None:
        return cached
    result = {r.name: r for r in context.source_system.get_components(VariableReserve)}
    context._cache["source_reserve_name_index"] = result
    return result


def _build_source_interface_name_index(context: PluginContext) -> dict[str, Any]:
    """Build TransmissionInterface names index, cached."""
    cached = context._cache.get("source_interface_name_index")
    if cached is not None:
        return cached
    result = {i.name: i for i in context.source_system.get_components(TransmissionInterface)}
    context._cache["source_interface_name_index"] = result
    return result


def _build_target_line_name_index(context: PluginContext) -> dict[str, Any]:
    """Build PLEXOSLine names index, cached."""
    cached = context._cache.get("target_line_name_index")
    if cached is not None:
        return cached
    result = {ln.name: ln for ln in context.target_system.get_components(PLEXOSLine)}
    context._cache["target_line_name_index"] = result
    return result


def _reservoir_base_name(name: str) -> str:
    """Helper to get base name of a reservoir by stripping _head/_tail suffix if present."""
    for suffix in ("_head", "_tail"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _build_generator_service_index(context: PluginContext) -> dict[str, list[Any]]:
    """Map reserve_name -> list of source generators that provide it."""
    cached = context._cache.get("generator_service_index")
    if cached is not None:
        return cached
    index: dict[str, list[Any]] = defaultdict(list)
    for gen_type in SOURCE_GENERATOR_TYPES:
        for gen in context.source_system.get_components(gen_type):
            for service in getattr(gen, "services", None) or []:
                service_name = getattr(service, "name", None)
                if service_name:
                    index[service_name].append(gen)
    result = dict(index)
    context._cache["generator_service_index"] = result
    return result


def _build_battery_service_index(context: PluginContext) -> dict[str, list[Any]]:
    """Map reserve_name -> list of source batteries that provide it."""
    cached = context._cache.get("battery_service_index")
    if cached is not None:
        return cached
    index: dict[str, list[Any]] = defaultdict(list)
    for battery in context.source_system.get_components(EnergyReservoirStorage):
        for service in getattr(battery, "services", None) or []:
            service_name = getattr(service, "name", None)
            if service_name:
                index[service_name].append(battery)
    result = dict(index)
    context._cache["battery_service_index"] = result
    return result


def _build_oil_plant_name_set(context: PluginContext) -> set[str]:
    """Build normalized petroleum plant names set from us_power_plants.json, cached."""
    cached = context._cache.get("oil_plant_name_set")
    if cached is not None:
        return cached
    plants_path = files("r2x_sienna_to_plexos.config") / "us_power_plants.json"
    with plants_path.open() as f:
        plants_data = json.load(f)
    name_set = {
        p["power Plant Name"].lower()
        for p in plants_data
        if isinstance(p.get("Primary Energy Source"), str)
        and p["Primary Energy Source"].lower() == "petroleum"
        and isinstance(p.get("power Plant Name"), str)
    }
    context._cache["oil_plant_name_set"] = name_set
    return name_set


def _build_nuclear_plant_name_set(context: PluginContext) -> set[str]:
    """Build normalized nuclear plant names set from defaults.json and us_power_plants.json, cached."""
    cached = context._cache.get("nuclear_plant_name_set")
    if cached is not None:
        return cached

    # From defaults.json nuclear_plants list
    defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
    with defaults_path.open() as f:
        defaults_data = json.load(f)
    name_set = {p["name"].lower() for p in defaults_data.get("nuclear_plants", [])}

    # From us_power_plants.json filtered by Primary Energy Source == "nuclear"
    plants_path = files("r2x_sienna_to_plexos.config") / "us_power_plants.json"
    with plants_path.open() as f:
        plants_data = json.load(f)
    name_set |= {
        p["power Plant Name"].lower()
        for p in plants_data
        if isinstance(p.get("Primary Energy Source"), str)
        and p["Primary Energy Source"].lower() == "nuclear"
        and isinstance(p.get("power Plant Name"), str)
    }

    context._cache["nuclear_plant_name_set"] = name_set
    return name_set


def _build_area_buses_index(context: PluginContext) -> dict[str, list[Any]]:
    """Map area_name -> list of ACBus components in that area."""
    cached = context._cache.get("area_buses_index")
    if cached is not None:
        return cached
    index: dict[str, list[Any]] = defaultdict(list)
    for bus in context.source_system.get_components(ACBus):
        area = getattr(bus, "area", None)
        if area is None:
            continue
        area_name = getattr(area, "name", None)
        if area_name:
            index[area_name].append(bus)
        arname = (getattr(area, "ext", None) or {}).get("ARNAME")
        if arname and str(arname) != area_name:
            index[str(arname)].append(bus)
    result = dict(index)
    context._cache["area_buses_index"] = result
    return result


def _build_node_name_index(context: PluginContext) -> dict[str, Any]:
    """Build name->PLEXOSNode index once and cache it."""
    cached = context._cache.get("node_name_index")
    if cached is not None:
        return cached
    result = {node.name: node for node in context.target_system.get_components(PLEXOSNode)}
    context._cache["node_name_index"] = result
    return result


def _build_bus_name_index(context: PluginContext) -> dict[str, Any]:
    """Build name->ACBus index once and cache it."""
    cached = context._cache.get("bus_name_index")
    if cached is not None:
        return cached
    result = {bus.name: bus for bus in context.source_system.get_components(ACBus)}
    context._cache["bus_name_index"] = result
    return result


def _build_area_to_node_index(context: PluginContext) -> dict[str, PLEXOSNode]:
    """Build area_name->PLEXOSNode index once and cache it.

    Replaces _lookup_target_node_by_source_area which was O(nodes*buses) per call.
    """
    cached = context._cache.get("area_to_node_index")
    if cached is not None:
        return cached

    bus_name_index = _build_bus_name_index(context)
    node_name_index = _build_node_name_index(context)

    index: dict[str, PLEXOSNode] = {}
    for node_name, node in node_name_index.items():
        source_bus = bus_name_index.get(node_name)
        if source_bus is None:
            continue
        bus_area = getattr(source_bus, "area", None)
        if isinstance(bus_area, Area):
            index[bus_area.name] = node
            arname = (getattr(bus_area, "ext", None) or {}).get("ARNAME")
            if arname:
                index[str(arname)] = node
        elif isinstance(bus_area, str):
            index[bus_area] = node

    context._cache["area_to_node_index"] = index
    return index


def _lookup_target_node_by_name(context: PluginContext, node_name: str) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node with the given name."""
    index = _build_node_name_index(context)
    node = index.get(node_name)
    if node is None:
        return Err(ValueError(f"No PLEXOSNode found with name '{node_name}'"))
    return Ok(node)


def _lookup_target_node_by_source_area(
    context: PluginContext, area_name: str
) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node whose source ACBus has matching area name."""
    index = _build_area_to_node_index(context)
    node = index.get(area_name)
    if node is None:
        return Err(ValueError(f"No PLEXOSNode found with source area '{area_name}'"))
    return Ok(node)


def _lookup_target_zone_by_name(context: PluginContext, zone_name: str) -> Result[Any, ValueError]:
    """Return the translated zone with the given name."""
    cache_key = "zone_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        index = {zone.name: zone for zone in context.target_system.get_components(PLEXOSZone)}
        context._cache[cache_key] = index
    zone = index.get(zone_name)
    if zone is None:
        return Err(ValueError(f"No PLEXOSZone found with name '{zone_name}'"))
    return Ok(zone)


def _lookup_source_generator(context: PluginContext, gen_name: str) -> Any | None:
    """Find a source generator by name across all Sienna generator types."""
    cache_key = "source_generator_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        display_index = _build_generator_display_name_index(context)
        by_orig: dict[str, Any] = {}
        by_display: dict[str, Any] = {}
        for gen_type in SOURCE_GENERATOR_TYPES:
            for gen in context.source_system.get_components(gen_type):
                by_orig[gen.name] = gen
                display_name = display_index.get(gen.name)
                if display_name:
                    by_display.setdefault(display_name, gen)
        # display names overwrite original names so that a HydroReservoir whose
        # Sienna name equals a HydroDispatch's plant_name does not shadow it
        index = {**by_orig, **by_display}
        context._cache[cache_key] = index
    return index.get(gen_name)


def _build_generator_display_name_index(context: PluginContext) -> dict[str, str]:
    """Map each source generator's original name -> final display name.

    Priority:
    1. ext["unit_name"] — used as-is (assumed unique per unit)
    2. ext["plant_name"] — deduplicated with _1, _2, ... suffixes when shared
    3. original component name — same dedup logic as plant_name
    """
    cached = context._cache.get("generator_display_name_index")
    if cached is not None:
        return cached

    result: dict[str, str] = {}
    needs_dedup: list[tuple[str, str]] = []

    for gen_type in SOURCE_GENERATOR_TYPES:
        for gen in context.source_system.get_components(gen_type):
            orig = gen.name
            ext = getattr(gen, "ext", None)
            ext_dict = ext if isinstance(ext, dict) else {}

            unit_name = ext_dict.get("unit_name")
            if unit_name:
                result[orig] = str(unit_name)
            else:
                plant_name = ext_dict.get("plant_name")
                display = str(plant_name) if plant_name else orig
                needs_dedup.append((orig, display))

    groups: dict[str, list[str]] = defaultdict(list)
    for orig, display in needs_dedup:
        groups[display].append(orig)

    for display, orig_names in groups.items():
        if len(orig_names) == 1:
            result[orig_names[0]] = display
        else:
            for i, orig in enumerate(sorted(orig_names), start=1):
                result[orig] = f"{display}_{i}"

    context._cache["generator_display_name_index"] = result
    return result


def _lookup_source_battery(context: PluginContext, battery_name: str) -> Any | None:
    """Find a source battery by name."""
    cache_key = "source_battery_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        index = {b.name: b for b in context.source_system.get_components(EnergyReservoirStorage)}
        context._cache[cache_key] = index
    return index.get(battery_name)


def _find_source_line(context: PluginContext, line_name: str) -> Any | None:
    """Find a source line by name across Line, MonitoredLine, and TwoTerminalHVDCLine types."""
    cache_key = "source_line_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        index = {}
        for line_type in SOURCE_LINE_TYPES:
            for ln in context.source_system.get_components(line_type):
                index[ln.name] = ln
        context._cache[cache_key] = index
    return index.get(line_name)


def _find_source_transformer(context: PluginContext, transformer_name: str) -> Any | None:
    """Find a source transformer by name."""
    cache_key = "source_transformer_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        index = {}
        for tf_type in [Transformer2W, TapTransformer, PhaseShiftingTransformer]:
            for tf in context.source_system.get_components(tf_type):
                index[tf.name] = tf
        context._cache[cache_key] = index
    return index.get(transformer_name)


def _get_time_limit(component: Any, attr: str, ext_key: str) -> float | None:
    """Extract time limit from time_limits attribute or ext dict."""
    time_limits = getattr(component, "time_limits", None)
    if isinstance(time_limits, dict):
        value = time_limits.get(attr)
    else:
        value = getattr(time_limits, attr, None) if time_limits else None

    if value is None:
        ext = getattr(component, "ext", None)
        if ext is not None and isinstance(ext, dict):
            value = ext.get(ext_key)

    return _convert_time_value(value)


def _ramp_value_to_float(source_component: object, raw_value: Any) -> float:
    """Convert ramp value to float, applying base power like sienna_get_ramp_limits does."""
    magnitude = get_magnitude(raw_value)
    if magnitude is None and isinstance(raw_value, int | float):
        magnitude = raw_value
    if magnitude is None:
        return 0.0
    return float(magnitude) * resolve_base_power(source_component)


def _convert_time_value(value: Any) -> float | None:
    """Convert a time value to float hours, handling different formats."""
    if value is None:
        return None
    magnitude = get_magnitude(value)
    return float(magnitude) if magnitude is not None else None


def _get_minmax_value(obj: Any, key: str) -> float | None:
    """Extract min or max value from a MinMax-like object or dict."""
    if obj is None:
        return None
    val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    if val is None:
        return None
    magnitude = get_magnitude(val)
    if magnitude is not None:
        return float(magnitude)
    return float(val) if isinstance(val, int | float) else None


def _get_ramp_default(source_component: object, context: PluginContext) -> float:
    """Return the ramp default from defaults.json max_ramp_up_percentage * max active power (MW/min)."""
    category = _resolve_generator_category(source_component, context) or "gas-cc"
    pct = _get_defaults(category, "max_ramp_up_percentage")
    if math.isclose(pct, 0.0, rel_tol=0.0, abs_tol=1e-6):
        return 0.0
    try:
        max_mw = float(sienna_get_max_active_power(source_component) or 0.0)
    except (TypeError, NotImplementedError, AttributeError, KeyError):
        max_mw = 0.0
    if math.isclose(max_mw, 0.0, rel_tol=0.0, abs_tol=1e-6):
        max_mw = _get_defaults(category, "capacity_MW") or 100.0
    return pct * max_mw


def _get_defaults(category: str, key: str) -> float:
    """Extract a default value from defaults.json for the given category and key."""
    defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
    with defaults_path.open() as f:
        defaults = json.load(f)
    value = defaults.get("reeds_defaults", {}).get(category, {}).get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _attach_generator_time_series(
    context: PluginContext,
    generator_name: str,
    target_generator: Any,
) -> None:
    """Attach time series from source generator to translated PLEXOS generator."""
    source_gen = _lookup_source_generator(context, generator_name)
    if source_gen is None:
        logger.debug("No source generator found for '{}', skipping time series attachment.", generator_name)
        return

    if not context.source_system.time_series.has_time_series(source_gen):
        return

    for metadata in context.source_system.time_series.list_time_series_metadata(source_gen):
        ts_list = context.source_system.list_time_series(source_gen, name=metadata.name, **metadata.features)
        if not ts_list:
            logger.warning("Missing time series {} for generator {}", metadata.name, generator_name)
            continue
        ts = deepcopy(ts_list[0])
        ts_type = ts.__class__
        if not context.target_system.has_time_series(
            target_generator, name=ts.name, time_series_type=ts_type, **metadata.features
        ):
            context.target_system.add_time_series(ts, target_generator, **metadata.features)
            logger.success("Attached time series {} to generator {}", ts.name, generator_name)


def _attach_region_node_load_time_series(
    context: PluginContext,
    region_name: str,
    node: PLEXOSNode,
    region_component: Any | None,
) -> None:
    """Aggregate load time series from all loads in the region and attach to the region's node in PLEXOS."""
    area_buses_index = _build_area_buses_index(context)
    buses_in_region = area_buses_index.get(region_name, [])
    if not buses_in_region:
        logger.debug("No buses found in region {}", region_name)
        return

    bus_loads_index = _build_bus_to_loads_index(context)
    all_loads = [load for bus in buses_in_region for load in bus_loads_index.get(str(bus.uuid), [])]
    if not all_loads:
        logger.debug("No loads found for region {}", region_name)
        return

    aggregated_ts = None
    for load in all_loads:
        if context.source_system.time_series.has_time_series(load):
            for ts in context.source_system.list_time_series(load):
                if ts.name == "max_active_power":
                    load_mw = _get_load_mw(load)
                    ts_copy = deepcopy(ts)
                    ts_copy.name = "load"
                    if load_mw > 0.0:
                        import numpy as np

                        ts_copy.data = np.asarray(ts_copy.data) * load_mw
                    if aggregated_ts is None:
                        aggregated_ts = ts_copy
                    else:
                        aggregated_ts.data += ts_copy.data
                    break

    if aggregated_ts is not None and region_component is not None:
        ts_type = aggregated_ts.__class__
        if not context.target_system.has_time_series(region_component, name="load", time_series_type=ts_type):
            context.target_system.add_time_series(aggregated_ts, region_component)
            logger.debug("Attached aggregated 'load' time series to region {}", region_name)


def _build_bus_to_loads_index(context: PluginContext) -> dict[str, list[Any]]:
    """Build bus_uuid to list of all Load components (StandardLoad and PowerLoad) connected to that bus, cached."""
    cached = context._cache.get("bus_to_loads")
    if cached is not None:
        return cached

    index: dict[str, list[Any]] = defaultdict(list)
    for load in context.source_system.get_components(StandardLoad):
        bus = getattr(load, "bus", None)
        if bus is not None:
            index[str(bus.uuid)].append(load)
    for load in context.source_system.get_components(PowerLoad):
        bus = getattr(load, "bus", None)
        if bus is not None:
            index[str(bus.uuid)].append(load)

    result = dict(index)
    context._cache["bus_to_loads"] = result
    return result


def _build_bus_to_standard_loads_index(context: PluginContext) -> dict[str, list[Any]]:
    """Build bus_uuid to list of StandardLoad components connected to that bus, cached."""
    cached = context._cache.get("bus_to_standard_loads")
    if cached is not None:
        return cached

    index: dict[str, list[Any]] = defaultdict(list)
    for load in context.source_system.get_components(StandardLoad):
        bus = getattr(load, "bus", None)
        if bus is not None:
            index[str(bus.uuid)].append(load)

    result = dict(index)
    context._cache["bus_to_standard_loads"] = result
    return result


def _build_3w_transformer_name_index(context: PluginContext) -> dict[str, Any]:
    """Build Transformer3W / PhaseShiftingTransformer3W names index, cached."""
    cached = context._cache.get("source_3w_transformer_name_index")
    if cached is not None:
        return cached
    index: dict[str, Any] = {}
    for tf_type in [Transformer3W, PhaseShiftingTransformer3W]:
        for tf in context.source_system.get_components(tf_type):
            index[tf.name] = tf
    context._cache["source_3w_transformer_name_index"] = index
    return index


def _find_3w_source_transformer(context: PluginContext, arm_name: str) -> tuple[Any, str] | None:
    """Given an arm name like 'TRANSFORMER_primary', return (transformer3w, arm) or None."""
    for arm in ("primary", "secondary", "tertiary"):
        suffix = f"_{arm}"
        if arm_name.endswith(suffix):
            base_name = arm_name[: -len(suffix)]
            tf = _build_3w_transformer_name_index(context).get(base_name)
            if tf is not None:
                return tf, arm
    return None


def _get_load_mw(load: Any) -> float:
    """Extract MW value from a StandardLoad or PowerLoad for LPF computation."""
    magnitude = get_magnitude(getattr(load, "max_active_power", None))
    if magnitude is not None:
        return float(magnitude) * float(getattr(load, "base_power", 100.0))
    for attr in ("max_constant_active_power", "constant_active_power"):
        val = getattr(load, attr, None)
        if isinstance(val, int | float) and val > 0:
            return float(val) * float(getattr(load, "base_power", 100.0))
    return 0.0


def _compute_total_system_load(context: PluginContext) -> float:
    """Compute total system load in MW by summing max_active_power of all StandardLoad and PowerLoad components."""
    cached = context._cache.get("total_system_load")
    if cached is not None:
        return cached
    total = 0.0
    for load_type in [StandardLoad, PowerLoad]:
        for load in context.source_system.get_components(load_type):
            total += _get_load_mw(load)
    context._cache["total_system_load"] = total
    return total


def _get_system_base_power(context: PluginContext) -> float:
    """Extract system base power from source_system.base_power or default to 100 MVA."""
    value = getattr(getattr(context, "source_system", None), "base_power", None)
    try:
        return float(value) if value is not None else 100.0
    except (TypeError, ValueError):
        return 100.0


def _get_general_default(key: str) -> float:
    """Extract a general default value from defaults.json for the given key."""
    defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
    with defaults_path.open() as f:
        defaults = json.load(f)
    value = defaults.get("general_defaults", {}).get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@getter
def get_component_ext(source_component: object, context: PluginContext) -> Result[dict, ValueError]:
    """Store the Sienna source type name in ext for downstream use (e.g. time series file naming)."""
    return Ok({"sienna_type": type(source_component).__name__})


@getter
def get_region_ext(source_component: Area, context: PluginContext) -> Result[dict, ValueError]:
    """Return ext with sienna_type set to the load type found in this region (StandardLoad or PowerLoad)."""
    area_name = getattr(source_component, "name", "")
    ext_dict = getattr(source_component, "ext", None)
    if isinstance(ext_dict, dict):
        arname = ext_dict.get("ARNAME")
        if arname:
            area_name = str(arname)

    area_buses_index = _build_area_buses_index(context)
    bus_loads_index = _build_bus_to_loads_index(context)
    for bus in area_buses_index.get(area_name, []):
        for load in bus_loads_index.get(str(bus.uuid), []):
            return Ok({"sienna_type": type(load).__name__})

    for _ in context.source_system.get_components(StandardLoad):
        return Ok({"sienna_type": "StandardLoad"})
    for _ in context.source_system.get_components(PowerLoad):
        return Ok({"sienna_type": "PowerLoad"})

    return Ok({"sienna_type": "StandardLoad"})


@getter
def get_availability(source_component: ACBus, context: PluginContext) -> Result[int, ValueError]:
    """Populate available field with units count from ACBus.

    Extracts the units attribute from ACBus and converts to int.
    Returns 1 if units attribute is not present.
    """
    units = getattr(source_component, "units", None)
    if units is None:
        return Ok(1)
    return Ok(int(units))


@getter
def get_voltage_kv(source_component: ACBus, context: PluginContext) -> Result[float, ValueError]:
    """Extract AC voltage magnitude from base_voltage Quantity."""
    value = get_magnitude(source_component.base_voltage)
    return Ok(round(float(value), 1) if value is not None else 0.0)


@getter
def get_ac_voltage_magnitude_pu(source_component: ACBus, context: PluginContext) -> Result[float, ValueError]:
    """Extract AC voltage magnitude in per unit from the source component."""
    value = getattr(source_component, "magnitude", None)
    return Ok(round(float(value), 3) if value is not None else 1.0)


@getter
def get_node_category(source_component: ACBus, context: PluginContext) -> Result[str, ValueError]:
    """Return human-readable region name (ARNAME) from the bus's area ext, falling back to area.name."""
    area = getattr(source_component, "area", None)
    if area is not None:
        ext = getattr(area, "ext", None)
        if isinstance(ext, dict):
            arname = ext.get("ARNAME")
            if arname:
                return Ok(str(arname))
        area_name = getattr(area, "name", None)
        if area_name:
            return Ok(str(area_name))
    return Err(ValueError(f"No area found for ACBus '{source_component.name}'"))


@getter
def get_load_participation_factor(
    source_component: ACBus,
    context: PluginContext,
) -> Result[float, ValueError]:
    """Extract load participation factor from StandardLoads connected to the bus.

    Priority:
    1. ext["MMWG_LPF"] or ext["ReEDS_LPF"] on connected StandardLoads
    2. Computed as node_load_MW / total_system_load_MW
    """

    # format LPF with scientific notation if very small, otherwise round to 4 decimals
    def format_lpf(val: float) -> float:
        """Format the LPF value with scientific notation if it's very small, otherwise round to 4 decimal places."""
        if abs(val) < 1e-4 and val != 0.0:
            return float(f"{val:.4e}")
        return round(val, 4)

    bus_uuid_str = str(source_component.uuid)
    index = _build_bus_to_standard_loads_index(context)
    node_lpf_total = 0.0
    for load in index.get(bus_uuid_str, []):
        if hasattr(load, "ext") and isinstance(load.ext, dict):
            lpf = load.ext.get("MMWG_LPF") or load.ext.get("ReEDS_LPF", 0)
            if isinstance(lpf, int | float):
                node_lpf_total += float(lpf)

    if node_lpf_total > 0.0:
        return Ok(format_lpf(node_lpf_total))

    # compute LPF as total_node_load / total_system_load
    all_loads_index = _build_bus_to_loads_index(context)
    node_load = sum(_get_load_mw(load) for load in all_loads_index.get(bus_uuid_str, []))
    total_load = _compute_total_system_load(context)
    if total_load > 0.0:
        return Ok(format_lpf(node_load / total_load))

    return Ok(0.0)


@getter
def is_slack_bus(source_component: ACBus, context: PluginContext) -> Result[int, ValueError]:
    """Populate bustype field based on slack bus status."""

    from r2x_sienna.models.enums import ACBusTypes

    value = 1 if source_component.bustype == ACBusTypes.SLACK else 0
    return Ok(value)


@getter
def get_area_units(source_component: Area, context: PluginContext) -> Result[float, ValueError]:
    """Always return 1 for region units."""
    return Ok(1.0)


@getter
def get_area_load(source_component: Area, context: PluginContext) -> Result[float, ValueError]:
    """
    This is zero by default, because it is a time series field (datafile).
    Supports both StandardLoad and PowerLoad.
    """
    return Ok(0.0)


@getter
def get_area_name(source_component: Area, context: PluginContext) -> Result[str, ValueError]:
    """Return ARNAME from ext if available, otherwise fall back to the component name."""
    ext = getattr(source_component, "ext", None)
    if isinstance(ext, dict):
        arname = ext.get("ARNAME")
        if arname:
            return Ok(str(arname))
    return Ok(getattr(source_component, "name", ""))


@getter
def get_line_min_flow(
    source_component: Line
    | MonitoredLine
    | DiscreteControlledACBranch
    | TwoTerminalGenericHVDCLine
    | TwoTerminalLCCLine
    | TwoTerminalVSCLine,
    context: PluginContext,
) -> Result[float, ValueError]:
    """Extract line min flow as float from source component negative rating."""
    min_flow = getattr(source_component, "rating", None)
    if min_flow is not None:
        magnitude = get_magnitude(min_flow)
        value = (
            float(magnitude)
            if magnitude is not None
            else float(min_flow)
            if isinstance(min_flow, int | float)
            else None
        )
        if value is not None:
            if abs(value) > 1e6:
                return Ok(-99999.0)
            return Ok(float(-abs(value)) * _get_system_base_power(context))

    val = _get_minmax_value(getattr(source_component, "active_power_limits_to", None), "min")
    if val is not None and abs(val) <= 1e6:
        return Ok(float(val) * _get_system_base_power(context))

    return Ok(-99999.0)


@getter
def get_line_max_flow(
    source_component: Line
    | MonitoredLine
    | DiscreteControlledACBranch
    | TwoTerminalGenericHVDCLine
    | TwoTerminalLCCLine
    | TwoTerminalVSCLine,
    context: PluginContext,
) -> Result[float, ValueError]:
    """Extract line max flow as float from source component rating."""
    max_flow = getattr(source_component, "rating", None)
    if max_flow is not None:
        magnitude = get_magnitude(max_flow)
        value = (
            float(magnitude)
            if magnitude is not None
            else float(max_flow)
            if isinstance(max_flow, int | float)
            else None
        )
        if value is not None:
            if abs(value) > 1e6:
                return Ok(99999.0)
            return Ok(float(abs(value)) * _get_system_base_power(context))

    val = _get_minmax_value(getattr(source_component, "active_power_limits_from", None), "max")
    if val is not None and abs(val) <= 1e6:
        return Ok(float(abs(val)) * _get_system_base_power(context))

    return Ok(99999.0)


@getter
def lines_loss_incremental(
    component: Line | MonitoredLine | TwoTerminalGenericHVDCLine | TwoTerminalLCCLine | TwoTerminalVSCLine,
    context: PluginContext,
) -> Result[float, ValueError]:
    """Return the incremental loss factor for the line. If not specified, return a default value."""
    losses = getattr(component, "loss", None)
    match losses:
        case None:
            return Ok(_get_general_default("ac_line_losses"))
        case int() | float() as val:
            return Ok(float(val))
        case _:
            # InputOutputCurve: extract proportional_term as incremental loss
            function_data = getattr(getattr(losses, "function_data", None), "proportional_term", None)
            return Ok(
                float(function_data) if function_data is not None else _get_general_default("ac_line_losses")
            )


@getter
def lines_wheeling_charge(line: Line | MonitoredLine, context: PluginContext) -> Result[float, ValueError]:
    """Return the wheeling charge for the forward direction (from_region to to_region).
    If not specified on the line, return a default value.
    """
    wc = getattr(line, "wheeling_charge", None)
    if wc is None:
        return Ok(_get_general_default("wheeling_charge"))
    return Ok(float(wc))


@getter
def lines_wheeling_charge_back(
    line: Line | MonitoredLine, context: PluginContext
) -> Result[float, ValueError]:
    """Return the wheeling charge for the reverse direction (to_region to from_region).
    If not specified on the line, return a default value.
    """
    wc_back = getattr(line, "wheeling_charge_back", None)
    if wc_back is None:
        return Ok(_get_general_default("wheeling_charge_back"))
    return Ok(float(wc_back))


@getter
def get_line_charging_susceptance(
    source_component: Line | MonitoredLine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract line charging susceptance as float from source component."""
    match getattr(source_component, "b", None):
        case None:
            return Ok(0.0)
        case int() | float() as val:
            return Ok(float(val))
        case complex() as val:
            return Ok(float(val.imag))
        case FromTo_ToFrom() as val:
            return Ok(float(val.from_to))
        case dict() as val:
            match val.get("from_to"):
                case int() | float() as ft:
                    return Ok(float(ft))
                case _:
                    return Ok(0.0)
        case val:
            match get_magnitude(val):
                case int() | float() as mag:
                    return Ok(float(mag))
                case _:
                    return Ok(0.0)


@getter
def get_vsc_line_resistance(
    source_component: TwoTerminalVSCLine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract line resistance (1/g) from TwoTerminalVSCLine conductance."""
    g = getattr(source_component, "g", None)
    if g is None:
        return Ok(0.0)
    magnitude = get_magnitude(g)
    g_val = float(magnitude) if magnitude is not None else float(g) if isinstance(g, int | float) else None
    if g_val is None or g_val == 0.0:
        return Ok(0.0)
    return Ok(float(1.0 / g_val))


@getter
def get_transformer_susceptance(
    source_component: Transformer2W | TapTransformer | PhaseShiftingTransformer, context: PluginContext
) -> Result[float, ValueError]:
    """Extract susceptance (imaginary part) from transformer component's primary_shunt."""
    match source_component.primary_shunt:
        case None:
            return Err(ValueError("Transformer primary_shunt is None"))
        case complex() as val:
            return Ok(float(val.imag))
        case int() | float() as val:
            return Ok(float(val))
        case val:
            match get_magnitude(val):
                case complex() as mag:
                    return Ok(float(mag.imag))
                case dict() as mag:
                    imag_part = mag.get("imag")
                    if isinstance(imag_part, int | float):
                        return Ok(float(imag_part))
                    return Err(ValueError(f"Cannot extract imag from primary_shunt magnitude dict: {mag}"))
                case int() | float() as mag:
                    return Ok(float(mag))
                case mag:
                    imag_part = getattr(mag, "imag", None)
                    if imag_part is not None:
                        return Ok(float(imag_part))
                    return Err(ValueError(f"Cannot convert primary_shunt to float: {val}"))


@getter
def get_transformer_rating(
    source_component: Transformer2W | TapTransformer | PhaseShiftingTransformer, context: PluginContext
) -> Result[float, ValueError]:
    """Extract transformer rating as float from source component."""
    rating = getattr(source_component, "rating", None)
    if rating is None:
        return Ok(0.0)
    value = float(rating) if isinstance(rating, int | float) else None
    return Ok(round(float(value) * _get_system_base_power(context), 2) if value is not None else 0.0)


@getter
def get_3w_transformer_susceptance(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[float, ValueError]:
    """Read shunt susceptance from the global 'b' attribute of a 3W transformer."""
    b = getattr(source_component, "b", None)
    if b is None:
        return Ok(0.0)
    return Ok(float(b))


@getter
def get_3w_transformer_primary_name(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Return a name for the primary winding based on the source component's name."""
    return Ok(f"{source_component.name}_primary")


@getter
def get_3w_transformer_primary_uuid(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the primary winding based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_primary")))


@getter
def get_3w_transformer_primary_rating(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[float, ValueError]:
    """Extract primary winding rating (MVA) from ext['RATA1'], then rating_primary."""
    ext = getattr(source_component, "ext", None) or {}
    rata = ext.get("RATA1")
    if isinstance(rata, int | float) and rata > 0.0:
        return Ok(round(float(rata), 2))
    rating = getattr(source_component, "rating_primary", None)
    if rating is None:
        return Ok(99999.0)
    val = float(rating)
    return Ok(99999.0 if val >= 1e6 else round(abs(val), 2))


@getter
def get_3w_transformer_secondary_name(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Return a name for the secondary winding based on the source component's name."""
    return Ok(f"{source_component.name}_secondary")


@getter
def get_3w_transformer_secondary_uuid(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the secondary winding based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_secondary")))


@getter
def get_3w_transformer_secondary_rating(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[float, ValueError]:
    """Extract secondary winding rating (MVA) from ext['RATA2'], then rating_secondary."""
    ext = getattr(source_component, "ext", None) or {}
    rata = ext.get("RATA2")
    if isinstance(rata, int | float) and rata > 0.0:
        return Ok(round(float(rata), 2))
    rating = getattr(source_component, "rating_secondary", None)
    if rating is None:
        return Ok(0.0)
    val = float(rating)
    return Ok(99999.0 if val >= 1e6 else round(abs(val), 2))


@getter
def get_3w_transformer_tertiary_name(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Return a name for the tertiary winding based on the source component's name."""
    return Ok(f"{source_component.name}_tertiary")


@getter
def get_3w_transformer_tertiary_uuid(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the tertiary winding based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_tertiary")))


@getter
def get_3w_transformer_tertiary_rating(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[float, ValueError]:
    """Extract tertiary winding rating (MVA) from ext['RATA3'], then rating_tertiary."""
    ext = getattr(source_component, "ext", None) or {}
    rata = ext.get("RATA3")
    if isinstance(rata, int | float) and rata > 0.0:
        return Ok(round(float(rata), 2))
    rating = getattr(source_component, "rating_tertiary", None)
    if rating is None:
        return Ok(0.0)
    val = float(rating)
    return Ok(99999.0 if val >= 1e6 else round(abs(val), 2))


@getter
def get_generator_category(source_component: object, context: PluginContext) -> Result[str, ValueError]:
    """Determine generator category using ReEDS tech names, gen_type_string, or prime_mover/fuel mapping.

    Priority:
    1. ext["gen_type_string"] mapped through _GEN_TYPE_STRING_MAP
    2. ReEDS component name patterns (hydend, hyded, distpv, wind-ofs, etc.)
    3. prime_mover + fuel via context.config.prime_mover_mapping
    4. prime_mover abbreviation via defaults.json prime_mover_types
    5. Err → rule default applies
    """
    category = _resolve_generator_category(source_component, context)
    if category is not None:
        return Ok(category)
    return Err(ValueError("Cannot resolve generator category; rule default will apply"))


@getter
def get_fuel_price(
    source_component: ThermalStandard | ThermalMultiStart, context: PluginContext
) -> Result[float, ValueError]:
    """Extract fuel price in $/GJ from fuel_cost attribute of FuelCurve, if available."""
    cost = getattr(source_component, "operation_cost", None)
    variable = getattr(cost, "variable", None) if cost else None
    if isinstance(variable, FuelCurve):
        price = get_magnitude(getattr(variable, "fuel_cost", None))
        if price is not None:
            return Ok(round(float(price), 2))
    return Ok(0.0)


@getter
def get_max_capacity(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract maximum capacity in MW from rating, active_power_limits, or max_active_power, and return as float."""
    rating = getattr(source_component, "rating", None)
    rating_value = get_magnitude(rating)
    if rating_value is not None:
        return Ok(round(abs(float(rating_value) * resolve_base_power(source_component)), 2))

    limits = getattr(source_component, "active_power_limits", None)
    if isinstance(limits, dict):
        max_value = limits.get("max")
        if isinstance(max_value, int | float):
            return Ok(round(abs(float(max_value)), 2))

    try:
        value = sienna_get_max_active_power(source_component)
    except (TypeError, NotImplementedError, AttributeError, KeyError):
        value = None

    if value is not None:
        return Ok(round(abs(float(value)), 2))

    return Err(ValueError("active_power_limits or rating missing"))


@getter
def get_heat_rate(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate from computed heat rate data, round to 2 decimals, and return as float (units='GJ/MWh')"""
    value = compute_heat_rate_data(source_component).get("heat_rate")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_base(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate_base from computed heat rate data, round to 2 decimals, and return as float (units='GJ/h')"""
    value = compute_heat_rate_data(source_component).get("heat_rate_base")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_incr(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate_incr from computed heat rate data and return as float (units='GJ/MWh')"""
    value = compute_heat_rate_data(source_component).get("heat_rate_incr")
    return Ok(coerce_value(value))


@getter
def get_heat_rate_incr2(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate_incr2 from computed heat rate data, round to 2 decimals, and return as float (units='GJ/MWh^2')"""
    value = compute_heat_rate_data(source_component).get("heat_rate_incr2")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_incr3(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate_incr3 from computed heat rate data, round to 2 decimals, and return as float (units='GJ/MWh^3')"""
    value = compute_heat_rate_data(source_component).get("heat_rate_incr3")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_initial_generation(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract initial generation in MW from active_power attribute, convert using base power, and return as float."""
    power = get_magnitude(getattr(source_component, "active_power", None))
    if power is None:
        return Ok(0.0)
    value = float(power) * resolve_base_power(source_component)
    return Ok(round(abs(value), 2))


@getter
def get_min_up_time(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract minimum up time from time_limits or ext dict."""
    value = _get_time_limit(source_component, "up", "NARIS_Min_Up_Time")
    return Ok(value if value is not None else 0.0)


@getter
def get_min_down_time(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract minimum down time from time_limits or ext dict."""
    value = _get_time_limit(source_component, "down", "NARIS_Min_Down_Time")
    return Ok(value if value is not None else 0.0)


@getter
def get_max_ramp_up(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract maximum ramp up from ramp_limits, convert to MW/min; falls back to category default."""
    ramp = getattr(source_component, "ramp_limits", None)
    if isinstance(ramp, dict):
        value = abs(_ramp_value_to_float(source_component, ramp.get("up")))
    elif ramp is not None:
        value = abs(_ramp_value_to_float(source_component, getattr(ramp, "up", None)))
    else:
        value = 0.0

    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-6):
        value = abs(_get_ramp_default(source_component, context))

    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-6):
        try:
            max_mw = float(sienna_get_max_active_power(source_component) or 0.0)
        except (TypeError, NotImplementedError, AttributeError, KeyError):
            max_mw = 0.0
        value = max_mw / 60.0

    return Ok(max(value, 1e-3))


@getter
def get_max_ramp_down(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract maximum ramp down from ramp_limits, convert to MW/min; falls back to category default."""
    ramp = getattr(source_component, "ramp_limits", None)
    if isinstance(ramp, dict):
        value = abs(_ramp_value_to_float(source_component, ramp.get("down")))
    elif ramp is not None:
        value = abs(_ramp_value_to_float(source_component, getattr(ramp, "down", None)))
    else:
        value = 0.0

    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-6):
        value = abs(_get_ramp_default(source_component, context))

    if math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-6):
        try:
            max_mw = float(sienna_get_max_active_power(source_component) or 0.0)
        except (TypeError, NotImplementedError, AttributeError, KeyError):
            max_mw = 0.0
        value = max_mw / 60.0

    return Ok(max(value, 1e-3))


@getter
def get_generator_name(source_component: object, context: PluginContext) -> Result[str, ValueError]:
    """Return plant_name from ext (with _N suffix for duplicates), otherwise component name."""
    index = _build_generator_display_name_index(context)
    orig_name = getattr(source_component, "name", "")
    return Ok(index.get(orig_name, orig_name))


@getter
def get_generator_min_stable_level(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    """Extract minimum stable level from active_power_limits or compute as percentage of max capacity."""
    min_pu = _get_minmax_value(getattr(source_component, "active_power_limits", None), "min")
    if min_pu is not None:
        value = abs(min_pu) * resolve_base_power(source_component)
        return Ok(round(value, 2))

    category = _resolve_generator_category(source_component, context) or "gas-cc"
    pct = _get_defaults(category, "min_stable_level_percentage")
    try:
        max_mw = float(sienna_get_max_active_power(source_component) or 0.0)
    except (TypeError, NotImplementedError, AttributeError, KeyError):
        max_mw = 0.0
    return Ok(round(pct * max_mw, 2))


@getter
def get_generator_forced_outage_rate(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "forced_outage_rate") if category else 0.0)


@getter
def get_generator_maintenance_rate(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "maintenance_rate") if category else 0.0)


@getter
def get_generator_mean_time_to_repair(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "mean_time_to_repair") if category else 0.0)


@getter
def get_generator_start_cost(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = get_magnitude(getattr(cost, "start_up", None)) if cost else None
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_generator_shutdown_cost(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = get_magnitude(getattr(cost, "shut_down", None)) if cost else None
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_generator_rating(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract turbine rating (in MW) from the HydroTurbine."""
    rating = getattr(source_component, "rating", None)
    if rating is not None:
        return Ok(
            round(
                max(
                    0.0,
                    float(rating) * resolve_base_power(source_component),
                ),
                2,
            )
        )
    return Ok(0.0)


@getter
def get_generator_vom_cost(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract variable operating and maintenance cost ($/MWh) from a Generator."""
    value = compute_markup_data(source_component).get("mark_up")
    if value is not None and float(value) != 0.0:
        return Ok(float(value))
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "vom_cost") if category else 0.0)


@getter
def get_generator_max_energy_day(
    component: HydroDispatch, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return the maximum energy per day for a hydro generator as a PLEXOSPropertyValue with units MW."""
    value = getattr(component, "max_energy_per_day", None)
    if value is None:
        return Ok(0.0)
    return Ok(value)


@getter
def get_generator_fixed_load(
    source_component: HydroDispatch, context: PluginContext
) -> Result[float, ValueError]:
    """Extract fixed load (in MW) from the Generator."""
    value = getattr(source_component, "fixed_load", None)
    if value is None:
        return Ok(0.0)
    return Ok(value)


@getter
def get_generator_load_subtracter(
    source_component: RenewableDispatch | RenewableNonDispatch, context: PluginContext
) -> Result[float, ValueError]:
    """Extract load subtracter (in MW) from the Generator."""
    load_subtracter = getattr(source_component, "load_subtracter", None)
    if load_subtracter is None:
        return Ok(0.0)
    return Ok(0.0)


@getter
def get_turbine_pump_efficiency(
    source_component: HydroTurbine | HydroPumpTurbine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract pump efficiency (%) from the HydroTurbine."""
    pump_efficiency = getattr(source_component, "efficiency", None)
    if pump_efficiency is None:
        return Ok(100.0)

    pump_val = getattr(pump_efficiency, "pump", None)
    if pump_val is not None:
        magnitude = get_magnitude(pump_val)
        value = (
            float(magnitude)
            if isinstance(magnitude, int | float)
            else float(pump_val)
            if isinstance(pump_val, int | float)
            else None
        )
        if value is not None:
            return Ok(round(value * 100 if value <= 1.0 else value, 2))

    if isinstance(pump_efficiency, int | float):
        return Ok(
            round(float(pump_efficiency) * 100 if pump_efficiency <= 1.0 else float(pump_efficiency), 2)
        )

    return Ok(100.0)


@getter
def get_turbine_pump_load(
    source_component: HydroTurbine | HydroPumpTurbine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract pump load (MW) from the HydroTurbine."""
    pump_load = getattr(source_component, "rating", None)
    if pump_load is not None:
        magnitude = get_magnitude(pump_load)
        if magnitude is not None:
            return Ok(
                round(
                    float(magnitude) * resolve_base_power(source_component),
                    2,
                )
            )
    return Ok(0.0)


@getter
def get_head_storage_name(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    """Return the storage name for the head reservoir (appends _head), using plant_name from ext if available."""
    ext = getattr(source_component, "ext", None)
    base = None
    if isinstance(ext, dict):
        plant_name = ext.get("plant_name")
        if plant_name:
            base = str(plant_name)
    if base is None:
        base = _reservoir_base_name(source_component.name)
    return Ok(f"{base}_head")


@getter
def get_head_storage_uuid(
    source_component: HydroReservoir,
    context: PluginContext,
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the head reservoir storage based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_head")))


@getter
def get_tail_storage_name(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    """Return the storage name for the tail reservoir (appends _tail), using plant_name from ext if available."""
    ext = getattr(source_component, "ext", None)
    base = None
    if isinstance(ext, dict):
        plant_name = ext.get("plant_name")
        if plant_name:
            base = str(plant_name)
    if base is None:
        base = _reservoir_base_name(source_component.name)
    return Ok(f"{base}_tail")


@getter
def get_tail_storage_uuid(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the tail reservoir storage based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_tail")))


@getter
def get_storage_initial_volume(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the initial storage volume for a storage type."""
    value = getattr(source_component, "initial_volume", None)
    if value is not None and float(value) != 0.0:
        return Ok(round(float(value) / 1000.0, 2))
    storage_limits = getattr(source_component, "storage_level_limits", None)
    if storage_limits is None:
        return Ok(50.0)
    if isinstance(storage_limits, dict):
        max_val = storage_limits.get("max")
        max_volume = float(max_val) if isinstance(max_val, int | float) and max_val else 100.0
    else:
        max_val = getattr(storage_limits, "max", None)
        max_volume = float(max_val) if isinstance(max_val, int | float) and max_val else 100.0
    return Ok(round(max_volume * 0.5 / 1000.0, 2))


@getter
def get_storage_max_volume(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the max storage volume for a storage type."""
    value = getattr(source_component, "storage_level_limits", None)
    if value is None:
        return Ok(100.0)
    if isinstance(value, dict):
        max_val = value.get("max")
        if isinstance(max_val, int | float) and max_val:
            return Ok(round(float(max_val) / 1000.0, 2))
        return Ok(100.0)
    max_val = getattr(value, "max", None)
    if isinstance(max_val, int | float) and max_val:
        return Ok(round(float(max_val) / 1000.0, 2))
    return Ok(100.0)


@getter
def get_storage_natural_inflow(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the natural inflow for a storage type."""
    value = getattr(source_component, "inflow", None)
    if value is not None:
        return Ok(float(value))
    return Ok(0.0)


@getter
def get_battery_capacity(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract battery capacity in MWh from storage_capacity attribute, convert using base power, and return as float."""
    value = getattr(source_component, "storage_capacity", None)
    if value is not None and float(value) != 0.0:
        return Ok(round(float(value) * resolve_base_power(source_component), 2))
    return Ok(round(_get_defaults("battery", "average_capacity_MW"), 2))


@getter
def get_battery_charge_efficiency(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract battery charge efficiency from efficiency attribute, convert to percentage if necessary, and return as float."""
    efficiency = source_component.efficiency
    value = float(efficiency.get("input", 0.0)) if isinstance(efficiency, dict) else float(efficiency.input)
    if value != 0.0:
        return Ok(round(value * 100 if value <= 1.0 else value, 2))
    return Ok(round(_get_defaults("battery", "charge_efficiency") * 100, 2))


@getter
def get_battery_discharge_efficiency(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract battery discharge efficiency from efficiency attribute, convert to percentage if necessary, and return as float."""
    efficiency = source_component.efficiency
    value = float(efficiency.get("output", 0.0)) if isinstance(efficiency, dict) else float(efficiency.output)
    if value != 0.0:
        return Ok(round(value * 100 if value <= 1.0 else value, 2))
    return Ok(round(_get_defaults("battery", "discharge_efficiency") * 100, 2))


@getter
def get_battery_initial_soc(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract initial state of charge from initial_storage_capacity_level attribute, convert to percentage if necessary, and return as float."""
    value = getattr(source_component, "initial_storage_capacity_level", None)
    if value is None:
        return Ok(_get_defaults("battery", "initial_soc") * 100)
    return Ok(float(value) * 100)


@getter
def get_battery_min_soc(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract minimum state of charge from storage_level_limits attribute, convert to percentage if necessary, and return as float."""
    limits = getattr(source_component, "storage_level_limits", None)
    if limits is None:
        return Ok(_get_defaults("battery", "min_soc") * 100)
    if isinstance(limits, dict):
        min_val = limits.get("min")
        if isinstance(min_val, int | float):
            return Ok(float(min_val) * 100)
        return Ok(_get_defaults("battery", "min_soc") * 100)
    return Ok(float(limits.min) * 100)


@getter
def get_battery_max_soc(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract maximum state of charge from storage_level_limits attribute, convert to percentage if necessary, and return as float."""
    limits = getattr(source_component, "storage_level_limits", None)
    if limits is None:
        return Ok(_get_defaults("battery", "max_soc") * 100)
    if isinstance(limits, dict):
        max_val = limits.get("max")
        if isinstance(max_val, int | float):
            return Ok(float(max_val) * 100)
        return Ok(_get_defaults("battery", "max_soc") * 100)
    return Ok(float(limits.max) * 100)


@getter
def get_battery_cycles(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "cycle_limits", None)
    if value is None:
        return Ok(10000.0)
    return Ok(float(value))


@getter
def get_battery_max_power(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    rating = getattr(source_component, "rating", None)
    rating_value = get_magnitude(rating)
    if rating_value is not None:
        return Ok(round(float(rating_value) * resolve_base_power(source_component), 2))

    limits = getattr(source_component, "output_active_power_limits", None)
    if limits is None:
        return Ok(0.0)
    if isinstance(limits, dict):
        max_val = limits.get("max")
        if isinstance(max_val, int | float):
            return Ok(float(max_val) * resolve_base_power(source_component))
        return Ok(0.0)
    if getattr(limits, "max", None) is None:
        return Ok(0.0)
    value = get_magnitude(limits.max)
    return Ok(float(value) * resolve_base_power(source_component) if value is not None else 0.0)


@getter
def get_reserve_timeframe(
    source_component: VariableReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get reserve timeframe in seconds."""
    time_frame = getattr(source_component, "time_frame", 0.0)
    return Ok(time_frame * 60)


@getter
def get_reserve_duration(
    source_component: VariableReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get reserve sustained time in seconds."""
    sustained_time = getattr(source_component, "sustained_time", 0.0)
    return Ok(sustained_time)


@getter
def get_reserve_min_provision(
    source_component: VariableReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get reserve requirement."""
    requirement = getattr(source_component, "requirement", 0.0)
    return Ok(requirement)


@getter
def get_reserve_type(source_component: VariableReserve, context: PluginContext) -> Result[int, ValueError]:
    """Get PLEXOS reserve type from Sienna ReserveType."""
    reserve_type_mapping = {
        ReserveType.SPINNING: 1,
        ReserveType.FLEXIBILITY: 2,
        ReserveType.REGULATION: 3,
    }
    plexos_type = reserve_type_mapping.get(source_component.reserve_type, 1)
    return Ok(plexos_type)


@getter
def get_reserve_vors(source_component: VariableReserve, context: PluginContext) -> Result[float, ValueError]:
    """Get reserve VORS."""
    vors = getattr(source_component, "vors", -1.0)
    return Ok(vors)


@getter
def get_interface_min_flow(
    source_component: TransmissionInterface, context: PluginContext
) -> Result[float, ValueError]:
    """Get min_flow from active_power_flow_limits or default."""
    limits = getattr(source_component, "active_power_flow_limits", None)
    if limits is None:
        return Ok(-99999.9)
    value = limits.get("min") if isinstance(limits, dict) else getattr(limits, "min", None)
    return Ok(float(value) if isinstance(value, int | float) else -99999.9)


@getter
def get_interface_max_flow(
    source_component: TransmissionInterface, context: PluginContext
) -> Result[float, ValueError]:
    """Get max_flow from active_power_flow_limits or default."""
    limits = getattr(source_component, "active_power_flow_limits", None)
    if limits is None:
        return Ok(99999.9)
    value = limits.get("max") if isinstance(limits, dict) else getattr(limits, "max", None)
    return Ok(float(value) if isinstance(value, int | float) else 99999.9)


@getter
def membership_parent_component(component: object, context: PluginContext) -> Result[Any, ValueError]:
    """Return the component itself for membership parent/child fields."""
    return Ok(component)


@getter
def membership_collection_nodes(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Nodes collection enum."""
    return Ok(CollectionEnum.Nodes)


@getter
def membership_collection_lines(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Lines collection enum."""
    return Ok(CollectionEnum.Lines)


@getter
def membership_collection_generators(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Generators collection enum."""
    return Ok(CollectionEnum.Generators)


@getter
def membership_collection_batteries(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Batteries collection enum."""
    return Ok(CollectionEnum.Batteries)


@getter
def membership_collection_region(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Region collection enum."""
    return Ok(CollectionEnum.Region)


@getter
def membership_collection_node_from(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the NodeFrom collection enum."""
    return Ok(CollectionEnum.NodeFrom)


@getter
def membership_collection_node_to(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the NodeTo collection enum."""
    return Ok(CollectionEnum.NodeTo)


@getter
def membership_collection_zone(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Zone collection enum."""
    return Ok(CollectionEnum.Zone)


@getter
def membership_collection_head_storage(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Head Storage collection enum."""
    return Ok(CollectionEnum.HeadStorage)


@getter
def membership_collection_tail_storage(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Tail Storage collection enum."""
    return Ok(CollectionEnum.TailStorage)


@getter
def membership_node_child_zone(node: PLEXOSNode, context: PluginContext) -> Result[Any, ValueError]:
    bus_index = _build_bus_name_index(context)
    source_bus = bus_index.get(node.name)
    if source_bus is None:
        return Err(ValueError(f"No source ACBus found for node '{node.name}'"))
    load_zone = getattr(source_bus, "load_zone", None)
    if load_zone is None:
        return Err(ValueError(f"Source bus '{source_bus.name}' has no load_zone"))
    zone_name = load_zone.name if isinstance(load_zone, LoadZone) else str(load_zone)
    return _lookup_target_zone_by_name(context, zone_name)


@getter
def membership_reserve_child_generator(
    reserve: VariableReserve, context: PluginContext
) -> Result[PLEXOSGenerator, ValueError]:
    reserve_index = _build_source_reserve_name_index(context)
    service_index = _build_generator_service_index(context)

    reserve_name = getattr(reserve, "name", "")
    source_reserve = reserve_index.get(reserve_name)
    if source_reserve is None:
        return Err(ValueError(f"Source reserve '{reserve_name}' not found"))

    for gen in service_index.get(source_reserve.name, []):
        target_device = context.target_system.get_component_by_uuid(gen.uuid)
        if target_device:
            return Ok(target_device)

    return Err(ValueError(f"No contributing generators found for reserve '{reserve_name}'"))


@getter
def membership_reserve_child_battery(
    reserve: VariableReserve, context: PluginContext
) -> Result[PLEXOSBattery, ValueError]:
    reserve_index = _build_source_reserve_name_index(context)
    battery_service_index = _build_battery_service_index(context)

    reserve_name = getattr(reserve, "name", "")
    source_reserve = reserve_index.get(reserve_name)
    if source_reserve is None:
        logger.warning("Source reserve '{}' not found", reserve_name)
        return Err(ValueError(f"Source reserve '{reserve_name}' not found"))

    for battery in battery_service_index.get(source_reserve.name, []):
        target_device = context.target_system.get_component_by_uuid(battery.uuid)
        if target_device and isinstance(target_device, PLEXOSBattery):
            return Ok(target_device)

    logger.warning("No contributing batteries found for reserve '{}'", reserve_name)
    return Err(ValueError(f"No contributing batteries found for reserve '{reserve_name}'"))


@getter
def membership_component_child_node(
    component: object, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Resolve a component's bus to the translated node.

    Works for both PLEXOSGenerator and PLEXOSBattery components.
    Also attaches time series from source to target component.
    """
    comp_name = getattr(component, "name", "")

    if isinstance(component, PLEXOSGenerator):
        source_comp = _lookup_source_generator(context, comp_name)
        comp_type = "generator"
        _attach_generator_time_series(context, comp_name, component)
    elif isinstance(component, PLEXOSBattery):
        source_comp = _lookup_source_battery(context, comp_name)
        comp_type = "battery"
    else:
        source_comp = _lookup_source_generator(context, comp_name)
        if source_comp is None:
            source_comp = _lookup_source_battery(context, comp_name)
            comp_type = "battery" if source_comp is not None else "component"
        else:
            comp_type = "generator"
            _attach_generator_time_series(context, comp_name, component)

    if source_comp is None:
        return Err(ValueError(f"No source {comp_type} found for '{comp_name}'"))

    bus = getattr(source_comp, "bus", None)
    if bus is None or not getattr(bus, "name", None):
        return Err(ValueError(f"Source {comp_type} '{source_comp.name}' is missing bus data"))

    return _lookup_target_node_by_name(context, bus.name)


@getter
def membership_interface_child_line(
    interface: object, context: PluginContext
) -> Result[PLEXOSLine, ValueError]:
    interface_index = _build_source_interface_name_index(context)
    line_index = _build_target_line_name_index(context)

    interface_name = getattr(interface, "name", "")
    source_interface = interface_index.get(interface_name)
    if source_interface is None:
        return Err(ValueError(f"No source TransmissionInterface found for '{interface_name}'"))

    lines = getattr(source_interface, "lines", None)
    if not lines:
        return Err(ValueError(f"TransmissionInterface '{interface_name}' has no lines"))

    first_line = lines[0]
    line_name = first_line.name if hasattr(first_line, "name") else str(first_line)
    target_line = line_index.get(line_name)
    if target_line is None:
        return Err(ValueError(f"No PLEXOSLine found for line '{line_name}'"))
    return Ok(target_line)


@getter
def membership_region_parent_node(region: object, context: PluginContext) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node for membership parent links and attach load time series."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node_by_source_area(context, region_name)
    match result:
        case Ok(node):
            try:
                _attach_region_node_load_time_series(context, region_name, node, region_component=region)
            except Exception as exc:
                logger.warning("Failed to attach load time series for region {}: {}", region_name, exc)
            return result
        case Err(error):
            return Err(ValueError(str(error)) if not isinstance(error, ValueError) else error)
        case _:
            return Err(ValueError(f"Unexpected result type for region '{region_name}'"))


@getter
def membership_region_child_node(region: object, context: PluginContext) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node that matches the region name and attach load time series."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node_by_source_area(context, region_name)
    match result:
        case Ok(node):
            try:
                _attach_region_node_load_time_series(context, region_name, node, region_component=region)
            except Exception as exc:
                logger.warning("Failed to attach load time series for region {}: {}", region_name, exc)
            return result
        case Err(error):
            return Err(ValueError(str(error)) if not isinstance(error, ValueError) else error)
        case _:
            return Err(ValueError(f"Unexpected result type for region '{region_name}'"))


@getter
def membership_line_from_parent_node(
    line: PLEXOSLine, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Return the from-node for a translated line."""
    source_line = _find_source_line(context, line.name)

    if source_line is None:
        return Err(ValueError(f"Source line '{line.name}' not found"))

    if not hasattr(source_line, "arc"):
        return Err(ValueError(f"Source line '{line.name}' missing arc data"))

    from_bus = source_line.arc.from_to
    from_bus_name = from_bus.name if hasattr(from_bus, "name") else str(from_bus)

    return _lookup_target_node_by_name(context, from_bus_name)


@getter
def membership_line_to_parent_node(
    line: PLEXOSLine, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Return the to-node for a translated line."""
    source_line = _find_source_line(context, line.name)

    if source_line is None:
        return Err(ValueError(f"Source line '{line.name}' not found"))

    if not hasattr(source_line, "arc"):
        return Err(ValueError(f"Source line '{line.name}' missing arc data"))

    to_bus = source_line.arc.to_from
    to_bus_name = to_bus.name if hasattr(to_bus, "name") else str(to_bus)

    return _lookup_target_node_by_name(context, to_bus_name)


@getter
def membership_transformer_from_parent_node(
    transformer: PLEXOSTransformer, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Return the from-node for a translated transformer (2W and 3W arm transformers)."""
    result_3w = _find_3w_source_transformer(context, transformer.name)
    if result_3w is not None:
        source_3w, arm = result_3w
        arc = getattr(source_3w, f"{arm}_star_arc", None)
        if arc is None:
            return Err(ValueError(f"No '{arm}_star_arc' on source transformer '{source_3w.name}'"))
        from_bus = arc.from_to
        from_bus_name = from_bus.name if hasattr(from_bus, "name") else str(from_bus)
        return _lookup_target_node_by_name(context, from_bus_name)

    source_transformer = _find_source_transformer(context, transformer.name)
    if source_transformer is None:
        return Err(ValueError(f"Source transformer '{transformer.name}' not found"))
    if not hasattr(source_transformer, "arc"):
        return Err(ValueError(f"Source transformer '{transformer.name}' missing arc data"))
    from_bus = source_transformer.arc.from_to
    from_bus_name = from_bus.name if hasattr(from_bus, "name") else str(from_bus)
    return _lookup_target_node_by_name(context, from_bus_name)


@getter
def membership_transformer_to_parent_node(
    transformer: PLEXOSTransformer, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Return the to-node for a translated transformer (2W arms go to star_bus, 2W go to arc.to_from)."""
    result_3w = _find_3w_source_transformer(context, transformer.name)
    if result_3w is not None:
        source_3w, _ = result_3w
        star_bus = source_3w.star_bus
        star_bus_name = star_bus.name if hasattr(star_bus, "name") else str(star_bus)
        return _lookup_target_node_by_name(context, star_bus_name)

    source_transformer = _find_source_transformer(context, transformer.name)
    if source_transformer is None:
        return Err(ValueError(f"Source transformer '{transformer.name}' not found"))
    if not hasattr(source_transformer, "arc"):
        return Err(ValueError(f"Source transformer '{transformer.name}' missing arc data"))
    to_bus = source_transformer.arc.to_from
    to_bus_name = to_bus.name if hasattr(to_bus, "name") else str(to_bus)
    return _lookup_target_node_by_name(context, to_bus_name)


@getter
def membership_head_storage_generator(
    generator: HydroTurbine, context: PluginContext
) -> Result[Any, ValueError]:
    storage_index = _build_target_storage_name_index(context)
    gen_name = getattr(generator, "name", "")
    storage_name = (
        gen_name.replace("_Turbine", "_Reservoir_head")
        if gen_name.endswith("_Turbine")
        else f"{gen_name}_Reservoir_head"
    )
    target_storage = storage_index.get(storage_name.lower())
    if target_storage is None:
        storage_name = f"{gen_name}_head"
        target_storage = storage_index.get(storage_name.lower())

    if target_storage is None:
        logger.warning("No PLEXOSStorage found for '{}', skipping membership.", gen_name)
        return Err(ValueError(f"No PLEXOSStorage found for '{gen_name}'"))
    _attach_reservoir_time_series_to_storage(context, storage_name, target_storage)
    return Ok(target_storage)


@getter
def membership_tail_storage_generator(
    generator: HydroTurbine, context: PluginContext
) -> Result[Any, ValueError]:
    storage_index = _build_target_storage_name_index(context)
    gen_name = getattr(generator, "name", "")
    storage_name = (
        gen_name.replace("_Turbine", "_Reservoir_tail")
        if gen_name.endswith("_Turbine")
        else f"{gen_name}_Reservoir_tail"
    )
    target_storage = storage_index.get(storage_name.lower())
    if target_storage is None:
        storage_name = f"{gen_name}_tail"
        target_storage = storage_index.get(storage_name.lower())

    if target_storage is None:
        logger.warning("No PLEXOSStorage found for '{}', skipping membership.", gen_name)
        return Err(ValueError(f"No PLEXOSStorage found for '{gen_name}'"))
    _attach_reservoir_time_series_to_storage(context, storage_name, target_storage)
    return Ok(target_storage)


@getter
def membership_line_parent_interface(line: PLEXOSLine, context: PluginContext) -> Result[Any, ValueError]:
    """Return the parent PLEXOSInterface for a translated line by matching its name against source TransmissionInterface direction_mapping keys."""
    from r2x_plexos.models import PLEXOSInterface

    line_name = getattr(line, "name", "")
    line_to_iface = context._cache.get("line_to_interface_name_index")
    if line_to_iface is None:
        line_to_iface = {}
        for iface in context.source_system.get_components(TransmissionInterface):
            for mapped_name in getattr(iface, "direction_mapping", None) or {}:
                line_to_iface[mapped_name] = iface.name
        context._cache["line_to_interface_name_index"] = line_to_iface

    interface_name = line_to_iface.get(line_name)
    if interface_name is None:
        return Err(
            ValueError(f"No TransmissionInterface found containing line '{line_name}' in direction_mapping")
        )

    target_iface_index = context._cache.get("target_interface_name_index")
    if target_iface_index is None:
        target_iface_index = {
            iface.name: iface for iface in context.target_system.get_components(PLEXOSInterface)
        }
        context._cache["target_interface_name_index"] = target_iface_index

    target_iface = target_iface_index.get(interface_name)
    if target_iface is None:
        return Err(ValueError(f"No PLEXOSInterface found with name '{interface_name}'"))

    return Ok(target_iface)
