"""Getter helpers for ReEDS to Sienna translation rules."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING, Any, cast

from infrasys.cost_curves import CostCurve, FuelCurve, LinearCurve
from infrasys.cost_curves import UnitSystem as InfraUnitSystem
from r2x_sienna.models import ACBus, Arc
from r2x_sienna.models.costs import HydroGenerationCost, RenewableGenerationCost, ThermalGenerationCost
from r2x_sienna.models.enums import ACBusTypes, PrimeMoversType, StorageTechs, ThermalFuels
from r2x_sienna.models.named_tuples import FromTo_ToFrom, InputOutput, MinMax, UpDown
from r2x_sienna.units import ureg

from r2x_core import Err, Ok, Result
from r2x_core.getters import getter

if TYPE_CHECKING:
    from r2x_reeds.models import (
        ReEDSConsumingTechnology,
        ReEDSDataCenterDemand,
        ReEDSDemand,
        ReEDSElectrolyzerDemand,
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


def _get_defaults(technology: str, key: str) -> float:
    """Look up a pcm_defaults value for a given technology and key.

    Applies prefix normalisation identical to the reeds-to-plexos helper so that,
    e.g., ``battery_4`` resolves to the ``battery`` bucket.
    """
    prefixes = ("battery", "csp", "wind-ons", "wind-ofs", "geohydro_allkm", "egs_nearfield", "egs")
    tech_lower = technology.lower()
    normalised = tech_lower
    for prefix in prefixes:
        if tech_lower.startswith(prefix):
            normalised = prefix
            break
    defaults = _load_defaults_json()
    value = defaults.get("pcm_defaults", {}).get(normalised, {}).get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@cache
def _load_defaults_json() -> dict[str, Any]:
    """Load and cache defaults.json (parsed once per process)."""
    defaults_path = files("r2x_reeds_to_sienna.config") / "defaults.json"
    with defaults_path.open() as f:
        return json.load(f)


def _ok_num(val: float | int) -> Result[float | int, ValueError]:
    """Typed Ok wrapper for numeric Result returns."""
    return cast(Result[float | int, ValueError], Ok(val))


def _target_system(context: PluginContext) -> Any:
    return cast(Any, context.target_system)


def _lookup_area(context: PluginContext, name: str | None) -> Area | None:
    """Helper to find a target Area by name."""
    from r2x_sienna.models import Area

    for area in _target_system(context).get_components(Area):
        if getattr(area, "name", None) == name:
            return area
    return None


@getter
def get_component_ext(component: object, context: PluginContext) -> Result[dict, ValueError]:
    """
    Get the component's ext dict, storing the technology name under the 'technology' key
    and the ReEDS line type under the 'reeds_line_type' key.
    """
    ext = getattr(component, "ext", None)
    if ext is None:
        ext = {}
    elif not isinstance(ext, dict):
        return Err(ValueError("Component ext attribute is not a dict"))

    ext = dict(ext)
    technology = getattr(component, "technology", None)
    if technology is not None:
        ext["technology"] = technology

    line_type = getattr(component, "line_type", None)
    if line_type is not None:
        ext["reeds_line_type"] = line_type

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
    existing_names = {
        getattr(c, "name", None) for c in _target_system(context).get_components(ThermalStandard)
    }
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
def get_monitored_line_rating(component: ReEDSTransmissionLine, context: PluginContext):
    """Use the larger directional limit as the line rating."""
    try:
        return Ok(max(component.max_active_power.from_to, component.max_active_power.to_from))
    except Exception as e:
        return Err(ValueError(f"Could not get line rating: {e}"))


@getter
def get_line_flow_limits(
    component: ReEDSTransmissionLine, context: PluginContext
) -> Result[FromTo_ToFrom, ValueError]:
    """Map ReEDS directional capacities to Sienna flow limits.

    ReEDS transmission parsing stores the source ``r -> rr`` capacity in
    ``max_active_power.to_from`` and the reverse capacity in
    ``max_active_power.from_to``.
    """
    try:
        return Ok(
            FromTo_ToFrom(
                from_to=component.max_active_power.to_from,
                to_from=component.max_active_power.from_to,
            )
        )
    except Exception as e:
        return Err(ValueError(f"Could not get line flow limits: {e}"))


@getter
def get_hvdc_active_power_limits_from(
    component: ReEDSTransmissionLine, context: PluginContext
) -> Result[MinMax, ValueError]:
    """Map directional ReEDS capacities to the HVDC from-terminal limits."""
    try:
        forward = component.max_active_power.to_from
        backward = component.max_active_power.from_to
        return Ok(MinMax(min=-backward, max=forward))
    except Exception as e:
        return Err(ValueError(f"Could not get HVDC from-terminal limits: {e}"))


@getter
def get_hvdc_active_power_limits_to(
    component: ReEDSTransmissionLine, context: PluginContext
) -> Result[MinMax, ValueError]:
    """Map directional ReEDS capacities to the HVDC to-terminal limits."""
    try:
        forward = component.max_active_power.to_from
        backward = component.max_active_power.from_to
        return Ok(MinMax(min=-forward, max=backward))
    except Exception as e:
        return Err(ValueError(f"Could not get HVDC to-terminal limits: {e}"))


@getter
def get_hvdc_reactive_power_limits(
    component: ReEDSTransmissionLine, context: PluginContext
) -> Result[MinMax, ValueError]:
    """Use zero reactive power limits because ReEDS does not provide them."""
    return Ok(MinMax(min=0.0, max=0.0))


@getter
def get_hvdc_loss(component: ReEDSTransmissionLine, context: PluginContext):
    """Represent the ReEDS transmission loss fraction as a linear loss curve."""
    return Ok(LinearCurve(float(component.losses or 0.0)))


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
    for bus in _target_system(context).get_components(ACBus):
        if getattr(getattr(bus, "area", None), "name", None) == from_region_name:
            from_bus_obj = bus
        if getattr(getattr(bus, "area", None), "name", None) == to_region_name:
            to_bus_obj = bus

    if from_bus_obj is None or to_bus_obj is None:
        return Err(ValueError(f"ACBus not found for Arc: from={from_region_name}, to={to_region_name}"))

    # Check for existing Arc between these buses (in either direction)
    for arc in _target_system(context).get_components(Arc):
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
    """Create a MinMax limit using capacity as max and min_stable_level * capacity as min.

    Falls back to ``min_stable_level_percentage`` from defaults.json when the
    source field is not populated.
    """
    capacity = float(getattr(component, "capacity", 0.0) or 0.0)
    min_stable = getattr(component, "min_stable_level", None)
    if min_stable is not None:
        min_mw = float(min_stable) * capacity
    else:
        technology = getattr(component, "technology", "")
        default_frac = _get_defaults(technology, "min_stable_level_percentage")
        min_mw = default_frac * capacity
    return Ok(MinMax(min=min_mw, max=capacity))


@getter
def get_thermal_operation_cost(
    component: ReEDSThermalGenerator,
    context: PluginContext,
) -> Result[ThermalGenerationCost, ValueError]:
    """Build thermal operation cost from heat_rate, fuel_price, vom_cost, and startup_cost.

    Falls back to ``start_cost_per_MW`` from defaults.json when ``startup_cost`` is not set.
    """
    heat_rate = float(getattr(component, "heat_rate", 0.0) or 0.0)
    fuel_price = float(getattr(component, "fuel_price", 0.0) or 0.0)
    vom_cost = float(getattr(component, "vom_cost", 0.0) or 0.0)
    startup_cost_per_mw = getattr(component, "startup_cost", None)
    capacity = float(getattr(component, "capacity", 0.0) or 0.0)
    if startup_cost_per_mw is None:
        technology = getattr(component, "technology", "")
        startup_cost_per_mw = _get_defaults(technology, "start_cost_per_MW")
    start_up = float(startup_cost_per_mw) * capacity

    return Ok(
        ThermalGenerationCost(
            fixed=0.0,
            shut_down=0.0,
            start_up=start_up,
            variable=FuelCurve(
                value_curve=LinearCurve(heat_rate),
                power_units=InfraUnitSystem.NATURAL_UNITS,
                fuel_cost=fuel_price,
                vom_cost=LinearCurve(vom_cost),
            ),
        )
    )


@getter
def get_renewable_operation_cost(
    component: ReEDSVariableGenerator, context: PluginContext
) -> Result[RenewableGenerationCost, ValueError]:
    """Return zeroed renewable operation cost."""
    zero_curve = CostCurve(value_curve=LinearCurve(0.0), power_units=InfraUnitSystem.NATURAL_UNITS)
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
def get_hydro_prime_mover(
    component: ReEDSHydroGenerator, context: PluginContext
) -> Result[PrimeMoversType, ValueError]:
    """Always return HY (hydro) as the prime mover for hydro generators."""
    return Ok(PrimeMoversType.HY)


@getter
def get_load_base_power(component: ReEDSDemand, context: PluginContext) -> Result[float | int, ValueError]:
    """Return a default load base power of 100.0 MVA."""
    return _ok_num(100.0)


@getter
def get_consuming_tech_max_active_power(
    component: ReEDSElectrolyzerDemand | ReEDSDataCenterDemand, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return max_active_power for consuming technologies.

    Prefers an explicit ``max_active_power`` field when set, then falls back to
    ``capacity``, and finally returns 0.0 if neither is available.
    """
    max_ap = getattr(component, "max_active_power", None)
    if max_ap is not None:
        return _ok_num(float(max_ap))
    capacity = getattr(component, "capacity", None)
    if capacity is not None:
        return _ok_num(float(capacity))
    return _ok_num(0.0)


