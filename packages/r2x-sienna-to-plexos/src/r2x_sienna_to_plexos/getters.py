"""Getter functions for rules."""

from __future__ import annotations

import json

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
    EnergyReservoirStorage,
    HydroDispatch,
    HydroEnergyReservoir,
    HydroPumpedStorage,
    HydroReservoir,
    HydroTurbine,
    Line,
    LoadZone,
    MonitoredLine,
    PhaseShiftingTransformer,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    StandardLoad,
    SynchronousCondenser,
    TapTransformer,
    ThermalMultiStart,
    ThermalStandard,
    Transformer2W,
    TransmissionInterface,
    TwoTerminalHVDCLine,
    VariableReserve,
)
from r2x_sienna.models.enums import ReserveType
from r2x_sienna.models.getters import (
    get_max_active_power as sienna_get_max_active_power,
)
from r2x_sienna.models.getters import (
    get_ramp_limits as sienna_get_ramp_limits,
)
from r2x_sienna.models.getters import (
    get_value as sienna_get_value,
)
from r2x_sienna.models.named_tuples import FromTo_ToFrom
from r2x_sienna.units import get_magnitude  # type: ignore[import-untyped]

from r2x_core import Err, Ok, PluginContext, Result
from r2x_core.getters import getter
from r2x_sienna_to_plexos.getters_utils import (
    coerce_value,
    compute_heat_rate_data,
    compute_markup_data,
    resolve_base_power,
)

SOURCE_GENERATOR_TYPES = [
    ThermalStandard,
    ThermalMultiStart,
    HydroDispatch,
    HydroPumpedStorage,
    HydroReservoir,
    HydroTurbine,
    HydroEnergyReservoir,
    RenewableDispatch,
    RenewableNonDispatch,
    SynchronousCondenser,
]


# def _build_target_node_name_index(context: PluginContext) -> dict[str, PLEXOSNode]:
#     cached = context._cache.get("target_node_name_index")
#     if cached is not None:
#         return cached
#     result = {n.name: n for n in context.target_system.get_components(PLEXOSNode)}
#     context._cache["target_node_name_index"] = result
#     return result


def _build_target_storage_name_index(context: PluginContext) -> dict[str, Any]:
    cached = context._cache.get("target_storage_name_index")
    if cached is not None:
        return cached
    result = {s.name.lower(): s for s in context.target_system.get_components(PLEXOSStorage)}
    context._cache["target_storage_name_index"] = result
    return result


def _build_source_reserve_name_index(context: PluginContext) -> dict[str, Any]:
    cached = context._cache.get("source_reserve_name_index")
    if cached is not None:
        return cached
    result = {r.name: r for r in context.source_system.get_components(VariableReserve)}
    context._cache["source_reserve_name_index"] = result
    return result


def _build_source_interface_name_index(context: PluginContext) -> dict[str, Any]:
    cached = context._cache.get("source_interface_name_index")
    if cached is not None:
        return cached
    result = {i.name: i for i in context.source_system.get_components(TransmissionInterface)}
    context._cache["source_interface_name_index"] = result
    return result


def _build_target_line_name_index(context: PluginContext) -> dict[str, Any]:
    cached = context._cache.get("target_line_name_index")
    if cached is not None:
        return cached
    result = {ln.name: ln for ln in context.target_system.get_components(PLEXOSLine)}
    context._cache["target_line_name_index"] = result
    return result


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


def _build_area_buses_index(context: PluginContext) -> dict[str, list[Any]]:
    """Map area_name -> list of ACBus components in that area."""
    cached = context._cache.get("area_buses_index")
    if cached is not None:
        return cached
    index: dict[str, list[Any]] = defaultdict(list)
    for bus in context.source_system.get_components(ACBus):
        area_name = getattr(getattr(bus, "area", None), "name", None)
        if area_name:
            index[area_name].append(bus)
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
        index = {}
        for gen_type in SOURCE_GENERATOR_TYPES:
            for gen in context.source_system.get_components(gen_type):
                index[gen.name] = gen
        context._cache[cache_key] = index
    return index.get(gen_name)


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
        for line_type in [Line, MonitoredLine, TwoTerminalHVDCLine]:
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


