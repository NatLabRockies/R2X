"""Getter helpers for ReEDS to Sienna translation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from infrasys.cost_curves import CostCurve, FuelCurve, LinearCurve
from r2x_sienna.models import ACBus, Arc
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
        ReEDSReserve,
        ReEDSStorage,
        ReEDSThermalGenerator,
        ReEDSTransmissionLine,
        ReEDSVariableGenerator,
    )
    from r2x_sienna.models import ACBus, Area

    from r2x_core import PluginContext


_NON_NUMERIC_REGION_BUS_NUMBERS: dict[str, int] = {}
_NEXT_AVAILABLE_BUS_NUMBER = 999999


def _ok_num(val: float | int) -> Result[float | int, ValueError]:
    """Typed Ok wrapper for numeric Result returns."""
    return cast(Result[float | int, ValueError], Ok(val))


def _lookup_area(context: PluginContext, name: str | None) -> Area | None:  # type: ignore[name-defined]
    """Helper to find a target Area by name."""
    from r2x_sienna.models import Area

    for area in context.target_system.get_components(Area):
        if getattr(area, "name", None) == name:
            return area
    return None


@getter
def get_component_ext(component: object, context: PluginContext) -> Result[dict, ValueError]:
    """
    Get the component's ext dict, storing the technology name under the 'technology' key.
    """
    ext = getattr(component, "ext", None)
    if ext is None:
        ext = {}
    elif not isinstance(ext, dict):
        return Err(ValueError("Component ext attribute is not a dict"))

    technology = getattr(component, "technology", None)
    if technology is not None:
        ext = dict(ext)
        ext["technology"] = technology

    return Ok(ext)


@getter
def unique_component_name(component: object, context: PluginContext) -> Result[str, ValueError]:
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
def get_line_resistance(
    component: ReEDSTransmissionLine,
    context: PluginContext,
) -> Result[float | int, ValueError]:
    """Get line resistance 'r' value."""
    r_value = getattr(component, "r", None)
    if r_value is None:
        return _ok_num(0.0)
    return _ok_num(float(r_value))


@getter
def get_line_reactance(
    component: ReEDSTransmissionLine, context: PluginContext
) -> Result[float | int, ValueError]:
    """Get line reactance 'x' value."""
    x_value = getattr(component, "x", None)
    if x_value is None:
        return _ok_num(0.0)
    return _ok_num(float(x_value))


@getter
def get_line_susceptance(
    component: ReEDSTransmissionLine, context: PluginContext
) -> Result[FromTo_ToFrom, ValueError]:
    """Get line susceptance 'b' value as FromTo_ToFrom."""
    b_value = getattr(component, "b", None)
    if b_value is None:
        b_value = 0.0
    return Ok(FromTo_ToFrom(from_to=float(b_value), to_from=float(b_value)))


@getter
def get_line_conductance(
    component: ReEDSTransmissionLine, context: PluginContext
) -> Result[FromTo_ToFrom, ValueError]:
    """Get line susceptance 'b' value as FromTo_ToFrom."""
    b_value = getattr(component, "b", None)
    if b_value is None:
        b_value = 0.0
    return Ok(FromTo_ToFrom(from_to=float(b_value), to_from=float(b_value)))


@getter
def get_line_rating(component: ReEDSTransmissionLine, context: PluginContext):
    """Use max_active_power.from_to as the line rating."""
    try:
        return Ok(component.max_active_power.from_to)
    except Exception as e:
        return Err(ValueError(f"Could not get line rating: {e}"))


@getter
def get_line_active_power_flow(component: ReEDSTransmissionLine, context: PluginContext):
    """Use max_active_power.from_to as the active power flow."""
    try:
        return Ok(component.max_active_power.from_to)
    except Exception as e:
        return Err(ValueError(f"Could not get active_power_flow: {e}"))


@getter
def get_line_reactive_power_flow(component: ReEDSTransmissionLine, context: PluginContext):
    """Return reactive_power_flow or 0.0 if not available."""
    return Ok(float(getattr(component, "reactive_power_flow", 0.0) or 0.0))


@getter
def get_line_angle_limits(component: ReEDSTransmissionLine, context: PluginContext):
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
def get_arc_for_line(component: ReEDSTransmissionLine, context: PluginContext):
    import re

    arc_name_str = getattr(component, "name", "")
    match = re.match(r"(p\d+)_((p\d+)_)?(ac|dc)", arc_name_str)
    if match:
        from_region_name = match.group(1)
        to_region_name = match.group(3) if match.group(3) else None
    else:
        from_region_name = getattr(getattr(component.interface, "from_region", None), "name", None)
        to_region_name = getattr(getattr(component.interface, "to_region", None), "name", None)

    if not from_region_name or not to_region_name:
        from_region_name = getattr(getattr(component.interface, "from_region", None), "name", None)
        to_region_name = getattr(getattr(component.interface, "to_region", None), "name", None)

    # Find buses by area name (region name)
    from_bus_obj = None
    to_bus_obj = None
    for bus in context.target_system.get_components(ACBus):
        if getattr(getattr(bus, "area", None), "name", None) == from_region_name:
            from_bus_obj = bus
        if getattr(getattr(bus, "area", None), "name", None) == to_region_name:
            to_bus_obj = bus

    if from_bus_obj is None or to_bus_obj is None:
        return Err(ValueError(f"ACBus not found for Arc: from={from_region_name}, to={to_region_name}"))

    # Check for existing Arc between these buses (in either direction)
    for arc in context.target_system.get_components(Arc):
        if (arc.from_to == from_bus_obj and arc.to_from == to_bus_obj) or (
            arc.from_to == to_bus_obj and arc.to_from == from_bus_obj
        ):
            return Ok(arc)  # Return the existing Arc

    arc_name = f"{arc_name_str}__{getattr(component, 'uuid', '')}"

    try:
        arc = Arc(name=arc_name, from_to=from_bus_obj, to_from=to_bus_obj)
        return Ok(arc)
    except Exception as e:
        return Err(ValueError(f"Could not create Arc: {e}"))


@getter
def get_capacity_as_rating(
    component: ReEDSThermalGenerator | ReEDSVariableGenerator, context: PluginContext
) -> Result[float | int, ValueError]:
    """Map ReEDS capacity (MW) to Sienna rating/base_power fields."""
    capacity = getattr(component, "capacity", None)
    if capacity is None:
        return _ok_num(0.0)
    return _ok_num(float(capacity))


@getter
def get_capacity_as_base_power(
    component: ReEDSThermalGenerator | ReEDSVariableGenerator, context: PluginContext
) -> Result[float | int, ValueError]:
    """Alias to reuse rating getter for base_power."""
    capacity = getattr(component, "capacity", None)
    if capacity is None:
        return _ok_num(0.0)
    return _ok_num(float(capacity))


@getter
def get_active_power_limits(
    component: ReEDSThermalGenerator,
    context: PluginContext,
) -> Result[MinMax, ValueError]:
    """Create a MinMax limit using capacity as the max."""
    capacity = getattr(component, "capacity", 0.0)
    return Ok(MinMax(min=0.0, max=float(capacity)))


@getter
def get_thermal_operation_cost(
    component: ReEDSThermalGenerator,
    context: PluginContext,
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
    component: ReEDSVariableGenerator, context: PluginContext
) -> Result[RenewableGenerationCost, ValueError]:
    """Return zeroed renewable operation cost."""
    zero_curve = CostCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS)
    return Ok(
        RenewableGenerationCost(
            fixed=0.0,
            variable=zero_curve,
            curtailment_cost=zero_curve,
        )
    )


@getter
def get_prime_mover(
    component: ReEDSThermalGenerator,
    context: PluginContext,
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
    component: ReEDSThermalGenerator,
    context: PluginContext,
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
    component: ReEDSVariableGenerator, context: PluginContext
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
def get_load_base_power(component: ReEDSDemand, context: PluginContext) -> Result[float | int, ValueError]:
    """Return a default load base power of 100.0 MVA."""
    return _ok_num(100.0)


@getter
def get_zero_active_power(component: object, context: PluginContext) -> Result[float | int, ValueError]:
    """Return zero active power placeholder."""
    return _ok_num(0.0)


@getter
def get_zero_reactive_power(component: object, context: PluginContext) -> Result[float | int, ValueError]:
    """Return zero reactive power placeholder."""
    return _ok_num(0.0)


@getter
def get_default_must_run(
    component: ReEDSThermalGenerator, context: PluginContext
) -> Result[bool, ValueError]:
    """Return default must_run flag."""
    return Ok(False)


@getter
def get_default_status(component: ReEDSThermalGenerator, context: PluginContext) -> Result[bool, ValueError]:
    """Return default online status."""
    return Ok(True)


@getter
def get_default_time_at_status(
    component: ReEDSThermalGenerator | ReEDSHydroGenerator, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return zeroed time_at_status."""
    return _ok_num(0.0)


