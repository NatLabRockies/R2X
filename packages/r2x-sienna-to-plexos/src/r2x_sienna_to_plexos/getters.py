"""Getter functions for rules."""

from __future__ import annotations

from typing import Any

from infrasys.cost_curves import FuelCurve
from plexosdb.enums import CollectionEnum
from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator, PLEXOSLine, PLEXOSNode
from r2x_sienna.models import (
    ACBus,
    Area,
    EnergyReservoirStorage,
    HydroDispatch,
    HydroEnergyReservoir,
    HydroPumpedStorage,
    Line,
    MonitoredLine,
    PhaseShiftingTransformer,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    SynchronousCondenser,
    TapTransformer,
    ThermalMultiStart,
    ThermalStandard,
    Transformer2W,
    TwoTerminalHVDCLine,
)
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


@getter
def is_slack_bus(context: TranslationContext, source_component: Any) -> Result[int, ValueError]:
    """Populate bustype field based on slack bus status."""

    from r2x_sienna.models.enums import ACBusTypes

    value = 1 if source_component.bustype == ACBusTypes.SLACK else 0
    return Ok(value)


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
def get_power_load(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    """Populate power_load fields with aggregated active power."""

    total_load = 0.0

    source_system = getattr(context, "source_system", None)
    if source_system is not None:
        power_loads = source_system.get_components(
            PowerLoad, filter_func=lambda comp: comp.bus == source_component
        )
    elif hasattr(source_component, "list_child_components"):
        power_loads = source_component.list_child_components(PowerLoad)
    else:
        power_loads = []

    for load in power_loads:
        if not hasattr(load, "max_active_power"):
            continue
        magnitude = get_magnitude(load.max_active_power)
        total_load += float(magnitude) if magnitude is not None else 0.0

    return Ok(total_load)


@getter
def get_voltage(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    """Extract AC voltage magnitude from base_voltage Quantity."""
    value = get_magnitude(source_component.base_voltage)
    return Ok(float(value) if value is not None else 0.0)


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
    return Ok(float(min_level) if min_level is not None else 0.0)


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
    time_limits = getattr(component, "time_limits", None)
    value = getattr(time_limits, attr, None) if time_limits else None
    if value is None and component.ext:
        value = component.ext.get(ext_key)
    return _convert_time_value(value)


def _convert_time_value(value: Any) -> float | None:
    if value is None:
        return None
    magnitude = get_magnitude(value)
    return float(magnitude) if magnitude is not None else None


@getter
def get_min_up_time(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    value = _get_time_limit(source_component, "up", "min_up_time")
    if value is None:
        return Err(ValueError("Minimum up time missing"))
    return Ok(value)


@getter
def get_min_down_time(context: TranslationContext, source_component: Any) -> Result[float, ValueError]:
    value = _get_time_limit(source_component, "down", "min_down_time")
    if value is None:
        return Err(ValueError("Minimum down time missing"))
    return Ok(value)


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
def membership_parent_component(_: TranslationContext, component: Any) -> Result[Any, ValueError]:
    """Return the component itself for membership parent/child fields."""
    return Ok(component)


@getter
def membership_collection_nodes(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Nodes collection enum."""
    return Ok(CollectionEnum.Nodes)


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
    generator_types = [
        HydroDispatch,
        ThermalStandard,
        ThermalMultiStart,
        RenewableDispatch,
        RenewableNonDispatch,
        HydroEnergyReservoir,
        HydroPumpedStorage,
        SynchronousCondenser,
    ]

    for gen_type in generator_types:
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


@getter
def membership_component_child_node(
    context: TranslationContext, component: Any
) -> Result[PLEXOSNode, ValueError]:
    """Resolve a component's bus to the translated node.

    Works for both PLEXOSGenerator and PLEXOSBattery components.
    """
    comp_name = getattr(component, "name", "")

    if isinstance(component, PLEXOSGenerator):
        source_comp = _lookup_source_generator(context, comp_name)
        comp_type = "generator"
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

    if source_comp is None:
        return Err(ValueError(f"No source {comp_type} found for '{comp_name}'"))

    bus = getattr(source_comp, "bus", None)
    if bus is None or not getattr(bus, "name", None):
        return Err(ValueError(f"Source {comp_type} '{source_comp.name}' is missing bus data"))

    return _lookup_target_node_by_name(context, bus.name)


@getter
def membership_region_parent_node(context: TranslationContext, region: Any) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node for membership parent links."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node_by_source_area(context, region_name)
    match result:
        case Ok(_):
            return result
        case Err(error):
            return Err(ValueError(str(error)) if not isinstance(error, ValueError) else error)
        case _:
            return Err(ValueError(f"Unexpected result type for region '{region_name}'"))


@getter
def membership_region_child_node(context: TranslationContext, region: Any) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node that matches the region name."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node_by_source_area(context, region_name)
    match result:
        case Ok(_):
            return result
        case Err(error):
            return Err(ValueError(str(error)) if not isinstance(error, ValueError) else error)
        case _:
            return Err(ValueError(f"Unexpected result type for region '{region_name}'"))


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