@getter
def get_consuming_tech_base_power(
    component: ReEDSElectrolyzerDemand | ReEDSDataCenterDemand, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return capacity as base_power for consuming technologies.

    Falls back to 100.0 MVA if capacity is missing.
    """
    capacity = getattr(component, "capacity", None)
    if capacity is not None:
        return _ok_num(float(capacity))
    return _ok_num(100.0)


@getter
def get_gen_services(component: object, context: PluginContext) -> Result[list, ValueError]:
    """Return the list of reserve service objects the generator participates in.

    Reads reserve names from ``ext['reserves']`` and looks up each already-
    translated reserve service in the target system.  Both ``VariableReserve``
    and ``VariableReserveNonSpinning`` are searched so that NON_SPINNING
    reserves (which map to the latter) are correctly attached.  Reserves that
    have not been translated yet are silently skipped.  Works for all generator
    types.
    """
    from r2x_sienna.models import VariableReserve, VariableReserveNonSpinning

    ext = getattr(component, "ext", {}) or {}
    reserve_names: list[str] = ext.get("reserves", []) or []
    if not reserve_names:
        return Ok([])

    reserves_by_name: dict[str, object] = {}
    for cls in (VariableReserve, VariableReserveNonSpinning):
        for r in _target_system(context).get_components(cls):
            reserves_by_name[r.name] = r
    return Ok([reserves_by_name[n] for n in reserve_names if n in reserves_by_name])


@getter
def get_thermal_active_power(
    component: ReEDSThermalGenerator,
    context: PluginContext,
) -> Result[float | int, ValueError]:
    """Return the generator capacity as initial active power dispatch."""
    capacity = getattr(component, "capacity", None)
    if capacity is None:
        return _ok_num(0.0)
    return _ok_num(float(capacity))


@getter
def get_zero_active_power(component: object, context: PluginContext) -> Result[float | int, ValueError]:
    """Return zero active power placeholder."""
    return _ok_num(0.0)


@getter
def get_zero_reactive_power(component: object, context: PluginContext) -> Result[float | int, ValueError]:
    """Return zero reactive power placeholder."""
    return _ok_num(0.0)


@getter
def get_zero_reactive_power_limits(component: object, context: PluginContext) -> Result[MinMax, ValueError]:
    """Return zeroed reactive power limits for components with no reactive power data from source."""
    return Ok(MinMax(min=0.0, max=0.0))


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
def thermal_ramp_limits(
    component: ReEDSThermalGenerator, context: PluginContext
) -> Result[UpDown | None, ValueError]:
    """Convert ramp_rate (fraction/hour) to MW/min for Sienna ramp_limits.

    Falls back to ``max_ramp_up_percentage`` from defaults.json (fraction of capacity
    per hour) when the source field is not populated. Returns None only if both the
    source field and the default are zero.
    """
    ramp_rate = getattr(component, "ramp_rate", None)
    capacity = float(getattr(component, "capacity", 0.0) or 0.0)
    if ramp_rate is None:
        technology = getattr(component, "technology", "")
        ramp_rate = _get_defaults(technology, "max_ramp_up_percentage")
        if not ramp_rate:
            return Ok(None)
    ramp_mw_per_min = float(ramp_rate) * capacity / 60.0
    return Ok(UpDown(up=ramp_mw_per_min, down=ramp_mw_per_min))


@getter
def thermal_time_limits(
    component: ReEDSThermalGenerator, context: PluginContext
) -> Result[UpDown | None, ValueError]:
    """Map min_up_time / min_down_time (hours) to Sienna UpDown time_limits.

    Falls back to ``min_up_time`` / ``min_down_time`` from defaults.json.
    Returns None only when both resolved values are zero.
    """
    min_up = getattr(component, "min_up_time", None)
    min_down = getattr(component, "min_down_time", None)
    technology = getattr(component, "technology", "")
    if min_up is None:
        min_up = _get_defaults(technology, "min_up_time") or None
    if min_down is None:
        min_down = _get_defaults(technology, "min_down_time") or None
    if min_up is None and min_down is None:
        return Ok(None)
    return Ok(UpDown(up=float(min_up or 0.0), down=float(min_down or 0.0)))


@getter
def get_area_from(component: ReEDSInterface, context: PluginContext) -> Result[Area, ValueError]:
    """Resolve the source Area for an interchange."""
    from r2x_sienna.models import Area

    target_areas = list(_target_system(context).get_components(Area))
    name = getattr(getattr(component, "from_region", None), "name", None)
    for area in target_areas:
        if getattr(area, "name", None) == name:
            return cast(Result[Area, ValueError], Ok(area))
    return Err(ValueError(f"No Area found for from_region {name}"))


@getter
def get_area_to(component: ReEDSInterface, context: PluginContext) -> Result[Area, ValueError]:
    """Resolve the destination Area for an interchange."""
    from r2x_sienna.models import Area

    target_areas = list(_target_system(context).get_components(Area))
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

    for bus in _target_system(context).get_components(ACBus):
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
def hydro_rating(component: ReEDSHydroGenerator, context: PluginContext) -> Result[float | int, ValueError]:
    """Map capacity to rating/base_power."""
    return _ok_num(float(getattr(component, "capacity", 0.0) or 0.0))


@getter
def hydro_active_power_limits(
    component: ReEDSHydroGenerator, context: PluginContext
) -> Result[MinMax, ValueError]:
    """Min/max active power limits for hydro."""
    cap = float(getattr(component, "capacity", 0.0) or 0.0)
    return Ok(MinMax(min=0.0, max=cap))


@getter
def hydro_ramp_limits(component: ReEDSHydroGenerator, context: PluginContext) -> Result[UpDown, ValueError]:
    """Convert ramp_rate (fraction/hour) to MW/min for Sienna ramp_limits.

    Falls back to ``max_ramp_up_percentage`` from defaults.json when the source
    field is not populated.
    """
    cap = float(getattr(component, "capacity", 0.0) or 0.0)
    ramp_rate = getattr(component, "ramp_rate", None)
    if ramp_rate is None:
        technology = getattr(component, "technology", "")
        ramp_rate = _get_defaults(technology, "max_ramp_up_percentage") or 0.0
    ramp_limit = cap * float(ramp_rate) / 60.0
    return Ok(UpDown(up=ramp_limit, down=ramp_limit))


@getter
def hydro_time_limits(component: ReEDSHydroGenerator, context: PluginContext) -> Result[UpDown, ValueError]:
    """Min/max time limits for hydro."""
    min_up_time = float(getattr(component, "min_up_time", 0.0) or 0.0)
    min_down_time = float(getattr(component, "min_down_time", 0.0) or 0.0)
    return Ok(UpDown(up=min_up_time, down=min_down_time))


@getter
def hydro_operation_cost(
    component: ReEDSHydroGenerator, context: PluginContext
) -> Result[HydroGenerationCost, ValueError]:
    """Return zeroed hydro cost."""
    from r2x_sienna.models.costs import HydroGenerationCost

    return Ok(
        HydroGenerationCost(
            fixed=0.0,
            variable=CostCurve(
                value_curve=LinearCurve(10),
                power_units=InfraUnitSystem.NATURAL_UNITS,
                vom_cost=LinearCurve(5.0),
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
    """Map round-trip efficiency to symmetric input/output pair.

    Splits the round-trip efficiency as sqrt(rte) for both charge and discharge,
    so input * output = rte.
    """
    import math

    default_eff = 0.95
    rte = float(getattr(component, "round_trip_efficiency", default_eff) or default_eff)
    one_side = math.sqrt(max(rte, 0.0))
    return Ok(InputOutput(input=one_side, output=one_side))


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


@getter
def consuming_capacity_as_max_power(
    component: ReEDSConsumingTechnology, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return the consuming technology capacity (MW) as max_active_power."""
    return _ok_num(float(getattr(component, "capacity", 0.0) or 0.0))


@getter
def consuming_capacity_as_base_power(
    component: ReEDSConsumingTechnology, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return the consuming technology capacity (MW) as base_power."""
    return _ok_num(float(getattr(component, "capacity", 0.0) or 0.0))
