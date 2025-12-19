"""Getter helpers for ReEDS to Sienna translation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from infrasys.cost_curves import CostCurve, FuelCurve, LinearCurve
from r2x_sienna.models import ACBus
from r2x_sienna.models.costs import HydroGenerationCost, RenewableGenerationCost, ThermalGenerationCost
from r2x_sienna.models.enums import ACBusTypes, PrimeMoversType, StorageTechs, ThermalFuels
from r2x_sienna.models.named_tuples import FromTo_ToFrom, InputOutput, MinMax, UpDown
from r2x_sienna.units import ureg

from r2x_core import Err, Ok, Result, UnitSystem
from r2x_core.getters import getter

if TYPE_CHECKING:
    from r2x_reeds.models import (
        ReEDSDemand,
        ReEDSHydroGenerator,
        ReEDSInterface,
        ReEDSRegion,
        ReEDSStorage,
        ReEDSThermalGenerator,
        ReEDSVariableGenerator,
    )
    from r2x_sienna.models import ACBus, Area

    from r2x_core import TranslationContext


def _ok_num(val: float | int) -> Result[float | int, ValueError]:
    """Typed Ok wrapper for numeric Result returns."""
    return cast(Result[float | int, ValueError], Ok(val))


@getter
def unique_component_name(context: TranslationContext, component) -> Result[str, ValueError]:
    """
    Ensure the component name is unique among ThermalStandard components in the target system
    by appending _1, _2, etc. if needed.
    """
    from r2x_sienna.models import ThermalStandard

    base_name = getattr(component, "name", "")
    name = base_name
    i = 1
    existing_names = {getattr(c, "name", None) for c in context.target_system.get_components(ThermalStandard)}
    while name in existing_names:
        name = f"{base_name}_{i}"
        i += 1
    return Ok(name)


@getter
def get_line_resistance(_: TranslationContext, component) -> Result[float | int, ValueError]:
    """Get line resistance 'r' value."""
    r_value = getattr(component, "r", None)
    if r_value is None:
        return _ok_num(0.0)
    return _ok_num(float(r_value))


@getter
def get_line_reactance(_: TranslationContext, component) -> Result[float | int, ValueError]:
    """Get line reactance 'x' value."""
    x_value = getattr(component, "x", None)
    if x_value is None:
        return _ok_num(0.0)
    return _ok_num(float(x_value))


@getter
def get_line_susceptance(_: TranslationContext, component) -> Result[FromTo_ToFrom, ValueError]:
    """Get line susceptance 'b' value as FromTo_ToFrom."""
    b_value = getattr(component, "b", None)
    if b_value is None:
        b_value = 0.0
    return Ok(FromTo_ToFrom(from_to=float(b_value), to_from=float(b_value)))


@getter
def get_line_conductance(_: TranslationContext, component) -> Result[FromTo_ToFrom, ValueError]:
    """Get line susceptance 'b' value as FromTo_ToFrom."""
    b_value = getattr(component, "b", None)
    if b_value is None:
        b_value = 0.0
    return Ok(FromTo_ToFrom(from_to=float(b_value), to_from=float(b_value)))


@getter
def get_capacity_as_rating(_: TranslationContext, component: object) -> Result[float | int, ValueError]:
    """Map ReEDS capacity (MW) to Sienna rating/base_power fields."""
    capacity = getattr(component, "capacity", None)
    if capacity is None:
        return _ok_num(0.0)
    return _ok_num(float(capacity))


@getter
def get_capacity_as_base_power(
    context: TranslationContext, component: object
) -> Result[float | int, ValueError]:
    """Alias to reuse rating getter for base_power."""
    capacity = getattr(component, "capacity", None)
    if capacity is None:
        return _ok_num(0.0)
    return _ok_num(float(capacity))


@getter
def get_active_power_limits(
    _: TranslationContext, component: ReEDSThermalGenerator
) -> Result[MinMax, ValueError]:
    """Create a MinMax limit using capacity as the max."""
    capacity = getattr(component, "capacity", 0.0)
    return Ok(MinMax(min=0.0, max=float(capacity)))


@getter
def get_thermal_operation_cost(
    _: TranslationContext, __: ReEDSThermalGenerator
) -> Result[ThermalGenerationCost, ValueError]:
    """Return zeroed thermal operation cost."""
    return Ok(
        ThermalGenerationCost(
            fixed=0.0,
            shut_down=0.0,
            start_up=0.0,
            variable=FuelCurve(
                value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS, fuel_cost=0.0
            ),
        )
    )


@getter
def get_renewable_operation_cost(
    _: TranslationContext, __: ReEDSVariableGenerator
) -> Result[RenewableGenerationCost, ValueError]:
    """Return zeroed renewable operation cost."""
    return Ok(
        RenewableGenerationCost(
            variable=CostCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS)
        )
    )


@getter
def get_prime_mover(
    _: TranslationContext, component: ReEDSThermalGenerator
) -> Result[PrimeMoversType, ValueError]:
    """Map ReEDS technology to a PrimeMoversType."""
    tech = (getattr(component, "technology", "") or "").lower()
    if "cc" in tech:
        return Ok(PrimeMoversType.CC)
    if "ct" in tech or "gas" in tech:
        return Ok(PrimeMoversType.CT)
    if "coal" in tech:
        return Ok(PrimeMoversType.ST)
    return Ok(PrimeMoversType.OT)


@getter
def get_fuel_enum(
    _: TranslationContext, component: ReEDSThermalGenerator
) -> Result[ThermalFuels, ValueError]:
    """Map ReEDS fuel type strings to Sienna ThermalFuels."""
    fuel = (getattr(component, "fuel_type", "") or "").lower()
    if "gas" in fuel:
        return Ok(ThermalFuels.NATURAL_GAS)
    if "coal" in fuel:
        return Ok(ThermalFuels.COAL)
    if "oil" in fuel:
        return Ok(ThermalFuels.RESIDUAL_FUEL_OIL)
    return Ok(ThermalFuels.OTHER)


@getter
def get_renewable_prime_mover(
    _: TranslationContext, component: ReEDSVariableGenerator
) -> Result[PrimeMoversType, ValueError]:
    """Map variable generator technology to a renewable prime mover."""
    tech = (getattr(component, "technology", "") or "").lower()
    if "wind" in tech:
        return Ok(PrimeMoversType.WT)
    if "distpv" in tech:
        return Ok(PrimeMoversType.PVe)
    if "pv" in tech:
        return Ok(PrimeMoversType.PVe)
    return Ok(PrimeMoversType.WT)


@getter
def get_load_base_power(_: TranslationContext, __: ReEDSDemand) -> Result[float | int, ValueError]:
    """Return a default load base power of 100.0 MVA."""
    return _ok_num(100.0)


@getter
def get_zero_active_power(_: TranslationContext, __: object) -> Result[float | int, ValueError]:
    """Return zero active power placeholder."""
    return _ok_num(0.0)


@getter
def get_zero_reactive_power(_: TranslationContext, __: object) -> Result[float | int, ValueError]:
    """Return zero reactive power placeholder."""
    return _ok_num(0.0)


@getter
def get_default_must_run(_: TranslationContext, __: object) -> Result[bool, ValueError]:
    """Return default must_run flag."""
    return Ok(False)


@getter
def get_default_status(_: TranslationContext, __: object) -> Result[bool, ValueError]:
    """Return default online status."""
    return Ok(True)


@getter
def get_default_time_at_status(_: TranslationContext, __: object) -> Result[float | int, ValueError]:
    """Return zeroed time_at_status."""
    return _ok_num(0.0)


@getter
def get_area_from(context: TranslationContext, component: ReEDSInterface) -> Result[Area, ValueError]:
    """Resolve the source Area for an interchange."""
    from r2x_sienna.models import Area

    target_areas = list(context.target_system.get_components(Area))
    name = getattr(getattr(component, "from_region", None), "name", None)
    for area in target_areas:
        if getattr(area, "name", None) == name:
            return cast(Result[Area, ValueError], Ok(area))
    return Err(ValueError(f"No Area found for from_region {name}"))


@getter
def get_area_to(context: TranslationContext, component: ReEDSInterface) -> Result[Area, ValueError]:
    """Resolve the destination Area for an interchange."""
    from r2x_sienna.models import Area

    target_areas = list(context.target_system.get_components(Area))
    name = getattr(getattr(component, "to_region", None), "name", None)
    for area in target_areas:
        if getattr(area, "name", None) == name:
            return cast(Result[Area, ValueError], Ok(area))
    return Err(ValueError(f"No Area found for to_region {name}"))


@getter
def get_reserve_time_frame(_: TranslationContext, component) -> Result[float, ValueError]:
    """Get the reserve time frame in seconds."""
    return Ok(float(getattr(component, "time_frame", 0.0) or 0.0))


@getter
def get_reserve_requirement(_: TranslationContext, component) -> Result[float | None, ValueError]:
    """Get the reserve requirement in p.u (SYSTEM_BASE)."""
    return Ok(getattr(component, "requirement", 0.0))


@getter
def get_reserve_sustained_time(_: TranslationContext, component) -> Result[float, ValueError]:
    """Get the sustained time in seconds."""
    return Ok(float(getattr(component, "duration", 3600.0) or 3600.0))


@getter
def get_reserve_max_output_fraction(_: TranslationContext, component) -> Result[float, ValueError]:
    """Get the max output fraction [0, 1.0]."""
    return Ok(float(getattr(component, "max_output_fraction", 1.0) or 1.0))


@getter
def get_reserve_max_participation_factor(_: TranslationContext, component) -> Result[float, ValueError]:
    """Get the max participation factor [0, 1.0]."""
    return Ok(float(getattr(component, "max_participation_factor", 1.0) or 1.0))


@getter
def get_reserve_deployed_fraction(_: TranslationContext, component) -> Result[float, ValueError]:
    """Get the deployed fraction [0, 1.0]."""
    return Ok(float(getattr(component, "deployed_fraction", 1.0) or 1.0))


@getter
def get_reserve_type(_: TranslationContext, component) -> Result[str, ValueError]:
    """Get the reserve type (e.g., 'SPINNING', 'REGULATION')."""
    return Ok(getattr(component, "reserve_type", "SPINNING"))


@getter
def get_reserve_direction(_: TranslationContext, component) -> Result[str, ValueError]:
    """Get the reserve direction as 'UP' or 'DOWN' string."""
    direction = getattr(component, "direction", "UP")
    if hasattr(direction, "name"):
        direction_str = direction.name.upper()
    elif isinstance(direction, str):
        direction_str = direction.upper()
    else:
        direction_str = "UP"
    if direction_str not in {"UP", "DOWN"}:
        direction_str = "UP"
    return Ok(direction_str)


@getter
def get_interface_flow_limits(_: TranslationContext, __: ReEDSInterface) -> Result[FromTo_ToFrom, ValueError]:
    """Provide zeroed flow limits placeholder."""
    return Ok(FromTo_ToFrom(from_to=0.0, to_from=0.0))


@getter
def get_zero_flow(_: TranslationContext, __: ReEDSInterface) -> Result[float | int, ValueError]:
    """Return zero flow for interchange defaults."""
    return _ok_num(0.0)


def _lookup_area(context: TranslationContext, name: str | None) -> Area | None:  # type: ignore[name-defined]
    """Helper to find a target Area by name."""
    from r2x_sienna.models import Area

    for area in context.target_system.get_components(Area):
        if getattr(area, "name", None) == name:
            return area
    return None


@getter
def get_area_for_region(context: TranslationContext, component: ReEDSRegion) -> Result[Area, ValueError]:
    """Resolve Area for a region."""
    area = _lookup_area(context, getattr(component, "name", None))
    if area is None:
        return Err(ValueError("Area not found for region"))
    return Ok(area)


@getter
def bus_name_from_region(_: TranslationContext, component: ReEDSRegion) -> Result[str, ValueError]:
    """Derive a bus name from the region."""
    return Ok(f"{getattr(component, 'name', 'REG')}_BUS")


@getter
def get_bus_for_region(context: TranslationContext, component: object) -> Result[ACBus, ValueError]:
    """
    Find the bus corresponding to the component's region.
    Extract region name from the component's name (e.g., 'wind-ons_7_p62' -> 'p62').
    """
    import re

    from r2x_sienna.models import ACBus

    # Try to extract region name (e.g., p62) from the component's name
    name = getattr(component, "name", "")
    match = re.search(r"(p\d+)", name)
    region_name = match.group(1) if match else None
    bus_name = f"{region_name}_BUS" if region_name else None

    if not bus_name:
        return Err(ValueError(f"Could not extract region from component name '{name}'"))

    for bus in context.target_system.get_components(ACBus):
        if getattr(bus, "name", "") == bus_name:
            return Ok(bus)
    return Err(ValueError(f"No bus found for region {region_name}"))


@getter
def get_bus_number(_: TranslationContext, component: ReEDSRegion) -> Result[int, ValueError]:
    """Extract and return the bus number as an integer from the region name (e.g., 'p60' -> 60)."""
    import re

    name = getattr(component, "name", "")
    match = re.match(r"p(\d+)", name)
    if match:
        return Ok(int(match.group(1)))
    return Err(ValueError(f"Could not extract bus number from region name '{name}'"))


@getter
def base_voltage_default(_: TranslationContext, __: object) -> Result[float | int, ValueError]:
    """Provide default base voltage in kV."""
    return _ok_num(float(ureg.Quantity(115.0, "kV").magnitude))  # magnitude only to avoid unit issues


@getter
def bustype_default(_: TranslationContext, __: object) -> Result[ACBusTypes, ValueError]:
    """Default bus type."""
    return Ok(ACBusTypes.PQ)


@getter
def demand_max_active_power(_: TranslationContext, component: ReEDSDemand) -> Result[float | int, ValueError]:
    """Return demand max active power."""
    return _ok_num(float(getattr(component, "max_active_power", 0.0) or 0.0))


@getter
def demand_max_reactive_power(_: TranslationContext, __: ReEDSDemand) -> Result[float | int, ValueError]:
    """Return zero reactive power."""
    return _ok_num(0.0)


@getter
def hydro_rating(_: TranslationContext, component: ReEDSHydroGenerator) -> Result[float | int, ValueError]:  # type: ignore[name-defined]
    """Map capacity to rating/base_power."""
    return _ok_num(float(getattr(component, "capacity", 0.0) or 0.0))


@getter
def hydro_active_power_limits(
    _: TranslationContext, component: ReEDSHydroGenerator
) -> Result[MinMax, ValueError]:  # type: ignore[name-defined]
    """Min/max active power limits for hydro."""
    cap = float(getattr(component, "capacity", 0.0) or 0.0)
    return Ok(MinMax(min=0.0, max=cap))


@getter
def hydro_ramp_limits(_: TranslationContext, component: ReEDSHydroGenerator) -> Result[UpDown, ValueError]:
    """Min/max ramp limits for hydro."""
    cap = float(getattr(component, "capacity", 0.0) or 0.0)
    ramp_rate = float(getattr(component, "ramp_rate", 0.0) or 0.0)
    ramp_limit = cap * ramp_rate / 100.0
    return Ok(UpDown(up=ramp_limit, down=ramp_limit))


@getter
def hydro_time_limits(_: TranslationContext, component: ReEDSHydroGenerator) -> Result[MinMax, ValueError]:
    """Min/max time limits for hydro."""
    min_up_time = float(getattr(component, "min_up_time", 0.0) or 0.0)
    min_down_time = float(getattr(component, "min_down_time", 0.0) or 0.0)
    return Ok(UpDown(up=min_up_time, down=min_down_time))


@getter
def hydro_operation_cost(
    _: TranslationContext, __: ReEDSHydroGenerator
) -> Result[HydroGenerationCost, ValueError]:  # type: ignore[name-defined]
    """Return zeroed hydro cost."""
    from r2x_sienna.models.costs import HydroGenerationCost

    return Ok(
        HydroGenerationCost(
            fixed=0.0,
            variable=CostCurve(
                value_curve=LinearCurve(10), power_units=UnitSystem.NATURAL_UNITS, vom_cost=LinearCurve(5.0)
            ),
        )
    )


@getter
def storage_rating(_: TranslationContext, component: ReEDSStorage) -> Result[float | int, ValueError]:
    """Use capacity as rating/base power for storage."""
    return _ok_num(float(getattr(component, "capacity", 0.0) or 0.0))


@getter
def storage_capacity_mwh(_: TranslationContext, component: ReEDSStorage) -> Result[float | int, ValueError]:
    """Energy capacity from explicit value or duration * power."""
    energy = getattr(component, "energy_capacity", None)
    if energy is not None:
        return _ok_num(float(energy))
    capacity = float(getattr(component, "capacity", 0.0) or 0.0)
    duration = float(getattr(component, "storage_duration", 0.0) or 0.0)
    return _ok_num(capacity * duration)


@getter
def storage_level_limits(context: TranslationContext, component: ReEDSStorage) -> Result[MinMax, ValueError]:
    """Always return storage level limits as a normalized fraction (0.0 to 1.0)."""
    return Ok(MinMax(min=0.0, max=1.0))


@getter
def storage_power_limits(context: TranslationContext, component: ReEDSStorage) -> Result[MinMax, ValueError]:
    """Charge/discharge limits from capacity."""
    cap = float(getattr(component, "capacity", 0.0) or 0.0)
    return Ok(MinMax(min=0.0, max=cap))


@getter
def storage_efficiency(_: TranslationContext, component: ReEDSStorage) -> Result[InputOutput, ValueError]:
    """Map round-trip efficiency to input/output pair."""
    rte = float(getattr(component, "round_trip_efficiency", 1.0) or 1.0)
    return Ok(InputOutput(input=1.0, output=rte))


@getter
def storage_prime_mover(_: TranslationContext, __: ReEDSStorage) -> Result[PrimeMoversType, ValueError]:
    """Default storage prime mover."""
    return Ok(PrimeMoversType.ES)


@getter
def storage_tech(_: TranslationContext, component: ReEDSStorage) -> Result[StorageTechs, ValueError]:
    """Map storage technology string to enum."""
    tech = (getattr(component, "technology", "") or "").lower()
    if "bat" in tech or "lib" in tech:
        return Ok(StorageTechs.LIB)
    return Ok(StorageTechs.OTHER_MECH)


@getter
def storage_initial_level(_: TranslationContext, __: ReEDSStorage) -> Result[float | int, ValueError]:
    """Initial storage level as fraction."""
    return _ok_num(0.0)


@getter
def storage_conversion_factor(_: TranslationContext, __: ReEDSStorage) -> Result[float | int, ValueError]:
    """Default conversion factor."""
    return _ok_num(1.0)


@getter
def get_line_rating(_: TranslationContext, component):
    """Use max_active_power.from_to as the line rating."""
    try:
        return Ok(component.max_active_power.from_to)
    except Exception as e:
        return Err(ValueError(f"Could not get line rating: {e}"))


@getter
def get_line_active_power_flow(_: TranslationContext, component):
    """Use max_active_power.from_to as the active power flow."""
    try:
        return Ok(component.max_active_power.from_to)
    except Exception as e:
        return Err(ValueError(f"Could not get active_power_flow: {e}"))


@getter
def get_line_reactive_power_flow(_: TranslationContext, component):
    """Return reactive_power_flow or 0.0 if not available."""
    return Ok(float(getattr(component, "reactive_power_flow", 0.0) or 0.0))


@getter
def get_line_angle_limits(_: TranslationContext, component):
    """Get angle limits for a line."""
    val = getattr(component, "angle_limits", None)
    if isinstance(val, MinMax):
        return Ok(val)
    if isinstance(val, dict) and "min" in val and "max" in val:
        return Ok(MinMax(min=val["min"], max=val["max"]))
    if isinstance(val, tuple | list) and len(val) == 2:
        return Ok(MinMax(min=val[0], max=val[1]))
    return Ok(MinMax(min=-90.0, max=90.0))


@getter
def get_arc_for_line(context: TranslationContext, component, resolved=None):
    """
    Create an Arc object for the line, referencing existing ACBus objects for from_to and to_from,
    using the arc's own direction as indicated by its name.
    """
    import re

    from r2x_sienna.models import ACBus, Arc

    # Try to extract direction from the arc/line name
    arc_name_str = getattr(component, "name", "")
    match = re.match(r"(p\d+)_((p\d+)_)?(ac|dc)", arc_name_str)
    if match:
        from_region_name = match.group(1)
        to_region_name = match.group(3) if match.group(3) else None
    else:
        # fallback to interface
        from_region_name = getattr(getattr(component.interface, "from_region", None), "name", None)
        to_region_name = getattr(getattr(component.interface, "to_region", None), "name", None)

    # If parsing failed, fallback to interface
    if not from_region_name or not to_region_name:
        from_region_name = getattr(getattr(component.interface, "from_region", None), "name", None)
        to_region_name = getattr(getattr(component.interface, "to_region", None), "name", None)

    # Get bus numbers
    from_number_result = get_bus_number(context, type("Dummy", (), {"name": from_region_name})())
    to_number_result = get_bus_number(context, type("Dummy", (), {"name": to_region_name})())

    if from_number_result.is_err() or to_number_result.is_err():
        return Err(ValueError("Could not extract bus numbers from arc name or interface"))

    from_number = from_number_result.unwrap()
    to_number = to_number_result.unwrap()

    from_bus_obj = None
    to_bus_obj = None
    for bus in context.target_system.get_components(ACBus):
        if getattr(bus, "number", None) == from_number:
            from_bus_obj = bus
        if getattr(bus, "number", None) == to_number:
            to_bus_obj = bus

    if from_bus_obj is None:
        return Err(ValueError(f"ACBus with number {from_number} not found for Arc from_to"))
    if to_bus_obj is None:
        return Err(ValueError(f"ACBus with number {to_number} not found for Arc to_from"))

    arc_name = f"{arc_name_str}__{getattr(component, 'uuid', '')}"

    try:
        arc = Arc(name=arc_name, from_to=from_bus_obj, to_from=to_bus_obj)
        return Ok(arc)
    except Exception as e:
        return Err(ValueError(f"Could not create Arc: {e}"))