def _convert_time_value(value: Any) -> float | None:
    if value is None:
        return None
    magnitude = get_magnitude(value)
    return float(magnitude) if magnitude is not None else None


def _get_defaults(category: str, key: str) -> float:
    defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
    with defaults_path.open() as f:
        defaults = json.load(f)
    value = defaults.get("pcm_defaults", {}).get(category, {}).get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# def _lookup_target_zone_by_name(context: PluginContext, zone_name: str) -> Result[Any, ValueError]:
#     """Return the translated zone with the given name."""
#     for zone in context.target_system.get_components(PLEXOSZone):
#         if zone.name == zone_name:
#             return Ok(zone)
#     return Err(ValueError(f"No PLEXOSZone found with name '{zone_name}'"))


# def _lookup_target_node_by_source_area(
#     context: PluginContext, area_name: str
# ) -> Result[PLEXOSNode, ValueError]:
#     """Return the translated node whose source ACBus has matching area name."""
#     for node in context.target_system.get_components(PLEXOSNode):
#         node_name = node.name
#         source_buses = list(
#             context.source_system.get_components(ACBus, filter_func=lambda bus, nn=node_name: bus.name == nn)
#         )

#         for source_bus in source_buses:
#             if hasattr(source_bus, "area"):
#                 bus_area = source_bus.area
#                 if isinstance(bus_area, Area):
#                     if bus_area.name == area_name:
#                         return Ok(node)
#                 elif isinstance(bus_area, str) and bus_area == area_name:
#                     return Ok(node)

#     return Err(ValueError(f"No PLEXOSNode found with source area '{area_name}'"))


# def _lookup_source_generator(context: PluginContext, gen_name: str) -> Any | None:
#     """Find a source generator by name across all Sienna generator types."""
#     for gen_type in SOURCE_GENERATOR_TYPES:
#         generators: list[Any] = list(context.source_system.get_components(gen_type))  # type: ignore[arg-type]
#         for gen in generators:
#             if gen.name == gen_name:
#                 return gen

#     return None


# def _lookup_source_battery(context: PluginContext, battery_name: str) -> Any | None:
#     """Find a source battery by name."""
#     batteries: list[Any] = list(context.source_system.get_components(EnergyReservoirStorage))
#     for battery in batteries:
#         if battery.name == battery_name:
#             return battery
#     return None


# def _lookup_target_node_by_name(context: PluginContext, node_name: str) -> Result[PLEXOSNode, ValueError]:
#     """Return the translated node with the given name."""
#     for node in context.target_system.get_components(PLEXOSNode):
#         if node.name == node_name:
#             return Ok(node)
#     return Err(ValueError(f"No PLEXOSNode found with name '{node_name}'"))


# def _find_source_line(context: PluginContext, line_name: str) -> Any | None:
#     """Find a source line by name across Line, MonitoredLine, and TwoTerminalHVDCLine types."""
#     line_types: list[type[Line | MonitoredLine | TwoTerminalHVDCLine]] = [
#         Line,
#         MonitoredLine,
#         TwoTerminalHVDCLine,
#     ]

#     for line_type in line_types:
#         source_line: Line | MonitoredLine | TwoTerminalHVDCLine | None = next(
#             (ln for ln in context.source_system.get_components(line_type) if ln.name == line_name),
#             None,
#         )
#         if source_line is not None:
#             return source_line

#     return None


# def _find_source_transformer(context: PluginContext, transformer_name: str) -> Any | None:
#     """Find a source transformer by name across Transformer2W, TapTransformer, and PhaseShiftingTransformer types."""
#     transformer_types: list[type[Transformer2W | TapTransformer | PhaseShiftingTransformer]] = [
#         Transformer2W,
#         TapTransformer,
#         PhaseShiftingTransformer,
#     ]

#     for transformer_type in transformer_types:
#         source_transformer: Transformer2W | TapTransformer | PhaseShiftingTransformer | None = next(
#             (
#                 tf
#                 for tf in context.source_system.get_components(transformer_type)
#                 if tf.name == transformer_name
#             ),
#             None,
#         )
#         if source_transformer is not None:
#             return source_transformer

