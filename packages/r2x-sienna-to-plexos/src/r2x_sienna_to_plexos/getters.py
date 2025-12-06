"""Getter functions for rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infrasys.cost_curves import FuelCurve
from r2x_sienna.models import PowerLoad
from r2x_sienna.models.getters import (
    get_max_active_power as sienna_get_max_active_power,
)
from r2x_sienna.models.getters import (
    get_ramp_limits as sienna_get_ramp_limits,
)
from r2x_sienna.models.getters import (
    get_value as sienna_get_value,
)
from r2x_sienna.units import get_magnitude  # type: ignore[import-untyped]

from r2x_core import Err, Ok, Result
from r2x_core.getters import getter
from r2x_sienna_to_plexos.getters_utils import (
    coerce_value,
    compute_heat_rate_data,
    compute_markup_data,
    resolve_base_power,
)

if TYPE_CHECKING:
    from r2x_sienna.models import (
        ACBus,
        EnergyReservoirStorage,
        Line,
        MonitoredLine,
        PhaseShiftingTransformer,
        TapTransformer,
        Transformer2W,
    )

    from r2x_core import TranslationContext


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
    b = source_component.b

    # If b is None, return 0.0 as safe default
    if b is None:
        return Ok(0.0)

    # Handle complex numbers by extracting imaginary part
    if isinstance(b, complex):
        return Ok(float(b.imag))

    # Handle Quantity types
    magnitude = get_magnitude(b)
    if magnitude is not None:
        return Ok(float(magnitude))

    # Handle plain floats/ints
    if isinstance(b, int | float):
        return Ok(float(b))

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
