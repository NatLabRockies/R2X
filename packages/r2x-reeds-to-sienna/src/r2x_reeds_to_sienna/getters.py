"""Getter helpers for ReEDS to Sienna translation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from r2x_sienna.models import ACBus
from r2x_sienna.models.costs import HydroGenerationCost, RenewableGenerationCost, ThermalGenerationCost
from r2x_sienna.models.enums import ACBusTypes, PrimeMoversType, StorageTechs, ThermalFuels
from r2x_sienna.models.named_tuples import FromTo_ToFrom, InputOutput, MinMax
from r2x_sienna.units import ureg

from r2x_core import Err, Ok, Result
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
    return Ok(ThermalGenerationCost())


@getter
def get_renewable_operation_cost(
    _: TranslationContext, __: ReEDSVariableGenerator
) -> Result[RenewableGenerationCost, ValueError]:
    """Return zeroed renewable operation cost."""
    return Ok(RenewableGenerationCost())


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
    """Provide default bus number."""
    return Ok(component.name[1:])


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
def hydro_operation_cost(
    _: TranslationContext, __: ReEDSHydroGenerator
) -> Result[HydroGenerationCost, ValueError]:  # type: ignore[name-defined]
    """Return zeroed hydro cost."""
    from r2x_sienna.models.costs import HydroGenerationCost

    return Ok(HydroGenerationCost())


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
def get_from_bus_for_line(context: TranslationContext, component):
    """Get the from_bus for a line based on its interface."""
    try:
        bus_name = f"{component.interface.from_region.name}_BUS"
        for bus in context.target_system.get_components(ACBus):
            if getattr(bus, "name", None) == bus_name:
                return Ok(bus)
        return Err(ValueError(f"ACBus '{bus_name}' not found for from_bus"))
    except Exception as e:
        return Err(ValueError(f"Could not get from_bus: {e}"))


@getter
def get_to_bus_for_line(context: TranslationContext, component):
    """Get the to_bus for a line based on its interface."""
    try:
        bus_name = f"{component.interface.to_region.name}_BUS"
        for bus in context.target_system.get_components(ACBus):
            if getattr(bus, "name", None) == bus_name:
                return Ok(bus)
        return Err(ValueError(f"ACBus '{bus_name}' not found for to_bus"))
    except Exception as e:
        return Err(ValueError(f"Could not get to_bus: {e}"))


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