#     return None


def _attach_generator_time_series(
    context: PluginContext,
    generator_name: str,
    target_generator: Any,
) -> None:
    """Attach time series from source generator to translated PLEXOS generator."""
    source_gen: RenewableDispatch | RenewableNonDispatch | HydroReservoir | HydroTurbine | None = None

    source_gen = next(
        (g for g in context.source_system.get_components(RenewableDispatch) if g.name == generator_name),
        None,
    )

    if source_gen is None:
        source_gen = next(
            (
                g
                for g in context.source_system.get_components(RenewableNonDispatch)
                if g.name == generator_name
            ),
            None,
        )

    if source_gen is None:
        source_gen = next(
            (g for g in context.source_system.get_components(HydroReservoir) if g.name == generator_name),
            None,
        )

    if source_gen is None:
        logger.debug("No source generator found for {}", generator_name)
        return

    for metadata in context.source_system.time_series.list_time_series_metadata(source_gen):
        ts_list = context.source_system.list_time_series(source_gen, name=metadata.name, **metadata.features)

        if not ts_list:
            logger.warning("Missing time series {} for generator {}", metadata.name, generator_name)
            continue

        ts = ts_list[0]
        ts_type = ts.__class__
        if not context.target_system.has_time_series(
            target_generator, name=metadata.name, time_series_type=ts_type, **metadata.features
        ):
            context.target_system.add_time_series(ts, target_generator, **metadata.features)
            logger.success("Attached time series {} to generator {}", metadata.name, generator_name)


def _attach_reservoir_time_series_to_storage(
    context: PluginContext,
    storage_name: str,
    target_storage: Any,
) -> None:
    from r2x_sienna.models import HydroReservoir

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
        logger.warning(f"No source HydroReservoir found for '{base_name}', skipping time series attachment.")
        return

    plexos_ts_list: list[Any] | None
    if context.source_system.time_series.has_time_series(source_reservoir):
        plexos_ts_list = []
        for ts in context.source_system.list_time_series(source_reservoir):
            plexos_ts = deepcopy(ts)
            if ts.name in ("inflow", "hydro_budget"):
                plexos_ts.name = "natural_inflow"
            elif ts.name == "outflow":
                plexos_ts.name = "natural_outflow"
                continue
            plexos_ts_list.append(plexos_ts)
    else:
        plexos_ts_list = None

    if plexos_ts_list:
        for ts in plexos_ts_list:
            ts_type = ts.__class__
            if not context.target_system.has_time_series(
                target_storage, name=ts.name, time_series_type=ts_type, **getattr(ts, "features", {})
            ):
                context.target_system.add_time_series(ts, target_storage, **getattr(ts, "features", {}))
                logger.success("Attached time series {} to storage {}", ts.name, storage_name)


def _attach_region_node_load_time_series(
    context: PluginContext,
    region_name: str,
    node: PLEXOSNode,
    region_component: Any | None,
) -> None:
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
                    ts_copy = deepcopy(ts)
                    ts_copy.name = "load"
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


@getter
def get_load_participation_factor(
    source_component: ACBus,
    context: PluginContext,
) -> Result[float, ValueError]:
    """Extract load participation factor from StandardLoads connected to the bus."""
    index = _build_bus_to_standard_loads_index(context)
    node_lpf_total = 0.0
    for load in index.get(source_component.uuid, []):
        if hasattr(load, "ext") and isinstance(load.ext, dict):
            lpf = load.ext.get("MMWG_LPF") or load.ext.get("ReEDS_LPF", 0)
            if isinstance(lpf, int | float):
                node_lpf_total += float(lpf)
    return Ok(node_lpf_total)


@getter
def get_power_or_standard_load(source_component: ACBus, context: PluginContext) -> Result[float, ValueError]:
    """Populate power_load fields with aggregated active power from PowerLoad and StandardLoad."""
    index = _build_bus_to_loads_index(context)
    total_load = 0.0
    for load in index.get(source_component.uuid, []):
        if not hasattr(load, "max_active_power"):
            continue
        magnitude = get_magnitude(load.max_active_power)
        total_load += float(magnitude) if magnitude is not None else 0.0
    return Ok(total_load)


