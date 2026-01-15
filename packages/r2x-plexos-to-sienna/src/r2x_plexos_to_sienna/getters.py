"""Getter functions for rules."""

from __future__ import annotations

import json
import re
import uuid
from importlib.resources import files
from typing import Any

from infrasys.cost_curves import CostCurve, FuelCurve
from infrasys.value_curves import InputOutputCurve, LinearCurve
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSReserve,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_sienna.models import ACBus, Arc, Area, LoadZone, VariableReserve
from r2x_sienna.models.costs import (
    HydroGenerationCost,
    HydroReservoirCost,
    RenewableGenerationCost,
    ThermalGenerationCost,
)
from r2x_sienna.models.enums import (
    ACBusTypes,
    PrimeMoversType,
    ReserveDirection,
    ReserveType,
    StorageTechs,
    ThermalFuels,
    TransformerControlObjective,
    WindingGroupNumber,
)
from r2x_sienna.models.named_tuples import Complex, FromTo_ToFrom, InputOutput, MinMax

from r2x_core import Ok, Result, TranslationContext, UnitSystem
from r2x_core.getters import getter


def extract_number_from_name(name: str) -> int | None:
    """Extract trailing digits from a string like 'p51191' or 'ACKRLNTC_9_1363'."""
    match = re.search(r"(\d+)$", name)
    if match:
        return int(match.group(1))
    return None


def _get_prime_mover_type(category: str) -> PrimeMoversType:
    defaults_path = files("r2x_plexos_to_sienna.config") / "defaults.json"
    with defaults_path.open() as f:
        defaults = json.load(f)
    code = defaults.get("prime_mover_types", {}).get(category, "OT")
    return getattr(PrimeMoversType, code, PrimeMoversType.OT)


@getter
def get_power_load_uuid(_: TranslationContext, component: PLEXOSRegion) -> Result[str, Any]:
    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{component.uuid}_load")))


@getter
def get_load_bus(context: TranslationContext, component: PLEXOSRegion) -> Result[ACBus | None, Any]:
    """
    Get the bus (ACBus) associated with the load region.

    Looks for a PLEXOSNode membership (collection=Region) and matches the node name to an ACBus.
    """
    memberships = context.source_system.get_supplemental_attributes_with_component(component)
    node_name = None
    for m in memberships:
        if (
            hasattr(m, "collection")
            and m.collection == CollectionEnum.Region
            and hasattr(m, "parent_object")
            and hasattr(m.parent_object, "name")
        ):
            node_name = m.parent_object.name
            break
    if node_name:
        acbuses = list(context.target_system.get_components(ACBus))
        bus = next((b for b in acbuses if getattr(b, "name", None) == node_name), None)
        return Ok(bus)
    return Ok(None)


