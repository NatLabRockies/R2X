"""Utility functions for getter operations, particularly multiband conversions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
    EnergyReservoirStorage,
    HydroReservoir,
    HydroTurbine,
    LoadZone,
    PhaseShiftingTransformer,
    TapTransformer,
    Transformer2W,
    TransmissionInterface,
    VariableReserve,
)
from r2x_sienna.units import get_magnitude  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from r2x_core import PluginContext

InputOutputCurveValue = InputOutputCurve[LinearFunctionData | QuadraticFunctionData | PiecewiseLinearData]

_SIENNA_TRANSFORMER_TYPES = (Transformer2W, TapTransformer, PhaseShiftingTransformer)


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
    membership = PLEXOSMembership(
        parent_object=parent_object,
        child_object=child_object,
        collection=collection,
    )
    context.target_system.add_supplemental_attribute(parent_object, membership)


def _bus_name_to_area_and_zone(context: PluginContext) -> dict[str, tuple[str | None, str | None]]:
    """Build a single-pass index: bus_name -> (area_name, zone_name).

    Computed once and cached. Replaces two separate O(n*m) nested loops in
    ensure_region_node_memberships and ensure_node_zone_memberships.
    """
    cached = context._cache.get("bus_name_to_area_and_zone")
    if cached is not None:
        return cached

    result: dict[str, tuple[str | None, str | None]] = {}
    for bus in context.source_system.get_components(ACBus):
        area = getattr(bus, "area", None)
        area_name: str | None = None
        if isinstance(area, Area):
            ext = getattr(area, "ext", None)
            arname = (ext or {}).get("ARNAME") if isinstance(ext, dict) else None
            area_name = str(arname) if arname else area.name
        elif area:
            area_name = str(area)

        load_zone = getattr(bus, "load_zone", None)
        zone_name: str | None = (
            load_zone.name if isinstance(load_zone, LoadZone) else (str(load_zone) if load_zone else None)
        )
        result[bus.name] = (area_name, zone_name)

    context._cache["bus_name_to_area_and_zone"] = result
    return result


def _attach_reservoir_time_series_to_storage(
    context: PluginContext,
    storage_name: str,
    target_storage: Any,
) -> None:
    """Attach time series from source HydroReservoir to translated PLEXOS storage."""
    base_name = storage_name[:-5] if storage_name.endswith(("_head", "_tail")) else storage_name

    source_reservoir = None
    for r in context.source_system.get_components(HydroReservoir):
        if r.name == base_name:
            source_reservoir = r
            break
    if source_reservoir is None:
        for r in context.source_system.get_components(HydroReservoir):
            if base_name in r.name:
                source_reservoir = r
                break
    if source_reservoir is None:
        logger.warning("No source HydroReservoir found for '{}', skipping time series attachment.", base_name)
        return

    if not context.source_system.time_series.has_time_series(source_reservoir):
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
        for t in context.source_system.get_components(HydroTurbine):
            t_base = t.name[: -len("_Turbine")] if t.name.endswith("_Turbine") else t.name
            if t_base == turbine_base:
                limits = getattr(t, "active_power_limits", None)
                if limits is not None:
                    max_val = limits.get("max") if isinstance(limits, dict) else getattr(limits, "max", None)
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

    for ts in context.source_system.list_time_series(source_reservoir):
        ts_name = "natural_inflow" if ts.name == "inflow" else ts.name
        ts_features = getattr(ts, "features", {})
        if not context.target_system.has_time_series(
            target_storage,
            name=ts_name,
            time_series_type=SingleTimeSeries,
            **ts_features,
        ):
            data = np.asarray(ts.data)
            if ts.name == "max_active_power":
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
                initial_timestamp=ts.initial_timestamp,
                resolution=ts.resolution,
            )
            context.target_system.add_time_series(fresh_ts, target_storage, **ts_features)
            logger.success("Attached time series {} to storage {}", ts_name, storage_name)


def ensure_region_node_memberships(context: PluginContext) -> None:
    """Create Region->Node memberships for all regions and their nodes."""
    bus_index = _bus_name_to_area_and_zone(context)
    regions_by_name = {r.name: r for r in context.target_system.get_components(PLEXOSRegion)}

    zone_to_area: dict[str, str] = {}
    for area_name, zone_name in bus_index.values():
        if area_name and zone_name and zone_name not in zone_to_area:
            zone_to_area[zone_name] = area_name

    total_memberships = 0
    for node in context.target_system.get_components(PLEXOSNode):
        area_name, zone_name = bus_index.get(node.name, (None, None))
        if area_name is None and zone_name is not None:
            area_name = zone_to_area.get(zone_name)
        if area_name is None:
            continue
        region = regions_by_name.get(area_name)
        if region is not None:
            _ensure_membership(context, node, region, CollectionEnum.Region)
            total_memberships += 1

    logger.info("Total {} Region-Node memberships created.", total_memberships)


def _extract_base_name(name: str) -> str:
    for suffix in ("_Turbine", "_Reservoir_head", "_Reservoir_tail", "_Reservoir", "_head", "_tail"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def ensure_head_storage_generator_membership(context: PluginContext) -> None:
    """Create HeadStorage memberships between generators and head storages."""
    generators_by_base = {
        _extract_base_name(g.name): g for g in context.target_system.get_components(PLEXOSGenerator)
    }

    total_memberships = 0
    for storage in context.target_system.get_components(PLEXOSStorage):
        if not storage.name.endswith("_head"):
            continue

        _attach_reservoir_time_series_to_storage(context, storage.name, storage)
        if storage.name.endswith("_Reservoir_head"):
            continue

        gen = generators_by_base.get(_extract_base_name(storage.name))
        if gen is not None:
            _ensure_membership(context, gen, storage, CollectionEnum.HeadStorage)
            total_memberships += 1

    logger.info("Total {} HeadStorage-Generator memberships created.", total_memberships)


def ensure_tail_storage_generator_membership(context: PluginContext) -> None:
    """Create TailStorage memberships between generators and tail storages."""
    generators_by_base = {
        _extract_base_name(g.name): g for g in context.target_system.get_components(PLEXOSGenerator)
    }

    total_memberships = 0
    for storage in context.target_system.get_components(PLEXOSStorage):
        if not storage.name.endswith("_tail"):
            continue

        _attach_reservoir_time_series_to_storage(context, storage.name, storage)
        if storage.name.endswith("_Reservoir_tail"):
            continue

        gen = generators_by_base.get(_extract_base_name(storage.name))
        if gen is not None:
            _ensure_membership(context, gen, storage, CollectionEnum.TailStorage)
            total_memberships += 1

    logger.info("Total {} TailStorage-Generator memberships created.", total_memberships)


def ensure_node_zone_memberships(context: PluginContext) -> None:
    """Create Node->Zone memberships for all nodes and their load zones."""
    bus_index = _bus_name_to_area_and_zone(context)
    zones_by_name = {z.name: z for z in context.target_system.get_components(PLEXOSZone)}

    total_memberships = 0
    for node in context.target_system.get_components(PLEXOSNode):
        _, zone_name = bus_index.get(node.name, (None, None))
        if zone_name is None:
            continue
        zone = zones_by_name.get(zone_name)
        if zone is not None:
            _ensure_membership(context, node, zone, CollectionEnum.Zone)
            total_memberships += 1

    logger.info("Total {} Node-Zone memberships created.", total_memberships)


def ensure_generator_node_memberships(context: PluginContext) -> None:
    """Ensure every translated generator has a node membership based on its source bus."""
    from r2x_sienna_to_plexos.getters import _build_generator_display_name_index
    from r2x_sienna_to_plexos.getters_mappings import SOURCE_GENERATOR_TYPES

    source_generators: dict[str, Any] = {}
    for gen_type in SOURCE_GENERATOR_TYPES:
        for gen in context.source_system.get_components(gen_type):
            source_generators[gen.name] = gen

    display_name_index = _build_generator_display_name_index(context)
    target_generators = {g.name: g for g in context.target_system.get_components(PLEXOSGenerator)}
    nodes_by_name = {n.name: n for n in context.target_system.get_components(PLEXOSNode)}

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
    target_generators = {g.name: g for g in context.target_system.get_components(PLEXOSGenerator)}

    total = 0
    for gen_type in SOURCE_GENERATOR_TYPES:
        for source_gen in context.source_system.get_components(gen_type):
            target_name = display_name_index.get(source_gen.name, source_gen.name)
            target_gen = target_generators.get(target_name)
            if target_gen is None:
                continue
            _attach_generator_time_series(context, source_gen.name, target_gen)
            total += 1
    logger.info("Ensured time series for {} generators.", total)


def ensure_battery_node_memberships(context: PluginContext) -> None:
    """Ensure every translated battery has a node membership based on its source bus."""
    target_batteries = {b.name: b for b in context.target_system.get_components(PLEXOSBattery)}
    nodes_by_name = {n.name: n for n in context.target_system.get_components(PLEXOSNode)}

    total_memberships = 0
    for battery in context.source_system.get_components(EnergyReservoirStorage):
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

    reserves_by_name = {r.name: r for r in context.target_system.get_components(PLEXOSReserve)}
    generators_by_name = {g.name: g for g in context.target_system.get_components(PLEXOSGenerator)}
    display_name_index = _build_generator_display_name_index(context)

    reserve_to_generators: dict[str, list[Any]] = {}
    for gen_type in SOURCE_GENERATOR_TYPES:
        for gen in context.source_system.get_components(gen_type):
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
    reserves_by_name = {r.name: r for r in context.target_system.get_components(PLEXOSReserve)}
    batteries_by_name = {b.name: b for b in context.target_system.get_components(PLEXOSBattery)}

    total_memberships = 0
    for source_battery in context.source_system.get_components(EnergyReservoirStorage):
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
        for tf in context.source_system.get_components(tf_type):  # type: ignore[arg-type]
            source_transformers_by_name[tf.name] = tf

    nodes_by_name = {n.name: n for n in context.target_system.get_components(PLEXOSNode)}

    total_memberships = 0
    for transformer in context.target_system.get_components(PLEXOSTransformer):
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


def ensure_interface_line_memberships(context: PluginContext) -> None:
    """Create Interface->Line memberships for all interfaces and their lines."""
    source_interfaces_by_name = {
        i.name: i for i in context.source_system.get_components(TransmissionInterface)
    }
    lines_by_name = {ln.name: ln for ln in context.target_system.get_components(PLEXOSLine)}

    total_memberships = 0
    for interface in context.target_system.get_components(PLEXOSInterface):
        source_intf = source_interfaces_by_name.get(interface.name)
        if source_intf is None:
            continue
        for line_name in getattr(source_intf, "direction_mapping", None) or {}:
            line = lines_by_name.get(line_name)
            if line is not None:
                _ensure_membership(context, interface, line, CollectionEnum.Lines)
                total_memberships += 1

    logger.info("Total {} Interface-Line memberships created.", total_memberships)


def ensure_pumped_hydro_storage_memberships(context: PluginContext) -> None:
    """Create Generator->Storage memberships for pumped hydro generators."""
    storages_by_name = {s.name: s for s in context.target_system.get_components(PLEXOSStorage)}

    total_memberships = 0
    for gen in context.target_system.get_components(PLEXOSGenerator):
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
    variable = getattr(cost, "variable", None) if cost else None
    if not isinstance(variable, FuelCurve):
        return {}
    curve = normalize_value_curve(variable.value_curve)
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
        initial_input = getattr(variable.value_curve, "initial_input", None)
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
