"""Getter functions for rules."""

from __future__ import annotations

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

from r2x_core import Err, Ok, Result, TranslationContext
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


@getter
def get_load_participation_factor(
    context: TranslationContext, source_component: ACBus
) -> Result[float, ValueError]:
    """Extract load participation factor from StandardLoads connected to the bus.

    Aggregates the 'MMWG_LPF' or 'ReEDS_LPF' values from the ext dictionary of all StandardLoads
    connected to this ACBus. Returns 0.0 if no StandardLoads are found or if
    the ext field is missing.
    """
    standard_loads = context.source_system.get_components(
        StandardLoad, filter_func=lambda load: load.bus == source_component
    )

    node_lpf_total = 0.0
    for load in standard_loads:
        if hasattr(load, "ext") and isinstance(load.ext, dict):
            lpf = load.ext.get("MMWG_LPF") or load.ext.get("ReEDS_LPF", 0)
            if isinstance(lpf, int | float):
                node_lpf_total += float(lpf)

    return Ok(node_lpf_total)


@getter
def is_slack_bus(context: TranslationContext, source_component: Any) -> Result[int, ValueError]:
    """Populate bustype field based on slack bus status."""

    from r2x_sienna.models.enums import ACBusTypes

    value = 1 if source_component.bustype == ACBusTypes.SLACK else 0
    return Ok(value)