@getter
def get_load_active_power(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the initial steady-state active power demand of the load in the region."""
    return Ok(getattr(component, "load", 0.0))


@getter
def get_load_reactive_power(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the reactive power of load at the bus (if available)."""
    return Ok(getattr(component, "reactive_power", 0.0))


@getter
def get_load_max_active_power(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the maximum active power demand of the load at the bus (if available)."""
    return Ok(getattr(component, "max_load", 0.0))


@getter
def get_load_max_reactive_power(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the maximum reactive power demand of the load at the bus (if available)."""
    return Ok(getattr(component, "max_reactive_power", 0.0))


@getter
def get_load_base_power(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the base power of the load at the bus (if available)."""
    return Ok(getattr(component, "base_power", 100.0))


@getter
def get_load_operation_cost(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the operation cost of the load at the bus (if available)."""
    return Ok(getattr(component, "operation_cost", None))


@getter
def get_zone_peak_active_power(_: TranslationContext, component: PLEXOSZone) -> Result[float, Any]:
    """Get the peak active power for a zone."""
    value = getattr(component, "peak_active_power", 0.0)
    return Ok(float(value))


@getter
def get_zone_peak_reactive_power(_: TranslationContext, component: PLEXOSZone) -> Result[float, Any]:
    """Get the peak reactive power for a zone."""
    value = getattr(component, "peak_reactive_power", 0.0)
    return Ok(float(value))


@getter
def get_node_angle(_: TranslationContext, component: PLEXOSNode) -> Result[float, Any]:
    """Get the angle of a node."""
    value = getattr(component, "angle", 0.0)
    return Ok(float(value))


@getter
def get_node_area(context: TranslationContext, component: PLEXOSNode) -> Result[Any, Any]:
    """Get the Area object of a node from its memberships (Region collection), matching by name in the target system."""
    memberships = context.source_system.get_supplemental_attributes_with_component(component)
    area_name = None
    for m in memberships:
        if (
            hasattr(m, "collection")
            and m.collection == CollectionEnum.Region
            and hasattr(m, "child_object")
            and hasattr(m.child_object, "name")
        ):
            area_name = m.child_object.name
            break
    if area_name:
        areas = list(context.target_system.get_components(Area))
        area_obj = next((a for a in areas if getattr(a, "name", None) == area_name), None)
        if area_obj:
            return Ok(area_obj)
    value = getattr(component, "area", None)
    return Ok(value)


@getter
def get_node_zone(context: TranslationContext, component: PLEXOSNode) -> Result[Any, Any]:
    """Get the LoadZone object of a node from its memberships (Zone collection), matching by name in the target system."""
    memberships = context.source_system.get_supplemental_attributes_with_component(component)
    zone_name = None
    for m in memberships:
        if (
            hasattr(m, "collection")
            and m.collection == CollectionEnum.Zone
            and hasattr(m, "child_object")
            and hasattr(m.child_object, "name")
        ):
            zone_name = m.child_object.name
            break
    if zone_name:
        zones = list(context.target_system.get_components(LoadZone))
        zone_obj = next((z for z in zones if getattr(z, "name", None) == zone_name), None)
        if zone_obj:
            return Ok(zone_obj)
    value = getattr(component, "zone", None)
    return Ok(value)


@getter
def get_base_voltage(_: TranslationContext, component: PLEXOSNode) -> Result[float, Any]:
    """Get the voltage of a node. Try 'voltage', then 'ac_voltage_magnitude', else default to 1.0."""
    voltage = getattr(component, "voltage", 0.0)
    if voltage and voltage != 0.0:
        return Ok(float(voltage))
    ac_voltage = getattr(component, "ac_voltage_magnitude", 0.0)
    if ac_voltage and ac_voltage != 0.0:
        return Ok(float(ac_voltage))
    return Ok(1.0)


@getter
def get_node_ext(_: TranslationContext, component: PLEXOSNode) -> Result[dict[str, Any], Any]:
    """Get the ext dictionary for a node."""
    value = {
        "load_participation_factor": getattr(component, "load_participation_factor", None),
    }
    return Ok(value)


@getter
def get_node_number(_: TranslationContext, component: PLEXOSNode) -> Result[int, Any]:
    """Assign node number from attribute, or extract from name if not present."""
    if hasattr(component, "number") and component.number is not None:
        return Ok(int(component.number))
    if hasattr(component, "name") and component.name:
        extracted = extract_number_from_name(component.name)
        if extracted is not None:
            return Ok(extracted)
    return Ok(1)


@getter
def is_slack_bus(_: TranslationContext, component: PLEXOSNode) -> Result[ACBusTypes, Any]:
    """Return ACBusTypes.SLACK if component.bustype == 1, else ACBusTypes.PQ."""
    value = getattr(component, "is_slack_bus", 0)
    bustype = ACBusTypes.SLACK if value == 1 else ACBusTypes.PQ
    return Ok(bustype)


@getter
def get_line_arc(context: TranslationContext, component: PLEXOSLine) -> Result[Arc, Any]:
    """Get the arc of a line by querying PlexosDB for node memberships and matching to ACBus objects."""
    memberships = context.source_system.get_supplemental_attributes_with_component(component)
    from_node = None
    to_node = None

    for m in memberships:
        if getattr(m, "collection", None) is not None:
            if m.collection == CollectionEnum.NodeFrom:
                from_node = getattr(m.child_object, "name", None)
            elif m.collection == CollectionEnum.NodeTo:
                to_node = getattr(m.child_object, "name", None)
        if from_node and to_node:
            break

    if not from_node or not to_node:
        raise ValueError(f"Could not find both nodes for line {component.name}. Memberships: {memberships}")

    acbuses = list(context.target_system.get_components(ACBus))
    from_bus = next((bus for bus in acbuses if getattr(bus, "name", None) == from_node), None)
    to_bus = next((bus for bus in acbuses if getattr(bus, "name", None) == to_node), None)

    if from_bus is None or to_bus is None:
        raise ValueError(
            f"Could not find ACBus for names: {from_node}, {to_node}. "
            f"Available: {[bus.name for bus in acbuses]}"
        )

    arc_sense = Arc(name=f"{from_node}-{to_node}", from_to=from_bus, to_from=to_bus)
    return Ok(arc_sense)


@getter
def get_line_conductance(_: TranslationContext, component: PLEXOSLine) -> Result[FromTo_ToFrom, Any]:
    """Get the conductance of a line as a FromTo_ToFrom namedtuple (g = 1/r)."""
    r = None
    if hasattr(component, "resistance") and component.resistance:
        if hasattr(component.resistance, "values") and component.resistance.values:
            r = float(component.resistance.values[0])
        else:
            r = float(component.resistance)
    if r and r != 0.0:
        g = 1.0 / r
        return Ok(FromTo_ToFrom(from_to=g, to_from=g))
    return Ok(FromTo_ToFrom(from_to=0.0, to_from=0.0))


@getter
def get_reactive_power_flow(_: TranslationContext, component: PLEXOSLine) -> Result[float, Any]:
    """Get the reactive power flow of a line as a FromTo_ToFrom namedtuple."""
    return Ok(0.0)


@getter
def get_line_angle_limits(_: TranslationContext, component: PLEXOSLine) -> Result[MinMax, Any]:
    """Get the angle limits of a line. Defaults to MinMax(-90.0, 90.0) if not found."""
    value = getattr(component, "angle_limits", None)
    if value is not None:
        if isinstance(value, MinMax):
            return Ok(value)
        if isinstance(value, tuple) and len(value) == 2:
            return Ok(MinMax(min=float(value[0]), max=float(value[1])))
    return Ok(MinMax(min=-90.0, max=90.0))


@getter
def get_line_susceptance(_: TranslationContext, component: PLEXOSLine) -> Result[FromTo_ToFrom, Any]:
    """Get the susceptance of a line as a FromTo_ToFrom namedtuple."""
    value = None
    if hasattr(component, "susceptance") and component.susceptance:
        if hasattr(component.susceptance, "values") and component.susceptance.values:
            value = float(component.susceptance.values[0])
        else:
            value = float(component.susceptance)
    if value is not None:
        return Ok(FromTo_ToFrom(from_to=value, to_from=value))
    return Ok(FromTo_ToFrom(from_to=0.0, to_from=0.0))


@getter
def get_line_flow_limits(_: TranslationContext, component: PLEXOSLine) -> Result[FromTo_ToFrom, Any]:
    """Get the flow limits (from_to, to_from) of a line as a FromTo_ToFrom namedtuple."""
    min_flow = getattr(component, "min_flow", -100.0)
    max_flow = getattr(component, "max_flow", None)
    if max_flow is not None:
        if hasattr(max_flow, "values") and max_flow.values:
            max_flow = float(max_flow.values[0])
        else:
            max_flow = float(max_flow)
    else:
        max_flow = 100.0
    return Ok(FromTo_ToFrom(from_to=max_flow, to_from=min_flow))


@getter
def get_line_losses(_: TranslationContext, component: PLEXOSLine) -> Result[float, Any]:
    """Get the losses of a line (if available)."""
    value = getattr(component, "losses", 0.0)
    if hasattr(value, "values") and value.values:
        value = float(value.values[0])
    return Ok(float(value))


@getter
def get_active_power_limits_from(_: TranslationContext, component: PLEXOSLine) -> Result[MinMax, Any]:
    """Get the active power limits (min, max) at the 'from' end of an HVDC line."""
    min_limit = getattr(component, "min_active_power_from", 0.0)
    max_limit = getattr(component, "max_active_power_from", 0.0)
    return Ok(MinMax(min=float(min_limit), max=float(max_limit)))


@getter
def get_active_power_limits_to(_: TranslationContext, component: PLEXOSLine) -> Result[MinMax, Any]:
    """Get the active power limits (min, max) at the 'to' end of an HVDC line."""
    min_limit = getattr(component, "min_active_power_to", 0.0)
    max_limit = getattr(component, "max_active_power_to", 0.0)
    return Ok(MinMax(min=float(min_limit), max=float(max_limit)))


@getter
def get_reactive_power_limits_from(_: TranslationContext, component: PLEXOSLine) -> Result[MinMax, Any]:
    """Get the reactive power limits (min, max) at the 'from' end of an HVDC line."""
    min_limit = getattr(component, "min_reactive_power_from", 0.0)
    max_limit = getattr(component, "max_reactive_power_from", 0.0)
    return Ok(MinMax(min=float(min_limit), max=float(max_limit)))


@getter
def get_reactive_power_limits_to(_: TranslationContext, component: PLEXOSLine) -> Result[MinMax, Any]:
    """Get the reactive power limits (min, max) at the 'to' end of an HVDC line."""
    min_limit = getattr(component, "min_reactive_power_to", 0.0)
    max_limit = getattr(component, "max_reactive_power_to", 0.0)
    return Ok(MinMax(min=float(min_limit), max=float(max_limit)))


@getter
def get_hvdc_line_loss(_: TranslationContext, component: PLEXOSLine) -> Result[InputOutputCurve, Any]:
    """Get the losses of an HVDC line as an InputOutputCurve (if available)."""
    loss_incr = getattr(component, "loss_incr", 0.0)
    return Ok(LinearCurve(loss_incr))


@getter
def get_gen_active_power(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the active power of a generator."""
    value = getattr(component, "max_capacity", 0.0)
    return Ok(float(value))


@getter
def get_device_services(
    context: TranslationContext, component: PLEXOSGenerator | PLEXOSBattery
) -> Result[list[Any], Any]:
    """
    Get the services provided by a device (generator, battery, etc.), returning VariableReserve objects from the target system.
    """
    services = []
    memberships = context.source_system.get_supplemental_attributes_with_component(component)
    valid_collections = {CollectionEnum.Generators, CollectionEnum.Batteries}
    variable_reserves = list(context.target_system.get_components(VariableReserve))
    for m in memberships:
        if hasattr(m, "collection") and m.collection in valid_collections and hasattr(m, "parent_object"):
            reserve_obj = m.parent_object
            reserve_uuid = getattr(reserve_obj, "uuid", None)
            reserve_name = getattr(reserve_obj, "name", None)
            match = next(
                (
                    vr
                    for vr in variable_reserves
                    if (
                        getattr(vr, "uuid", None) == reserve_uuid or getattr(vr, "name", None) == reserve_name
                    )
                ),
                None,
            )
            if match and match not in services:
                services.append(match)
    return Ok(services)


@getter
def get_gen_bus(
    context: TranslationContext, component: PLEXOSGenerator | PLEXOSBattery
) -> Result[ACBus | None, Any]:
    """
    Get the ACBus object for a generator by finding the connected node via memberships,
    then matching the node name to the ACBus in the target system.
    """
    memberships = context.source_system.get_supplemental_attributes_with_component(component)
    bus_name = None
    for m in memberships:
        if (
            hasattr(m, "collection")
            and m.collection == CollectionEnum.Nodes
            and hasattr(m, "child_object")
            and m.child_object is not None
            and hasattr(m.child_object, "name")
        ):
            bus_name = m.child_object.name
            break

    if not bus_name:
        return Ok(None)

    acbuses = list(context.target_system.get_components(ACBus))
    bus = next((b for b in acbuses if getattr(b, "name", None) == bus_name), None)
    return Ok(bus)


@getter
def get_hydro_gen_operation_cost(
    _: TranslationContext, __: PLEXOSGenerator
) -> Result[HydroGenerationCost, ValueError]:
    """Return zeroed hydro operation cost."""
    return Ok(
        HydroGenerationCost(
            fixed=0.0,
            variable=CostCurve(
                value_curve=LinearCurve(10), power_units=UnitSystem.NATURAL_UNITS, vom_cost=LinearCurve(5.0)
            ),
        )
    )


@getter
def get_hydro_reservoir_operation_cost(
    _: TranslationContext, __: PLEXOSGenerator
) -> Result[HydroReservoirCost, ValueError]:
    """Return zeroed hydro reservoir operation cost."""
    return Ok(HydroReservoirCost(level_shortage_cost=0.0, spillage_cost=0.0, level_surplus_cost=0.0))


@getter
def get_renewable_operation_cost(
    _: TranslationContext, __: PLEXOSGenerator
) -> Result[RenewableGenerationCost, ValueError]:
    """Return zeroed renewable operation cost."""
    return Ok(
        RenewableGenerationCost(
            fixed=0.0, variable=CostCurve(value_curve=LinearCurve(0), power_units=UnitSystem.NATURAL_UNITS)
        )
    )


@getter
def get_gen_reactive_power(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the reactive power of a generator."""
    value = getattr(component, "reactive_power", 0.0)
    return Ok(float(value))


@getter
def get_gen_start_types(_: TranslationContext, component: PLEXOSGenerator) -> Result[int, Any]:
    """Get the start type of a generator as an integer: 1=hot, 2=warm, 3=cold."""
    start_type = getattr(component, "start_type", "hot")
    mapping = {"hot": 1, "warm": 2, "cold": 3}
    value = mapping.get(str(start_type).lower(), 1)
    return Ok(value)


@getter
def get_gen_rating(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the rating of a generator."""
    value = getattr(component, "max_capacity", 0.0)
    return Ok(float(value))


@getter
def get_gen_base_power(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the base power of a generator."""
    value = getattr(component, "base_power", 0.0)
    return Ok(float(value))


@getter
def get_gen_active_power_limits(_: TranslationContext, component: PLEXOSGenerator) -> Result[Any, Any]:
    """Get the active power limits of a generator."""
    value = getattr(component, "active_power_limits", MinMax(min=0.0, max=0.0))
    return Ok(value)


@getter
def get_gen_active_power_losses(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the active power losses incurred by having the unit online."""
    value = getattr(component, "active_power_losses", 0.0)
    return Ok(float(value))


@getter
def get_gen_must_run(_: TranslationContext, component: PLEXOSGenerator) -> Result[bool, Any]:
    """Get the must-run status of a generator."""
    value = getattr(component, "must_run", True)
    return Ok(bool(value))


@getter
def get_gen_reactive_power_limits(_: TranslationContext, component: PLEXOSGenerator) -> Result[Any, Any]:
    """Get the reactive power limits of a generator."""
    value = getattr(component, "reactive_power_limits", MinMax(min=0.0, max=0.0))
    return Ok(value)


@getter
def get_gen_power_factor(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the power factor of a generator."""
    value = getattr(component, "power_factor", 1.0)
    return Ok(float(value))


@getter
def get_prime_mover_type(
    _: TranslationContext, component: PLEXOSGenerator | PLEXOSBattery | PLEXOSStorage
) -> Result[str, Any]:
    """Get the prime mover type of a generator by mapping file."""
    category = getattr(component, "category", None)
    value = _get_prime_mover_type(str(category))
    return Ok(value)


@getter
def get_gen_status(_: TranslationContext, component: PLEXOSGenerator) -> Result[int, Any]:
    """Get the status of a generator."""
    value = getattr(component, "units", "")
    return Ok(int(value))


@getter
def get_time_at_status(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the time at current status of a generator."""
    value = getattr(component, "time_at_status", 0.0)
    return Ok(float(value))


@getter
def get_thermal_operation_cost(
    _: TranslationContext, __: PLEXOSGenerator
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
def get_fuel_type(_: TranslationContext, component: PLEXOSGenerator) -> Result[str, Any]:
    """Get the fuel type of a generator."""
    value = ThermalFuels.NATURAL_GAS
    return Ok(str(value))


@getter
def get_region_peak_active_power(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the peak active power in the area (use 'load' as proxy)."""
    return Ok(float(getattr(component, "load", 0.0)))


@getter
def get_region_peak_reactive_power(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the peak reactive power in the area (no direct field, default to 0.0)."""
    return Ok(float(getattr(component, "peak_reactive_power", 0.0)))


@getter
def get_region_load_response(_: TranslationContext, component: PLEXOSRegion) -> Result[float, Any]:
    """Get the load-frequency damping parameter (use 'load_responce' as proxy)."""
    return Ok(float(getattr(component, "load_responce", 0.0)))


@getter
def get_storage_technology_type(
    _: TranslationContext, component: PLEXOSGenerator
) -> Result[StorageTechs, Any]:
    """Get the storage technology type. Defaults to StorageTechs.OTHER_CHEM."""
    return Ok(StorageTechs.OTHER_CHEM)


@getter
def get_initial_storage_capacity_level(
    _: TranslationContext, component: PLEXOSGenerator
) -> Result[float, Any]:
    """Get the initial storage capacity level (initial_soc), converting percent to decimal if needed."""
    value = float(getattr(component, "initial_soc", 0.0))
    if value > 1.0:
        value = value / 100.0
    return Ok(value)


@getter
def get_storage_capacity(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the storage capacity (max_volume)."""
    return Ok(float(getattr(component, "max_volume", 0.0)))


@getter
def get_storage_level_limits(_: TranslationContext, component: PLEXOSGenerator) -> Result[MinMax, Any]:
    """Get the storage level limits (min_volume, max_volume)."""
    min_vol = float(getattr(component, "min_volume", 0.0))
    max_vol = float(getattr(component, "max_volume", 0.0))
    return Ok(MinMax(min=min_vol, max=max_vol))


@getter
def get_storage_charge_power_limits(_: TranslationContext, component: PLEXOSGenerator) -> Result[MinMax, Any]:
    """Get the input (charge) active power limits."""
    min_charge = float(getattr(component, "min_release", 0.0))
    max_charge = float(getattr(component, "max_release", 0.0))
    return Ok(MinMax(min=min_charge, max=max_charge))


@getter
def get_storage_discharge_power_limits(
    _: TranslationContext, component: PLEXOSGenerator
) -> Result[MinMax, Any]:
    """Get the output (discharge) active power limits."""
    min_discharge = float(getattr(component, "min_release", 0.0))
    max_discharge = float(getattr(component, "max_release", 0.0))
    return Ok(MinMax(min=min_discharge, max=max_discharge))


@getter
def get_storage_efficiency(_: TranslationContext, component: PLEXOSGenerator) -> Result[InputOutput, Any]:
    """Get the storage efficiency as InputOutput (in/out)."""
    eff = float(getattr(component, "efficiency", 1.0))
    return Ok(InputOutput(input=eff, output=eff))


@getter
def get_storage_operation_cost(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the operation cost (use energy_value as proxy)."""
    return Ok(float(getattr(component, "energy_value", 0.0)))


@getter
def get_storage_conversion_factor(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the conversion factor (use capacity_coefficient as proxy)."""
    return Ok(float(getattr(component, "capacity_coefficient", 1.0)))


@getter
def get_storage_target(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the storage target (target_level or target)."""
    return Ok(float(getattr(component, "target_level", getattr(component, "target", 0.0))))


@getter
def get_storage_cycle_limits(_: TranslationContext, component: PLEXOSGenerator) -> Result[int, Any]:
    """Get the cycle limits as an integer (use 'cycle_limits' if available, else 0)."""
    value = getattr(component, "cycle_limits", 10000)
    return Ok(int(value))


@getter
def get_reserve_time_frame(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the timeframe in which the reserve is required (seconds)."""
    return Ok(float(getattr(component, "timeframe", 0.0)))


@getter
def get_reserve_requirement(_: TranslationContext, component: PLEXOSGenerator) -> Result[float | None, Any]:
    """Get the value of required reserves in p.u (SYSTEM_BASE)."""
    return Ok(getattr(component, "requirement", 0.0))


@getter
def get_interface_active_power_flow_limits(
    _: TranslationContext, component: PLEXOSInterface
) -> Result[MinMax, Any]:
    """Get the min/max active power flow limits for a TransmissionInterface."""
    min_flow = float(getattr(component, "min_flow", 0.0))
    max_flow = float(getattr(component, "max_flow", 0.0))
    return Ok(MinMax(min=min_flow, max=max_flow))


@getter
def get_interface_direction_mapping(
    _: TranslationContext, component: PLEXOSInterface
) -> Result[dict[str, int], Any]:
    """
    Get the direction mapping for a TransmissionInterface.
    This is a placeholder; actual mapping logic depends on your data model.
    """
    direction_mapping = getattr(component, "direction_mapping", {})
    return Ok(direction_mapping)


@getter
def get_trf_active_power_flow(_: TranslationContext, component: PLEXOSTransformer) -> Result[float, Any]:
    """Get the active power flow through the transformer."""
    return Ok(getattr(component, "active_power_flow", 0.0))


@getter
def get_trf_reactive_power_flow(_: TranslationContext, component: PLEXOSTransformer) -> Result[float, Any]:
    """Get the reactive power flow through the transformer."""
    return Ok(getattr(component, "reactive_power_flow", 0.0))


@getter
def get_trf_primary_shunt(
    _: TranslationContext, component: PLEXOSTransformer
) -> Result[Complex | float | None, Any]:
    """Get the primary shunt admittance of the transformer (complex or None)."""
    value = getattr(component, "primary_shunt", None)
    if value is None:
        return Ok(None)
    if isinstance(value, Complex):
        return Ok(value)
    return Ok(Complex(real=0.0, imag=0.0))


@getter
def get_trf_base_power(_: TranslationContext, component: PLEXOSTransformer) -> Result[float, Any]:
    """Get the base power of the transformer."""
    return Ok(getattr(component, "base_power", 100.0))


@getter
def get_trf_winding_group_number(
    _: TranslationContext, component: PLEXOSTransformer
) -> Result[WindingGroupNumber, Any]:
    """Get the winding group number of the transformer as a WindingGroupNumber enum."""
    return Ok(WindingGroupNumber.UNDEFINED)


@getter
def get_trf_control_objective(
    _: TranslationContext, component: PLEXOSTransformer
) -> Result[TransformerControlObjective, Any]:
    """Get the control objective of the transformer as a TransformerControlObjective enum."""
    return Ok(TransformerControlObjective.UNDEFINED)


@getter
def get_reserve_type(_: TranslationContext, component: PLEXOSReserve) -> Result[ReserveType, Any]:
    """Get the reserve type for a PLEXOSReserve component as a ReserveType enum."""
    value = getattr(component, "reserve_type", None)
    try:
        return Ok(ReserveType(value))
    except Exception:
        return Ok(ReserveType.SPINNING)


@getter
def get_reserve_direction(_: TranslationContext, component: PLEXOSReserve) -> Result[ReserveDirection, Any]:
    """Get the reserve direction for a PLEXOSReserve component as a ReserveDirection enum."""
    value = getattr(component, "direction", None)
    try:
        return Ok(ReserveDirection(value))
    except Exception:
        return Ok(ReserveDirection.UP)


@getter
def get_reserve_sustained_time(_: TranslationContext, component: PLEXOSReserve) -> Result[float, Any]:
    """Get the time in seconds reserve contribution must be sustained."""
    return Ok(float(getattr(component, "duration", 3600.0)))


@getter
def get_reserve_max_participation_factor(
    _: TranslationContext, component: PLEXOSReserve
) -> Result[float, Any]:
    """Get the maximum portion [0, 1.0] of the reserve that can be contributed per device."""
    return Ok(float(getattr(component, "max_participation_factor", 1.0)))


@getter
def get_reserve_max_output_fraction(_: TranslationContext, component: PLEXOSReserve) -> Result[float, Any]:
    """Get the max output fraction (default 1.0)."""
    return Ok(float(getattr(component, "max_output_fraction", 1.0)))


@getter
def get_reserve_deployed_fraction(_: TranslationContext, component: PLEXOSReserve) -> Result[float, Any]:
    """Get the fraction of service procurement assumed to be actually deployed."""
    return Ok(float(getattr(component, "deployed_fraction", 1.0)))