@getter
def get_area_from(component: ReEDSInterface, context: PluginContext) -> Result[Area, ValueError]:
    """Resolve the source Area for an interchange."""
    from r2x_sienna.models import Area

    target_areas = list(context.target_system.get_components(Area))
    name = getattr(getattr(component, "from_region", None), "name", None)
    for area in target_areas:
        if getattr(area, "name", None) == name:
            return cast(Result[Area, ValueError], Ok(area))
    return Err(ValueError(f"No Area found for from_region {name}"))


@getter
def get_area_to(component: ReEDSInterface, context: PluginContext) -> Result[Area, ValueError]:
    """Resolve the destination Area for an interchange."""
    from r2x_sienna.models import Area

    target_areas = list(context.target_system.get_components(Area))
    name = getattr(getattr(component, "to_region", None), "name", None)
    for area in target_areas:
        if getattr(area, "name", None) == name:
            return cast(Result[Area, ValueError], Ok(area))
    return Err(ValueError(f"No Area found for to_region {name}"))


@getter
def get_reserve_time_frame(component: ReEDSReserve, context: PluginContext) -> Result[float, ValueError]:
    """Get the reserve time frame in seconds."""
    return Ok(float(getattr(component, "time_frame", 0.0) or 0.0))


@getter
def get_reserve_requirement(
    component: ReEDSReserve, context: PluginContext
) -> Result[float | None, ValueError]:
    """Get the reserve requirement in p.u (SYSTEM_BASE)."""
    return Ok(getattr(component, "requirement", 0.0))