@getter
def is_slack_bus(source_component: ACBus, context: PluginContext) -> Result[int, ValueError]:
    """Populate bustype field based on slack bus status."""

    from r2x_sienna.models.enums import ACBusTypes

    value = 1 if source_component.bustype == ACBusTypes.SLACK else 0
    return Ok(value)


@getter
def get_voltage(source_component: ACBus, context: PluginContext) -> Result[float, ValueError]:
    """Extract AC voltage magnitude from base_voltage Quantity."""
    value = get_magnitude(source_component.base_voltage)
    return Ok(float(value) if value is not None else 0.0)


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
def get_susceptance(
    source_component: Transformer2W | TapTransformer | PhaseShiftingTransformer, context: PluginContext
) -> Result[float, ValueError]:
    """Extract susceptance as float from transformer component's primary_shunt.

    Transformer components (Transformer2W, TapTransformer, PhaseShiftingTransformer)
    have a primary_shunt attribute that may be complex.
    This extracts the imaginary part (susceptance) from the complex value.
    """
    primary_shunt = source_component.primary_shunt

    # If primary_shunt is None, return error to allow rule defaults to apply
    if primary_shunt is None:
        return Err(ValueError("Transformer primary_shunt is None"))

    # Handle complex numbers by extracting imaginary part
    if isinstance(primary_shunt, complex):
        return Ok(float(primary_shunt.imag))

    # Handle Quantity types - magnitude from get_magnitude might be Complex Quantity
    magnitude = get_magnitude(primary_shunt)
    if magnitude is not None:
        # Magnitude might be a Complex number (from pint or Python), extract imaginary part
        if isinstance(magnitude, complex):
            return Ok(float(magnitude.imag))
        # For pint Complex Quantity objects, access .imag to get imaginary part
        if isinstance(magnitude, dict):
            imag_part = magnitude.get("imag")
            if isinstance(imag_part, int | float):
                return Ok(float(imag_part))
            return Err(ValueError(f"Cannot extract imag from primary_shunt magnitude dict: {magnitude}"))
        if isinstance(magnitude, int | float):
            return Ok(float(magnitude))

        imag_part = getattr(magnitude, "imag", None)
        if imag_part is not None:
            return Ok(float(imag_part))

    # Handle plain floats/ints
    if isinstance(primary_shunt, int | float):
        return Ok(float(primary_shunt))

    # If conversion fails, return error to allow defaults
    return Err(ValueError(f"Cannot convert primary_shunt to float: {primary_shunt}"))