@getter
def get_voltage(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    """Extract AC voltage magnitude from base_voltage Quantity."""
    value = get_magnitude(source_component.base_voltage)
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_availability(context: TranslationContext, source_component: ACBus) -> Result[int, ValueError]:
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
    context: TranslationContext,
    source_component: Transformer2W | TapTransformer | PhaseShiftingTransformer,
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
        imag_part = magnitude.imag
        return Ok(float(imag_part))

    # Handle plain floats/ints
    if isinstance(primary_shunt, int | float):
        return Ok(float(primary_shunt))

    # If conversion fails, return error to allow defaults
    return Err(ValueError(f"Cannot convert primary_shunt to float: {primary_shunt}"))


@getter
def get_line_charging_susceptance(
    context: TranslationContext, source_component: Line | MonitoredLine
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

    # Handle FromTo_ToFrom types
    if isinstance(line_b, FromTo_ToFrom):
        return Ok(float(line_b.from_to))

    # Handle Quantity types
    magnitude = get_magnitude(line_b)
    if magnitude is not None:
        return Ok(float(magnitude))

    # Handle plain floats/ints
    if isinstance(line_b, int | float):
        return Ok(float(line_b))

    # If we can't convert it, return 0.0 as safe default
    return Ok(0.0)


@getter
def get_power_or_standard_load(
    context: TranslationContext, source_component: Any
) -> Result[float, ValueError]:
    """Populate power_load fields with aggregated active power from PowerLoad and StandardLoad."""

    total_load = 0.0

    source_system = getattr(context, "source_system", None)
    if source_system is not None:
        power_loads = source_system.get_components(
            PowerLoad, filter_func=lambda comp: comp.bus == source_component
        )
        standard_loads = source_system.get_components(
            StandardLoad, filter_func=lambda comp: comp.bus == source_component
        )
        all_loads = list(power_loads) + list(standard_loads)
    elif hasattr(source_component, "list_child_components"):
        power_loads = source_component.list_child_components(PowerLoad)
        standard_loads = source_component.list_child_components(StandardLoad)
        all_loads = list(power_loads) + list(standard_loads)
    else:
        all_loads = []

    for load in all_loads:
        if not hasattr(load, "max_active_power"):
            continue
        magnitude = get_magnitude(load.max_active_power)
        total_load += float(magnitude) if magnitude is not None else 0.0

    return Ok(total_load)


@getter
def get_heat_rate(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_base(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate_base")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_incr(context: TranslationContext, source_component: Any) -> Result[Any, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate_incr")
    return Ok(coerce_value(value))


@getter
def get_heat_rate_incr2(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate_incr2")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_incr3(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    value = compute_heat_rate_data(source_component).get("heat_rate_incr3")
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_heat_rate_load_point(context: TranslationContext, source_component: Any) -> Result[Any, ValueError]:
    value = compute_heat_rate_data(source_component).get("load_point")
    if value is None:
        return Err(ValueError("No heat rate load points"))
    return Ok(value)


@getter
def get_min_stable_level(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    limits = getattr(source_component, "active_power_limits", None)
    if not limits:
        return Ok(0.0)
    converted = sienna_get_value(limits, source_component)
    min_level = getattr(converted, "min", None)
    if min_level is None:
        return Ok(0.0)
    min_level = 0.0 if min_level < 0 else min_level
    return Ok(float(min_level))


@getter
def get_reserve_timeframe(
    context: TranslationContext, source_component: VariableReserve
) -> Result[float, ValueError]:
    """Get reserve timeframe in seconds."""
    time_frame = getattr(source_component, "time_frame", 0.0)
    return Ok(time_frame * 60)


@getter
def get_reserve_duration(
    context: TranslationContext, source_component: VariableReserve
) -> Result[float, ValueError]:
    """Get reserve sustained time in seconds."""
    sustained_time = getattr(source_component, "sustained_time", 0.0)
    return Ok(sustained_time)


@getter
def get_reserve_min_provision(
    context: TranslationContext, source_component: VariableReserve
) -> Result[float, ValueError]:
    """Get reserve requirement."""
    requirement = getattr(source_component, "requirement", 0.0)
    return Ok(requirement)


@getter
def get_reserve_max_provision(
    context: TranslationContext, source_component: VariableReserve
) -> Result[float, ValueError]:
    """Get reserve max requirement."""
    max_requirement = getattr(source_component, "max_requirement", 1e30)
    return Ok(max_requirement)


@getter
def get_reserve_type(
    context: TranslationContext, source_component: VariableReserve
) -> Result[int, ValueError]:
    """Get PLEXOS reserve type from Sienna ReserveType."""
    reserve_type_mapping = {
        ReserveType.SPINNING: 1,
        ReserveType.FLEXIBILITY: 2,
        ReserveType.REGULATION: 3,
    }
    plexos_type = reserve_type_mapping.get(source_component.reserve_type, 1)
    return Ok(plexos_type)


@getter
def get_reserve_vors(
    context: TranslationContext, source_component: VariableReserve
) -> Result[float, ValueError]:
    """Get reserve VORS."""
    vors = getattr(source_component, "vors", -1.0)
    return Ok(vors)


@getter
def get_reserve_max_sharing(
    context: TranslationContext, source_component: VariableReserve
) -> Result[float, ValueError]:
    """Get reserve max participation factor as a percentage."""
    max_participation_factor = getattr(source_component, "max_participation_factor", 1.0)
    return Ok(max_participation_factor * 100)


@getter
def get_max_capacity(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    value = None
    try:
        value = sienna_get_max_active_power(source_component)
    except TypeError:
        value = None

    if value is not None:
        return Ok(float(value))

    rating = getattr(source_component, "rating", None)
    rating_value = get_magnitude(rating)
    if rating_value is not None:
        return Ok(float(rating_value) * resolve_base_power(source_component))

    return Err(ValueError("active_power_limits or rating missing"))


@getter
def get_max_ramp_up(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    try:
        limits = sienna_get_ramp_limits(source_component)
    except (KeyError, TypeError) as err:
        return Err(ValueError(str(err)))
    return Ok(float(limits.up) if limits.up is not None else 0.0)


@getter
def get_max_ramp_down(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    try:
        limits = sienna_get_ramp_limits(source_component)
    except (KeyError, TypeError) as err:
        return Err(ValueError(str(err)))
    return Ok(float(limits.down) if limits.down is not None else 0.0)


def _get_time_limit(component: Any, attr: str, ext_key: str) -> float | None:
    """Extract time limit from time_limits attribute or ext dict."""
    time_limits = getattr(component, "time_limits", None)
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


@getter
def get_min_up_time(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    """Extract minimum up time from time_limits or ext dict."""
    value = _get_time_limit(source_component, "up", "NARIS_Min_Up_Time")
    return Ok(value if value is not None else 0.0)


@getter
def get_min_down_time(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    """Extract minimum down time from time_limits or ext dict."""
    value = _get_time_limit(source_component, "down", "NARIS_Min_Down_Time")
    return Ok(value if value is not None else 0.0)


@getter
def get_initial_generation(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    power = get_magnitude(getattr(source_component, "active_power", None))
    if power is None:
        return Ok(0.0)
    return Ok(float(power) * resolve_base_power(source_component))


@getter
def get_initial_hours_up(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    hours = _convert_time_value(getattr(source_component, "time_at_status", None)) or 0.0
    return Ok(hours if getattr(source_component, "status", False) else 0.0)


@getter
def get_initial_hours_down(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    hours = _convert_time_value(getattr(source_component, "time_at_status", None)) or 0.0
    return Ok(hours if not getattr(source_component, "status", False) else 0.0)


@getter
def get_running_cost(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = get_magnitude(getattr(cost, "fixed", None)) if cost else None
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_start_cost(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = get_magnitude(getattr(cost, "start_up", None)) if cost else None
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_shutdown_cost(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = get_magnitude(getattr(cost, "shut_down", None)) if cost else None
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_fuel_price(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    variable = getattr(cost, "variable", None) if cost else None
    if isinstance(variable, FuelCurve):
        price = get_magnitude(getattr(variable, "fuel_cost", None))
        if price is not None:
            return Ok(float(price))
    return Ok(0.0)


@getter
def get_mark_up(context: TranslationContext, source_component: Any) -> Result[Any, ValueError]:
    value = compute_markup_data(source_component).get("mark_up")
    return Ok(coerce_value(value))


@getter
def get_mark_up_point(context: TranslationContext, source_component: Any) -> Result[Any, ValueError]:
    value = compute_markup_data(source_component).get("mark_up_point")
    if value is None:
        return Err(ValueError("No mark-up load points"))
    return Ok(value)


@getter
def get_vom_charge(context: TranslationContext, source_component: Any) -> Result[Any, ValueError]:
    value = compute_markup_data(source_component).get("mark_up")
    return Ok(coerce_value(value))


@getter
def get_storage_charge_efficiency(
    context: TranslationContext, source_component: EnergyReservoirStorage
) -> Result[float, ValueError]:
    return Ok(float(source_component.efficiency.input))


@getter
def get_storage_discharge_efficiency(
    context: TranslationContext, source_component: EnergyReservoirStorage
) -> Result[float, ValueError]:
    return Ok(float(source_component.efficiency.output))


@getter
def get_storage_cycles(
    context: TranslationContext, source_component: EnergyReservoirStorage
) -> Result[float, ValueError]:
    return Ok(float(source_component.cycle_limits))


@getter
def get_storage_max_power(
    context: TranslationContext, source_component: EnergyReservoirStorage
) -> Result[float, ValueError]:
    value = get_magnitude(source_component.output_active_power_limits.max)
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_storage_capacity(
    context: TranslationContext, source_component: EnergyReservoirStorage
) -> Result[float, ValueError]:
    return Ok(float(source_component.storage_capacity))


@getter
def get_interface_min_flow(
    context: TranslationContext, source_component: TransmissionInterface
) -> Result[float, ValueError]:
    """Get min_flow from active_power_flow_limits or default."""
    limits = getattr(source_component, "active_power_flow_limits", None)
    value = getattr(limits, "min", None) if limits else None
    return Ok(float(value) if value is not None else 1e30)


@getter
def get_interface_max_flow(
    context: TranslationContext, source_component: TransmissionInterface
) -> Result[float, ValueError]:
    """Get max_flow from active_power_flow_limits or default."""
    limits = getattr(source_component, "active_power_flow_limits", None)
    value = getattr(limits, "max", None) if limits else None
    return Ok(float(value) if value is not None else 1e30)


@getter
def membership_parent_component(_: TranslationContext, component: Any) -> Result[Any, ValueError]:
    """Return the component itself for membership parent/child fields."""
    return Ok(component)


@getter
def membership_collection_nodes(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Nodes collection enum."""
    return Ok(CollectionEnum.Nodes)


@getter
def membership_collection_lines(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Lines collection enum."""
    return Ok(CollectionEnum.Lines)


@getter
def membership_collection_generators(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Generators collection enum."""
    return Ok(CollectionEnum.Generators)


@getter
def membership_collection_batteries(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Batteries collection enum."""
    return Ok(CollectionEnum.Batteries)


@getter
def membership_collection_region(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Region collection enum."""
    return Ok(CollectionEnum.Region)


@getter
def membership_collection_node_from(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the NodeFrom collection enum."""
    return Ok(CollectionEnum.NodeFrom)


@getter
def membership_collection_node_to(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the NodeTo collection enum."""
    return Ok(CollectionEnum.NodeTo)


@getter
def membership_collection_zone(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Zone collection enum."""
    return Ok(CollectionEnum.Zone)


@getter
def membership_collection_head_storage(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Head Storage collection enum."""
    return Ok(CollectionEnum.HeadStorage)


@getter
def membership_collection_tail_storage(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Tail Storage collection enum."""
    return Ok(CollectionEnum.TailStorage)


def _lookup_target_zone_by_name(context: TranslationContext, zone_name: str) -> Result[Any, ValueError]:
    """Return the translated zone with the given name."""
    for zone in context.target_system.get_components(PLEXOSZone):
        if zone.name == zone_name:
            return Ok(zone)
    return Err(ValueError(f"No PLEXOSZone found with name '{zone_name}'"))


def _lookup_target_node_by_source_area(
    context: TranslationContext, area_name: str
) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node whose source ACBus has matching area name."""
    for node in context.target_system.get_components(PLEXOSNode):
        node_name = node.name
        source_buses = list(
            context.source_system.get_components(ACBus, filter_func=lambda bus, nn=node_name: bus.name == nn)
        )

        for source_bus in source_buses:
            if hasattr(source_bus, "area"):
                bus_area = source_bus.area
                if isinstance(bus_area, Area):
                    if bus_area.name == area_name:
                        return Ok(node)
                elif isinstance(bus_area, str) and bus_area == area_name:
                    return Ok(node)

    return Err(ValueError(f"No PLEXOSNode found with source area '{area_name}'"))


def _lookup_source_generator(context: TranslationContext, gen_name: str) -> Any | None:
    """Find a source generator by name across all Sienna generator types."""
    for gen_type in SOURCE_GENERATOR_TYPES:
        generators: list[Any] = list(context.source_system.get_components(gen_type))  # type: ignore[arg-type]
        for gen in generators:
            if gen.name == gen_name:
                return gen

    return None


def _lookup_source_battery(context: TranslationContext, battery_name: str) -> Any | None:
    """Find a source battery by name."""
    batteries: list[Any] = list(context.source_system.get_components(EnergyReservoirStorage))
    for battery in batteries:
        if battery.name == battery_name:
            return battery
    return None


def _lookup_target_node_by_name(
    context: TranslationContext, node_name: str
) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node with the given name."""
    for node in context.target_system.get_components(PLEXOSNode):
        if node.name == node_name:
            return Ok(node)
    return Err(ValueError(f"No PLEXOSNode found with name '{node_name}'"))


def _find_source_line(context: TranslationContext, line_name: str) -> Any | None:
    """Find a source line by name across Line, MonitoredLine, and TwoTerminalHVDCLine types."""
    line_types: list[type[Line | MonitoredLine | TwoTerminalHVDCLine]] = [
        Line,
        MonitoredLine,
        TwoTerminalHVDCLine,
    ]

    for line_type in line_types:
        source_line: Line | MonitoredLine | TwoTerminalHVDCLine | None = next(
            (ln for ln in context.source_system.get_components(line_type) if ln.name == line_name),
            None,
        )
        if source_line is not None:
            return source_line

    return None


def _find_source_transformer(context: TranslationContext, transformer_name: str) -> Any | None:
    """Find a source transformer by name across Transformer2W, TapTransformer, and PhaseShiftingTransformer types."""
    transformer_types: list[type[Transformer2W | TapTransformer | PhaseShiftingTransformer]] = [
        Transformer2W,
        TapTransformer,
        PhaseShiftingTransformer,
    ]

    for transformer_type in transformer_types:
        source_transformer: Transformer2W | TapTransformer | PhaseShiftingTransformer | None = next(
            (
                tf
                for tf in context.source_system.get_components(transformer_type)
                if tf.name == transformer_name
            ),
            None,
        )
        if source_transformer is not None:
            return source_transformer

    return None


def _lookup_source_pumped_hydro(context: TranslationContext, gen_name: str) -> Any | None:
    """Find a source HydroPumpedStorage by deriving the base name from _head or _tail suffix."""
    # Remove _head or _tail suffix to get base name
    if gen_name.endswith(("_head", "_tail")):
        base_name = gen_name.rsplit("_", 1)[0]
    else:
        return None

    pumped_hydros: list[Any] = list(context.source_system.get_components(HydroPumpedStorage))
    for ph in pumped_hydros:
        if ph.name == base_name:
            return ph
    return None


def _attach_generator_time_series(
    context: TranslationContext,
    generator_name: str,
    target_generator: Any,
) -> None:
    """Attach time series from source generator to translated PLEXOS generator."""
    source_gen: RenewableDispatch | RenewableNonDispatch | HydroReservoir | None = None

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


def _attach_region_node_load_time_series(
    context: TranslationContext,
    region_name: str,
    node: PLEXOSNode,
    region_component: Any | None,
) -> None:
    """Attach demand load and time series from StandardLoad to the translated node and region.

    Aggregates all StandardLoads connected to buses in the given region/area and attaches
    the time series to both the node and the region component.
    """
    buses_in_region = [
        bus
        for bus in context.source_system.get_components(ACBus)
        if getattr(getattr(bus, "area", None), "name", None) == region_name
    ]

    if not buses_in_region:
        logger.debug("No buses found in region {}", region_name)
        return

    # Find all StandardLoads connected to buses in this region
    standard_loads = [
        load
        for load in context.source_system.get_components(StandardLoad)
        if getattr(load, "bus", None) in buses_in_region
    ]

    if not standard_loads:
        logger.debug("No StandardLoads found for region {}", region_name)
        return

    # Aggregate load values
    total_load = 0.0
    for load in standard_loads:
        load_value = getattr(load, "max_active_power", None)
        if load_value is not None:
            magnitude = get_magnitude(load_value)
            if magnitude is not None:
                total_load += float(magnitude)

    if total_load > 0.0:
        try:
            node.load = total_load
            logger.debug("Set node.load = {} for {}", total_load, node.name)
        except Exception as exc:
            logger.debug("Could not set node.load for {}: {}", node.name, exc)

        # Also set fixed_load on region if provided
        if region_component is not None:
            try:
                region_component.fixed_load = total_load
                logger.debug("Set fixed_load = {} for region {}", total_load, region_name)
            except Exception as exc:
                logger.debug("Could not set fixed_load for region {}: {}", region_name, exc)

    for load in standard_loads:
        for metadata in context.source_system.time_series.list_time_series_metadata(load):
            ts_list = context.source_system.list_time_series(load, name=metadata.name, **metadata.features)
            if not ts_list:
                logger.warning("Missing load time series {} for {}", metadata.name, load.name)
                continue

            ts = ts_list[0]
            ts_type = ts.__class__

            if region_component is not None and not context.target_system.has_time_series(
                region_component, name=metadata.name, time_series_type=ts_type, **metadata.features
            ):
                context.target_system.add_time_series(ts, region_component, **metadata.features)
                logger.debug("Attached load time series {} to region {}", metadata.name, region_name)


@getter
def membership_node_child_zone(context: TranslationContext, node: PLEXOSNode) -> Result[Any, ValueError]:
    """Resolve a node's load zone to the translated zone."""
    source_bus = next(
        (bus for bus in context.source_system.get_components(ACBus) if bus.name == node.name),
        None,
    )
    if source_bus is None:
        return Err(ValueError(f"No source ACBus found for node '{node.name}'"))

    load_zone = getattr(source_bus, "load_zone", None)
    if load_zone is None:
        return Err(ValueError(f"Source bus '{source_bus.name}' has no load_zone"))

    zone_name = load_zone.name if isinstance(load_zone, LoadZone) else str(load_zone)

    return _lookup_target_zone_by_name(context, zone_name)


@getter
def membership_reserve_child_generator(
    context: TranslationContext, reserve: Any
) -> Result[PLEXOSGenerator, ValueError]:
    """
    Resolve a reserve's participating generators.

    Note: This returns the first contributing generator found. For multiple devices,
    the membership rule would need to handle iteration.
    """
    reserve_name = getattr(reserve, "name", "")
    source_reserve = next(
        (r for r in context.source_system.get_components(VariableReserve) if r.name == reserve_name),
        None,
    )

    if source_reserve is None:
        return Err(ValueError(f"Source reserve '{reserve_name}' not found"))

    for gen_type in SOURCE_GENERATOR_TYPES:
        devices: list[Any] = list(context.source_system.get_components(gen_type))  # type: ignore[arg-type]
        for device in devices:
            services = getattr(device, "services", None)
            if not services:
                continue
            for service in services:
                if getattr(service, "name", None) == source_reserve.name:
                    target_device = context.target_system.get_component_by_uuid(device.uuid)
                    if target_device:
                        return Ok(target_device)

    return Err(ValueError(f"No contributing generators found for reserve '{reserve_name}'"))


@getter
def membership_reserve_child_battery(
    context: TranslationContext, reserve: Any
) -> Result[PLEXOSBattery, ValueError]:
    """
    Resolve a reserve's participating batteries.

    Note: This returns the first contributing battery found. For multiple devices,
    the membership rule would need to handle iteration.
    """
    reserve_name = getattr(reserve, "name", "")
    source_reserve = next(
        (r for r in context.source_system.get_components(VariableReserve) if r.name == reserve_name),
        None,
    )

    if source_reserve is None:
        return Err(ValueError(f"Source reserve '{reserve_name}' not found"))

    batteries: list[Any] = list(context.source_system.get_components(EnergyReservoirStorage))
    for device in batteries:
        services = getattr(device, "services", None)
        if not services:
            continue
        for service in services:
            if getattr(service, "name", None) == source_reserve.name:
                target_device = context.target_system.get_component_by_uuid(device.uuid)
                if target_device and isinstance(target_device, PLEXOSBattery):
                    return Ok(target_device)

    return Err(ValueError(f"No contributing batteries found for reserve '{reserve_name}'"))


@getter
def membership_component_child_node(
    context: TranslationContext, component: Any
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
    context: TranslationContext, interface: Any
) -> Result[PLEXOSLine, ValueError]:
    """Resolve an interface's lines to translated lines.

    Note: This returns the first line. For multiple lines,
    the membership rule should handle iteration.
    """
    interface_name = getattr(interface, "name", "")

    source_interface = next(
        (
            intf
            for intf in context.source_system.get_components(TransmissionInterface)
            if intf.name == interface_name
        ),
        None,
    )

    if source_interface is None:
        return Err(ValueError(f"No source TransmissionInterface found for '{interface_name}'"))

    lines = getattr(source_interface, "lines", None)
    if not lines:
        return Err(ValueError(f"TransmissionInterface '{interface_name}' has no lines"))

    if not lines:
        return Err(ValueError(f"TransmissionInterface '{interface_name}' has empty lines"))

    first_line = lines[0]
    line_name = first_line.name if hasattr(first_line, "name") else str(first_line)

    target_line = next(
        (line for line in context.target_system.get_components(PLEXOSLine) if line.name == line_name),
        None,
    )

    if target_line is None:
        return Err(ValueError(f"No PLEXOSLine found for line '{line_name}'"))

    return Ok(target_line)


@getter
def membership_region_parent_node(context: TranslationContext, region: Any) -> Result[PLEXOSNode, ValueError]:
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
def membership_region_child_node(context: TranslationContext, region: Any) -> Result[PLEXOSNode, ValueError]:
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
    context: TranslationContext, line: PLEXOSLine
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
    context: TranslationContext, line: PLEXOSLine
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
    context: TranslationContext, transformer: Any
) -> Result[PLEXOSNode, ValueError]:
    """Return the from-node for a translated transformer."""
    if not isinstance(transformer, PLEXOSTransformer):
        return Err(ValueError(f"Component '{transformer.name}' is not a PLEXOSTransformer"))

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
    context: TranslationContext, transformer: Any
) -> Result[PLEXOSNode, ValueError]:
    """Return the to-node for a translated transformer."""
    if not isinstance(transformer, PLEXOSTransformer):
        return Err(ValueError(f"Component '{transformer.name}' is not a PLEXOSTransformer"))

    source_transformer = _find_source_transformer(context, transformer.name)

    if source_transformer is None:
        return Err(ValueError(f"Source transformer '{transformer.name}' not found"))

    if not hasattr(source_transformer, "arc"):
        return Err(ValueError(f"Source transformer '{transformer.name}' missing arc data"))

    to_bus = source_transformer.arc.to_from
    to_bus_name = to_bus.name if hasattr(to_bus, "name") else str(to_bus)

    return _lookup_target_node_by_name(context, to_bus_name)


@getter
def membership_pumped_hydro_head_storage(
    context: TranslationContext, generator: Any
) -> Result[Any, ValueError]:
    """Resolve a pumped hydro generator's head storage.

    The head generator (with _head suffix) links to a storage with the same name.
    Both are created from the same HydroPumpedStorage source component.
    """
    gen_name = getattr(generator, "name", "")

    if not gen_name.endswith("_head"):
        return Err(ValueError(f"Generator '{gen_name}' is not a head generator (missing _head suffix)"))

    source_pumped_hydro = _lookup_source_pumped_hydro(context, gen_name)
    if source_pumped_hydro is None:
        return Err(
            ValueError(f"Generator '{gen_name}' does not correspond to a HydroPumpedStorage component")
        )

    storage_name = gen_name
    target_storage = next(
        (
            storage
            for storage in context.target_system.get_components(PLEXOSStorage)
            if storage.name == storage_name
        ),
        None,
    )

    if target_storage is None:
        return Err(ValueError(f"No PLEXOSStorage found for '{storage_name}'"))

    return Ok(target_storage)


@getter
def membership_pumped_hydro_tail_storage(
    context: TranslationContext, generator: Any
) -> Result[Any, ValueError]:
    """Resolve a pumped hydro generator's tail storage.

    The tail generator (with _tail suffix) links to a storage with the same name.
    Both are created from the same HydroPumpedStorage source component.
    """
    gen_name = getattr(generator, "name", "")

    if not gen_name.endswith("_tail"):
        return Err(ValueError(f"Generator '{gen_name}' is not a tail generator (missing _tail suffix)"))

    source_pumped_hydro = _lookup_source_pumped_hydro(context, gen_name)
    if source_pumped_hydro is None:
        return Err(
            ValueError(f"Generator '{gen_name}' does not correspond to a HydroPumpedStorage component")
        )

    storage_name = gen_name
    target_storage = next(
        (
            storage
            for storage in context.target_system.get_components(PLEXOSStorage)
            if storage.name == storage_name
        ),
        None,
    )

    if target_storage is None:
        return Err(ValueError(f"No PLEXOSStorage found for '{storage_name}'"))

    return Ok(target_storage)