@getter
def get_reserve_sustained_time(component: ReEDSReserve, context: PluginContext) -> Result[float, ValueError]:
    """Get the sustained time in seconds."""
    return Ok(float(getattr(component, "duration", 3600.0) or 3600.0))


@getter
def get_reserve_max_output_fraction(
    component: ReEDSReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get the max output fraction [0, 1.0]."""
    return Ok(float(getattr(component, "max_output_fraction", 1.0) or 1.0))


@getter
def get_reserve_max_participation_factor(
    component: ReEDSReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get the max participation factor [0, 1.0]."""
    return Ok(float(getattr(component, "max_participation_factor", 1.0) or 1.0))


@getter
def get_reserve_deployed_fraction(
    component: ReEDSReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get the deployed fraction [0, 1.0]."""
    return Ok(float(getattr(component, "deployed_fraction", 1.0) or 1.0))


@getter
def get_reserve_type(component: ReEDSReserve, context: PluginContext) -> Result[str, ValueError]:
    """Get the reserve type (e.g., 'SPINNING', 'REGULATION')."""
    return Ok(getattr(component, "reserve_type", "SPINNING"))


@getter
def get_reserve_direction(component: ReEDSReserve, context: PluginContext) -> Result[str, ValueError]:
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
def get_interface_flow_limits(
    component: ReEDSInterface, context: PluginContext
) -> Result[FromTo_ToFrom, ValueError]:
    """Provide zeroed flow limits placeholder."""
    return Ok(FromTo_ToFrom(from_to=0.0, to_from=0.0))


@getter
def get_zero_flow(component: ReEDSInterface, context: PluginContext) -> Result[float | int, ValueError]:
    """Return zero flow for interchange defaults."""
    return _ok_num(0.0)


@getter
def get_area_for_region(component: ReEDSRegion, context: PluginContext) -> Result[Area, ValueError]:
    """Resolve Area for a region."""
    area = _lookup_area(context, getattr(component, "name", None))
    if area is None:
        return Err(ValueError("Area not found for region"))
    return Ok(area)


@getter
def bus_name_from_region(component: ReEDSRegion, context: PluginContext) -> Result[str, ValueError]:
    """Derive a bus name from the region."""
    return Ok(f"{getattr(component, 'name', 'REG')}_BUS")


@getter
def get_bus_for_region(component: object, context: PluginContext) -> Result[ACBus, ValueError]:
    """
    Find the bus corresponding to the component's region.
    First tries to use the region attribute, then falls back to name extraction.
    """
    from r2x_sienna.models import ACBus

    # Try to get region directly from component
    region = getattr(component, "region", None)
    if region:
        region_name = getattr(region, "name", None)
        bus_name = f"{region_name}_BUS"
    else:
        import re

        name = getattr(component, "name", "")
        match = re.search(r"(p\d+)", name)
        region_name = match.group(1) if match else None
        bus_name = f"{region_name}_BUS" if region_name else None

    if not bus_name:
        return Err(ValueError("Could not determine region for component"))

    for bus in context.target_system.get_components(ACBus):
        if getattr(bus, "name", "") == bus_name:
            return Ok(bus)
    return Err(ValueError(f"No bus found with name {bus_name}"))


@getter
def get_bus_number(component: ReEDSRegion, context: PluginContext) -> Result[int, ValueError]:
    """
    Extract and return the bus number as an integer from the region name.

    - For regions like 'p60': extracts the number (60)
    - For non-numeric regions like 'otx', 'oms', 'ola': assigns a sequential number starting at 999999
    """
    global _NEXT_AVAILABLE_BUS_NUMBER
    import re

    name = getattr(component, "name", "")

    match = re.match(r"[a-z](\d+)", name)
    if match:
        return Ok(int(match.group(1)))

    if name not in _NON_NUMERIC_REGION_BUS_NUMBERS:
        _NON_NUMERIC_REGION_BUS_NUMBERS[name] = _NEXT_AVAILABLE_BUS_NUMBER
        _NEXT_AVAILABLE_BUS_NUMBER += 1

    return Ok(_NON_NUMERIC_REGION_BUS_NUMBERS[name])


@getter
def get_area_category(component: ReEDSRegion, context: PluginContext) -> Result[str, ValueError]:
    """Get category for Area, defaulting to 'region'."""
    category = getattr(component, "category", None)
    return Ok(category if category else "region")


@getter
def base_voltage_default(component: ReEDSRegion, context: PluginContext) -> Result[float | int, ValueError]:
    """Provide default base voltage in kV."""
    return _ok_num(float(ureg.Quantity(115.0, "kV").magnitude))  # magnitude only to avoid unit issues


@getter
def get_default_magnitude(component: ReEDSRegion, context: PluginContext) -> Result[float | int, ValueError]:
    """Default bus voltage magnitude."""
    return _ok_num(1.0)


@getter
def get_default_angle(component: ReEDSRegion, context: PluginContext) -> Result[float | int, ValueError]:
    """Default bus voltage angle."""
    return _ok_num(0.0)


@getter
def bustype_default(component: ReEDSRegion, context: PluginContext) -> Result[ACBusTypes, ValueError]:
    """Default bus type."""
    return Ok(ACBusTypes.PQ)


@getter
def demand_max_active_power(
    component: ReEDSDemand, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return demand max active power."""
    return _ok_num(float(getattr(component, "max_active_power", 0.0) or 0.0))


@getter
def demand_max_reactive_power(
    component: ReEDSDemand, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return zero reactive power."""
    return _ok_num(0.0)


@getter
def hydro_rating(component: ReEDSHydroGenerator, context: PluginContext) -> Result[float | int, ValueError]:  # type: ignore[name-defined]
    """Map capacity to rating/base_power."""
    return _ok_num(float(getattr(component, "capacity", 0.0) or 0.0))


@getter
def hydro_active_power_limits(
    component: ReEDSHydroGenerator, context: PluginContext
) -> Result[MinMax, ValueError]:  # type: ignore[name-defined]
    """Min/max active power limits for hydro."""
    cap = float(getattr(component, "capacity", 0.0) or 0.0)
    return Ok(MinMax(min=0.0, max=cap))


@getter
def hydro_ramp_limits(component: ReEDSHydroGenerator, context: PluginContext) -> Result[UpDown, ValueError]:
    """Min/max ramp limits for hydro."""
    cap = float(getattr(component, "capacity", 0.0) or 0.0)
    ramp_rate = float(getattr(component, "ramp_rate", 0.0) or 0.0)
    ramp_limit = cap * ramp_rate / 100.0
    return Ok(UpDown(up=ramp_limit, down=ramp_limit))


@getter
def hydro_time_limits(component: ReEDSHydroGenerator, context: PluginContext) -> Result[MinMax, ValueError]:
    """Min/max time limits for hydro."""
    min_up_time = float(getattr(component, "min_up_time", 0.0) or 0.0)
    min_down_time = float(getattr(component, "min_down_time", 0.0) or 0.0)
    return Ok(UpDown(up=min_up_time, down=min_down_time))


@getter
def hydro_operation_cost(
    component: ReEDSHydroGenerator, context: PluginContext
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
def storage_rating(component: ReEDSStorage, context: PluginContext) -> Result[float | int, ValueError]:
    """Use capacity as rating/base power for storage."""
    return _ok_num(float(getattr(component, "capacity", 0.0) or 0.0))


@getter
def storage_capacity_mwh(component: ReEDSStorage, context: PluginContext) -> Result[float | int, ValueError]:
    """Energy capacity from explicit value or duration * power."""
    energy = getattr(component, "energy_capacity", None)
    if energy is not None:
        return _ok_num(float(energy))
    capacity = float(getattr(component, "capacity", 0.0) or 0.0)
    duration = float(getattr(component, "storage_duration", 0.0) or 0.0)
    return _ok_num(capacity * duration)


@getter
def storage_level_limits(component: ReEDSStorage, context: PluginContext) -> Result[MinMax, ValueError]:
    """Always return storage level limits as a normalized fraction (0.0 to 1.0)."""
    return Ok(MinMax(min=0.0, max=1.0))


@getter
def storage_power_limits(component: ReEDSStorage, context: PluginContext) -> Result[MinMax, ValueError]:
    """Charge/discharge limits from capacity."""
    cap = float(getattr(component, "capacity", 0.0) or 0.0)
    return Ok(MinMax(min=0.0, max=cap))


@getter
def storage_efficiency(component: ReEDSStorage, context: PluginContext) -> Result[InputOutput, ValueError]:
    """Map round-trip efficiency to input/output pair."""
    default_eff = 0.95
    rte = float(getattr(component, "round_trip_efficiency", default_eff) or default_eff)
    return Ok(InputOutput(input=default_eff, output=rte))


@getter
def storage_prime_mover(
    component: ReEDSStorage, context: PluginContext
) -> Result[PrimeMoversType, ValueError]:
    """Default storage prime mover."""
    return Ok(PrimeMoversType.ES)


@getter
def storage_tech(component: ReEDSStorage, context: PluginContext) -> Result[StorageTechs, ValueError]:
    """Map storage technology string to enum."""
    tech = (getattr(component, "technology", "") or "").lower()
    if "bat" in tech or "lib" in tech:
        return Ok(StorageTechs.LIB)
    return Ok(StorageTechs.OTHER_MECH)


@getter
def storage_initial_level(component: ReEDSStorage, context: PluginContext) -> Result[float | int, ValueError]:
    """Initial storage level as fraction."""
    return _ok_num(0.0)


@getter
def storage_conversion_factor(
    component: ReEDSStorage, context: PluginContext
) -> Result[float | int, ValueError]:
    """Default conversion factor."""
    return _ok_num(1.0)