@getter
def get_line_min_flow(
    source_component: Line | MonitoredLine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract line min flow as float from source component negative rating.

    Returns the negative of the line's rating magnitude if available,
    otherwise returns 0.0.
    """
    min_flow = getattr(source_component, "rating", None)
    if min_flow is None:
        return Ok(0.0)

    magnitude = get_magnitude(min_flow)
    if magnitude is not None:
        return Ok(float(-abs(magnitude)) * 100)

    if isinstance(min_flow, int | float):
        return Ok(float(-abs(min_flow)) * 100)

    return Ok(0.0)


@getter
def get_line_max_flow(
    source_component: Line | MonitoredLine | TwoTerminalHVDCLine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract line min flow as float from source component negative rating.

    Returns the negative of the line's rating magnitude if available,
    otherwise returns 0.0.
    """
    max_flow = getattr(source_component, "rating", None)
    if max_flow is None:
        return Ok(0.0)

    magnitude = get_magnitude(max_flow)
    if magnitude is not None:
        return Ok(float(abs(magnitude)) * 100)

    if isinstance(max_flow, int | float):
        return Ok(float(abs(max_flow)) * 100)

    return Ok(0.0)


@getter
def get_line_charging_susceptance(
    source_component: Line | MonitoredLine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract line charging susceptance as float from source component.

    Line and MonitoredLine components have a b attribute for shunt susceptance.
    Returns 0.0 if b is None or not available.
    """
    # Access b attribute directly from Line/MonitoredLine component
    line_b = source_component.b

    # If b is None, return 0.0 as safe default
    if line_b is None:
        return Ok(0.0)

    # Handle complex numbers by extracting imaginary part
    if isinstance(line_b, complex):
        return Ok(float(line_b.imag))

    # Handle dict types (e.g., {"from_to": ..., "to_from": ...})
    if isinstance(line_b, dict):
        ft_val = line_b.get("from_to")
        if isinstance(ft_val, int | float):
            return Ok(float(ft_val))
        return Ok(0.0)

    # Handle FromTo_ToFrom types
    if isinstance(line_b, FromTo_ToFrom):
        return Ok(float(line_b.from_to))

    # Handle Quantity types
    magnitude = get_magnitude(line_b)
    if isinstance(magnitude, int | float):
        return Ok(float(magnitude))

    # Handle plain floats/ints
    if isinstance(line_b, int | float):
        return Ok(float(line_b))

    # If we can't convert it, return 0.0 as safe default
    return Ok(0.0)


@getter
def get_storage_initial_level(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the initial storage level for a HydroReservoir."""
    value = getattr(source_component, "initial_level", None)
    if value is not None:
        return Ok(float(value))
    return Ok(0.0)


@getter
def get_storage_max_volume(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the max storage volume for a HydroReservoir."""
    value = getattr(source_component, "storage_level_limits", None)
    if value is None:
        return Ok(0.0)
    if isinstance(value, dict):
        max_val = value.get("max")
        return Ok(float(max_val) if isinstance(max_val, int | float) else 0.0)
    return Ok(float(value.max))


@getter
def get_storage_natural_inflow(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the natural inflow for a HydroReservoir."""
    value = getattr(source_component, "inflow", None)
    if value is not None:
        return Ok(float(value))
    return Ok(0.0)


@getter
def get_heat_rate(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_base(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate_base")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_incr(source_component: object, context: PluginContext) -> Result[Any, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate_incr")
    return Ok(coerce_value(value))


@getter
def get_heat_rate_incr2(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate_incr2")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_incr3(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate_incr3")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_load_point(source_component: object, context: PluginContext) -> Result[Any, ValueError]:
    value = compute_heat_rate_data(source_component).get("load_point")
    if value is None:
        return Err(ValueError("No heat rate load points"))
    return Ok(value)


@getter
def get_min_stable_level(
    source_component: ThermalStandard, context: PluginContext
) -> Result[float, ValueError]:
    limits = getattr(source_component, "active_power_limits", None)
    if not limits:
        return Ok(0.0)
    if isinstance(limits, dict):
        min_val = limits.get("min", 0.0)
        if isinstance(min_val, int | float):
            return Ok(float(max(0.0, min_val)))
        return Ok(0.0)
    try:
        converted = sienna_get_value(limits, source_component)
        min_level = getattr(converted, "min", None)
    except (NotImplementedError, AttributeError, TypeError):
        min_level = getattr(limits, "min", None)
    if min_level is None:
        return Ok(0.0)
    min_level = 0.0 if min_level < 0 else min_level
    return Ok(float(min_level))


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
def get_reserve_max_sharing(
    source_component: VariableReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get reserve max participation factor as a percentage."""
    max_participation_factor = getattr(source_component, "max_participation_factor", 1.0)
    return Ok(max_participation_factor * 100)


@getter
def get_max_capacity(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    value = None
    try:
        value = sienna_get_max_active_power(source_component)
    except (TypeError, NotImplementedError, AttributeError, KeyError):
        value = None

    if value is not None:
        return Ok(max(0.0, float(value)))

    limits = getattr(source_component, "active_power_limits", None)
    if isinstance(limits, dict):
        max_value = limits.get("max")
        if isinstance(max_value, int | float):
            return Ok(max(0.0, float(max_value)))

    rating = getattr(source_component, "rating", None)
    rating_value = get_magnitude(rating)
    if rating_value is not None:
        return Ok(max(0.0, float(rating_value) * resolve_base_power(source_component)))

    return Err(ValueError("active_power_limits or rating missing"))


@getter
def get_load_subtracter(
    source_component: RenewableDispatch | RenewableNonDispatch, context: PluginContext
) -> Result[float, ValueError]:
    """Extract load subtracter (in MW) from the Generator."""
    load_subtracter = getattr(source_component, "load_subtracter", None)
    if load_subtracter is not None:
        magnitude = get_magnitude(load_subtracter)
        if magnitude is not None:
            return Ok(float(magnitude) * resolve_base_power(source_component))
    return Ok(0.0)


@getter
def get_component_rating(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract turbine rating (in MW) from the HydroTurbine."""
    rating = getattr(source_component, "rating", None)
    if rating is not None:
        return Ok(max(0.0, float(rating) * source_component.base_power))
    return Ok(0.0)


@getter
def get_vom_cost(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract variable operating and maintenance cost ($/MWh) from a Generator."""
    try:
        value = (
            getattr(source_component, "operation_cost", None)
            and getattr(source_component.operation_cost, "variable", None)
            and getattr(source_component.operation_cost.variable, "vom_cost", None)
            and getattr(source_component.operation_cost.variable.vom_cost, "function_data", None)
            and getattr(
                source_component.operation_cost.variable.vom_cost.function_data, "constant_term", None
            )
        )
        if value is not None:
            return Ok(float(value))
    except Exception:
        pass
    return Ok(0.0)


@getter
def get_turbine_pump_load(
    source_component: HydroTurbine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract pump load (MW) from the HydroTurbine."""
    pump_load = getattr(source_component, "rating", None)
    if pump_load is not None:
        magnitude = get_magnitude(pump_load)
        if magnitude is not None:
            return Ok(float(magnitude) * resolve_base_power(source_component))
    return Ok(0.0)


@getter
def get_turbine_pump_efficiency(
    source_component: HydroTurbine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract pump efficiency (%) from the HydroTurbine."""
    pump_efficiency = getattr(source_component, "efficiency", None)
    if pump_efficiency is not None and pump_efficiency <= 1.0:
        magnitude = get_magnitude(pump_efficiency)
        if magnitude is None:
            return Ok(float(pump_efficiency) * 100)
        return Ok(float(magnitude) * 100)
    return Ok(100.0)


@getter
def get_thermal_forced_outage_rate(
    source_component: HydroTurbine, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "forced_outage_rate", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("gas-ct", "forced_outage_rate"))


@getter
def get_thermal_maintenance_rate(
    source_component: HydroTurbine, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "maintenance_rate", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("gas-ct", "maintenance_rate"))


@getter
def get_thermal_mean_time_to_repair(
    source_component: HydroTurbine, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "mean_time_to_repair", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("gas-ct", "mean_time_to_repair"))


@getter
def get_turbine_forced_outage_rate(
    source_component: HydroTurbine, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "forced_outage_rate", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("pumped-hydro", "forced_outage_rate"))


@getter
def get_turbine_maintenance_rate(
    source_component: HydroTurbine, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "maintenance_rate", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("pumped-hydro", "maintenance_rate"))


@getter
def get_hydro_mean_time_to_repair(
    source_component: HydroDispatch, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "mean_time_to_repair", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("hydro", "mean_time_to_repair"))


@getter
def get_turbine_mean_time_to_repair(
    source_component: HydroTurbine, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "mean_time_to_repair", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("pumped-hydro", "mean_time_to_repair"))


def _ramp_value_to_float(source_component: object, raw_value: Any) -> float:
    """Convert ramp value to float, applying base power like sienna_get_ramp_limits does."""
    magnitude = get_magnitude(raw_value)
    if magnitude is None and isinstance(raw_value, int | float):
        magnitude = raw_value
    if magnitude is None:
        return 0.0
    return float(magnitude) * resolve_base_power(source_component)


@getter
def get_max_ramp_up(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    try:
        limits = sienna_get_ramp_limits(source_component)
        value = float(limits.up) if limits.up is not None else 0.0
        return Ok(max(0.0, value))
    except (KeyError, TypeError, AttributeError, NotImplementedError):
        pass

    ramp = getattr(source_component, "ramp_limits", None)
    if isinstance(ramp, dict):
        value = _ramp_value_to_float(source_component, ramp.get("up"))
        return Ok(max(0.0, value))
    if ramp is not None:
        value = _ramp_value_to_float(source_component, getattr(ramp, "up", None))
        return Ok(max(0.0, value))

    return Ok(0.0)


@getter
def get_max_ramp_down(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    try:
        limits = sienna_get_ramp_limits(source_component)
        value = float(limits.down) if limits.down is not None else 0.0
        return Ok(max(0.0, value))
    except (KeyError, TypeError, AttributeError, NotImplementedError):
        pass

    ramp = getattr(source_component, "ramp_limits", None)
    if isinstance(ramp, dict):
        value = _ramp_value_to_float(source_component, ramp.get("down"))
        return Ok(max(0.0, value))
    if ramp is not None:
        value = _ramp_value_to_float(source_component, getattr(ramp, "down", None))
        return Ok(max(0.0, value))

    return Ok(0.0)


@getter
def get_min_up_time(source_component: ThermalStandard, context: PluginContext) -> Result[float, ValueError]:
    """Extract minimum up time from time_limits or ext dict."""
    value = _get_time_limit(source_component, "up", "NARIS_Min_Up_Time")
    return Ok(value if value is not None else 0.0)


@getter
def get_min_down_time(source_component: ThermalStandard, context: PluginContext) -> Result[float, ValueError]:
    """Extract minimum down time from time_limits or ext dict."""
    value = _get_time_limit(source_component, "down", "NARIS_Min_Down_Time")
    return Ok(value if value is not None else 0.0)


@getter
def get_initial_generation(
    source_component: ThermalStandard, context: PluginContext
) -> Result[float, ValueError]:
    power = get_magnitude(getattr(source_component, "active_power", None))
    if power is None:
        return Ok(0.0)
    # Active power may be negative in some cases (e.g. EI dataset)
    value = float(power) * resolve_base_power(source_component)
    return Ok(abs(value))


@getter
def get_initial_hours_up(
    source_component: ThermalStandard, context: PluginContext
) -> Result[float, ValueError]:
    hours = _convert_time_value(getattr(source_component, "time_at_status", None)) or 0.0
    return Ok(hours if getattr(source_component, "status", False) else 0.0)


@getter
def get_initial_hours_down(
    source_component: ThermalStandard, context: PluginContext
) -> Result[float, ValueError]:
    hours = _convert_time_value(getattr(source_component, "time_at_status", None)) or 0.0
    return Ok(hours if not getattr(source_component, "status", False) else 0.0)


@getter
def get_running_cost(source_component: ThermalStandard, context: PluginContext) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = get_magnitude(getattr(cost, "fixed", None)) if cost else None
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_start_cost(source_component: ThermalStandard, context: PluginContext) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = get_magnitude(getattr(cost, "start_up", None)) if cost else None
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_shutdown_cost(source_component: ThermalStandard, context: PluginContext) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = get_magnitude(getattr(cost, "shut_down", None)) if cost else None
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_fuel_price(source_component: ThermalStandard, context: PluginContext) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    variable = getattr(cost, "variable", None) if cost else None
    if isinstance(variable, FuelCurve):
        price = get_magnitude(getattr(variable, "fuel_cost", None))
        if price is not None:
            return Ok(float(price))
    return Ok(0.0)


@getter
def get_mark_up(source_component: object, context: PluginContext) -> Result[Any, ValueError]:
    value = compute_markup_data(source_component).get("mark_up")
    return Ok(coerce_value(value))


@getter
def get_mark_up_point(source_component: object, context: PluginContext) -> Result[Any, ValueError]:
    value = compute_markup_data(source_component).get("mark_up_point")
    if value is None:
        return Err(ValueError("No mark-up load points"))
    return Ok(value)


@getter
def get_vom_charge(source_component: object, context: PluginContext) -> Result[Any, ValueError]:
    value = compute_markup_data(source_component).get("mark_up")
    return Ok(coerce_value(value))


@getter
def get_battery_forced_outage_rate(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "forced_outage_rate", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("battery", "forced_outage_rate"))


@getter
def get_battery_maintenance_rate(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "maintenance_rate", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("battery", "maintenance_rate"))


@getter
def get_battery_mean_time_to_repair(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "mean_time_to_repair", None)
    if value is not None:
        return Ok(float(value))
    return Ok(_get_defaults("battery", "mean_time_to_repair"))


@getter
def get_storage_charge_efficiency(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    efficiency = source_component.efficiency
    value = float(efficiency.get("input", 1.0)) if isinstance(efficiency, dict) else float(efficiency.input)
    if value <= 1.0:
        value *= 100
    return Ok(value)


@getter
def get_storage_discharge_efficiency(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    efficiency = source_component.efficiency
    value = float(efficiency.get("output", 1.0)) if isinstance(efficiency, dict) else float(efficiency.output)
    if value <= 1.0:
        value *= 100
    return Ok(value)


@getter
def get_storage_cycles(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "cycle_limits", None)
    if value is None:
        return Ok(0.0)
    return Ok(float(value))


@getter
def get_storage_max_power(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    limits = getattr(source_component, "output_active_power_limits", None)
    if limits is None:
        return Ok(0.0)
    if isinstance(limits, dict):
        max_val = limits.get("max")
        if isinstance(max_val, int | float):
            return Ok(float(max_val))
        return Ok(0.0)
    if getattr(limits, "max", None) is None:
        return Ok(0.0)
    value = get_magnitude(limits.max)
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_storage_capacity(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "storage_capacity", None)
    if value is None:
        return Ok(0.0)
    return Ok(float(value))


@getter
def get_interface_min_flow(
    source_component: TransmissionInterface, context: PluginContext
) -> Result[float, ValueError]:
    """Get min_flow from active_power_flow_limits or default."""
    limits = getattr(source_component, "active_power_flow_limits", None)
    if limits is None:
        return Ok(1e30)
    value = limits.get("min") if isinstance(limits, dict) else getattr(limits, "min", None)
    return Ok(float(value) if isinstance(value, int | float) else 1e30)


@getter
def get_interface_max_flow(
    source_component: TransmissionInterface, context: PluginContext
) -> Result[float, ValueError]:
    """Get max_flow from active_power_flow_limits or default."""
    limits = getattr(source_component, "active_power_flow_limits", None)
    if limits is None:
        return Ok(1e30)
    value = limits.get("max") if isinstance(limits, dict) else getattr(limits, "max", None)
    return Ok(float(value) if isinstance(value, int | float) else 1e30)


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
def get_head_storage_uuid(
    source_component: HydroReservoir,
    context: PluginContext,
) -> Result[str, ValueError]:
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_head")))


@getter
def get_tail_storage_uuid(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_tail")))


@getter
def get_area_units(source_component: Area, context: PluginContext) -> Result[float, ValueError]:
    """Always return 1 for region units."""
    return Ok(1.0)


@getter
def get_area_load(source_component: Area, context: PluginContext) -> Result[float, ValueError]:
    """
    Aggregate static load for the region. Supports both StandardLoad and PowerLoad.
    """
    return Ok(0.0)


@getter
def get_head_storage_name(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    """Return the storage name for the head reservoir (appends _head)."""
    base_name = source_component.name
    if base_name.endswith("_head"):
        base_name = base_name[:-5]
    if base_name.endswith("_tail"):
        base_name = base_name[:-5]
    return Ok(f"{base_name}_head")


@getter
def get_tail_storage_name(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    """Return the storage name for the tail reservoir (appends _tail)."""
    base_name = source_component.name
    if base_name.endswith("_head"):
        base_name = base_name[:-5]
    if base_name.endswith("_tail"):
        base_name = base_name[:-5]
    return Ok(f"{base_name}_tail")


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
    """Return the from-node for a translated transformer."""
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
    """Return the to-node for a translated transformer."""
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
        logger.warning("No PLEXOSStorage found for '{}', skipping membership.", storage_name)
        return Err(ValueError(f"No PLEXOSStorage found for '{storage_name}'"))
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
        logger.warning("No PLEXOSStorage found for '{}', skipping membership.", storage_name)
        return Err(ValueError(f"No PLEXOSStorage found for '{storage_name}'"))
    _attach_reservoir_time_series_to_storage(context, storage_name, target_storage)
    return Ok(target_storage)
