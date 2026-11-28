"""Getter functions for rules."""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping
from typing import Any

from infrasys.cost_curves import CostCurve, FuelCurve
from infrasys.function_data import PiecewiseStepData
from infrasys.value_curves import AverageRateCurve, InputOutputCurve, LinearCurve
from loguru import logger
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSPurchaser,
    PLEXOSRegion,
    PLEXOSReserve,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_sienna.models import (
    ACBus,
    Arc,
    Area,
    LoadZone,
    VariableReserve,
)
from r2x_sienna.models.costs import (
    HydroGenerationCost,
    HydroReservoirCost,
    RenewableGenerationCost,
    ThermalGenerationCost,
)
from r2x_sienna.models.enums import (
    ACBusTypes,
    ReserveDirection,
    ReserveType,
    StorageTechs,
    ThermalFuels,
    TransformerControlObjective,
    WindingGroupNumber,
)
from r2x_sienna.models.named_tuples import (
    Complex,
    FromTo_ToFrom,
    InputOutput,
    MinMax,
    UpDown,
)

from r2x_core import Ok, PluginContext, Result
from r2x_core.getters import getter

from .constants import NATURAL_UNITS
from .utils import (
    _classify_generator_category,
    _first_numeric,
    _get_fuel_type,
    _get_hvdc_active_power_limits,
    _get_prime_mover_type,
    _get_region_node_names,
    _get_target_component_by_name,
    _get_target_system_base_power,
    _get_transformer_base_power,
    _get_trf_phase_angle_radians,
    _sync_time_series_for_source,
    _to_per_unit_power,
)
from .utils import (
    get_plexos_node_number as _get_plexos_node_number,
)


@getter
def get_load_bus(component: PLEXOSRegion, context: PluginContext) -> Result[ACBus | None, Any]:
    """
    Get the bus (ACBus) associated with the load region.

    Looks for a PLEXOSNode membership (collection=Region) and matches the node name to an ACBus.
    """
    _sync_time_series_for_source(component, context)

    if context.source_system is None or context.target_system is None:
        return Ok(None)

    node_names = _get_region_node_names(context.source_system, component)
    if len(node_names) != 1:
        return Ok(None)
    node_name = next(iter(node_names))
    return Ok(_get_target_component_by_name(context.target_system, ACBus, node_name))


@getter
def get_purchaser_bus(component: PLEXOSPurchaser, context: PluginContext) -> Result[ACBus | None, Any]:
    """Get the ACBus associated with a purchaser through its node membership."""
    _sync_time_series_for_source(component, context)

    if context.source_system is None or context.target_system is None:
        return Ok(None)

    memberships = context.source_system.get_supplemental_attributes_with_component(component)
    node_name = next(
        (
            membership.child_object.name
            for membership in memberships
            if getattr(membership, "collection", None) == CollectionEnum.Nodes
            and getattr(getattr(membership, "child_object", None), "name", None)
        ),
        None,
    )
    if node_name is None:
        return Ok(None)

    bus = _get_target_component_by_name(context.target_system, ACBus, node_name)
    return Ok(bus)


@getter
def get_purchaser_active_power(component: PLEXOSPurchaser, context: PluginContext) -> Result[float, Any]:
    """Get the purchaser's fixed demand on its device base."""
    return Ok(float(component.fixed_load) / _get_purchaser_base_power(component))


@getter
def get_purchaser_available(component: PLEXOSPurchaser, context: PluginContext) -> Result[bool, Any]:
    """Convert the PLEXOS purchaser units flag to Sienna availability."""
    return Ok(bool(getattr(component, "units", 0)))


@getter
def get_purchaser_max_active_power(component: PLEXOSPurchaser, context: PluginContext) -> Result[float, Any]:
    """Get the maximum purchaser load on its device base."""
    maximum = max(component.max_load, component.fixed_load)
    return Ok(float(maximum) / _get_purchaser_base_power(component))


@getter
def get_purchaser_reactive_power(component: PLEXOSPurchaser, context: PluginContext) -> Result[float, Any]:
    """Get the purchaser's reactive power, defaulting to zero."""
    value = float(getattr(component, "reactive_power", 0.0) or 0.0)
    return Ok(value / _get_purchaser_base_power(component))


@getter
def get_purchaser_max_reactive_power(
    component: PLEXOSPurchaser, context: PluginContext
) -> Result[float, Any]:
    """Get the purchaser's maximum reactive power, defaulting to zero."""
    value = float(getattr(component, "max_reactive_power", 0.0) or 0.0)
    return Ok(value / _get_purchaser_base_power(component))


def _get_purchaser_base_power(component: PLEXOSPurchaser) -> float:
    return getattr(component, "base_power", 100.0) or 100.0


@getter
def get_purchaser_base_power(component: PLEXOSPurchaser, context: PluginContext) -> Result[float, Any]:
    """Get the purchaser's base power, defaulting to 100 MW."""
    return Ok(_get_purchaser_base_power(component))


@getter
def get_load_active_power(component: PLEXOSRegion, context: PluginContext) -> Result[float, Any]:
    """Get regional demand on the load device base."""
    return Ok(_get_load_active_power(component))


@getter
def get_load_reactive_power(component: PLEXOSRegion, context: PluginContext) -> Result[float, Any]:
    """Get the reactive power of load at the bus (if available)."""
    value = float(getattr(component, "reactive_power", 0.0))
    return Ok(value / _get_load_base_power(component))


@getter
def get_load_max_active_power(component: PLEXOSRegion, context: PluginContext) -> Result[float, Any]:
    """Get the regional load peak on the device base."""
    return Ok(_get_load_active_power(component))


@getter
def get_load_max_reactive_power(component: PLEXOSRegion, context: PluginContext) -> Result[float, Any]:
    """Get the maximum reactive power demand of the load at the bus (if available)."""
    value = float(getattr(component, "max_reactive_power", 0.0))
    return Ok(value / _get_load_base_power(component))


def _get_load_base_power(component: PLEXOSRegion) -> float:
    return getattr(component, "base_power", 100.0)


def _get_load_active_power(component: PLEXOSRegion) -> float:
    return float(component.load) / _get_load_base_power(component)


@getter
def get_load_base_power(component: PLEXOSRegion, context: PluginContext) -> Result[float, Any]:
    """Get the base power of the load at the bus (if available)."""
    return Ok(_get_load_base_power(component))


@getter
def get_node_load_bus(component: PLEXOSNode, context: PluginContext) -> Result[ACBus | None, Any]:
    """Get the bus for a node-level PowerLoad."""
    _sync_time_series_for_source(component, context)
    if context.target_system is None:
        return Ok(None)
    return Ok(_get_target_component_by_name(context.target_system, ACBus, component.name))


@getter
def get_node_load_active_power(component: PLEXOSNode, context: PluginContext) -> Result[float, Any]:
    """Get node-level demand on the load device base."""
    return Ok(float(component.load) / _get_node_load_base_power(component))


@getter
def get_node_load_base_power(component: PLEXOSNode, context: PluginContext) -> Result[float, Any]:
    """Get the node load base power, defaulting to 100 MW."""
    return Ok(_get_node_load_base_power(component))


def _get_node_load_base_power(component: PLEXOSNode) -> float:
    return float(getattr(component, "base_power", 100.0) or 100.0)


@getter
def get_zone_peak_active_power(component: PLEXOSZone, context: PluginContext) -> Result[float, Any]:
    """Get the peak active power for a zone."""
    value = getattr(component, "peak_active_power", 0.0)
    return Ok(_to_per_unit_power(value, _get_target_system_base_power(context)))


@getter
def get_zone_peak_reactive_power(component: PLEXOSZone, context: PluginContext) -> Result[float, Any]:
    """Get the peak reactive power for a zone."""
    value = getattr(component, "peak_reactive_power", 0.0)
    return Ok(_to_per_unit_power(value, _get_target_system_base_power(context)))


@getter
def get_node_angle(component: PLEXOSNode, context: PluginContext) -> Result[float, Any]:
    """Get the angle of a node."""
    value = getattr(component, "angle", 0.0)
    return Ok(float(value))


@getter
def get_node_area(component: PLEXOSNode, context: PluginContext) -> Result[Any, Any]:
    """Get the Area object of a node from its memberships (Region collection), matching by name in the target system."""
    if context.source_system is None or context.target_system is None:
        value = getattr(component, "area", None)
        return Ok(value)
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
        area_obj = _get_target_component_by_name(context.target_system, Area, area_name)
        if area_obj:
            return Ok(area_obj)
    value = getattr(component, "area", None)
    return Ok(value)


@getter
def get_node_zone(component: PLEXOSNode, context: PluginContext) -> Result[Any, Any]:
    """Get the LoadZone object of a node from its memberships (Zone collection), matching by name in the target system."""
    if context.source_system is None or context.target_system is None:
        value = getattr(component, "zone", None)
        return Ok(value)
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
        zone_obj = _get_target_component_by_name(context.target_system, LoadZone, zone_name)
        if zone_obj:
            return Ok(zone_obj)
    value = getattr(component, "zone", None)
    return Ok(value)


@getter
def get_base_voltage(component: PLEXOSNode, context: PluginContext) -> Result[float, Any]:
    """Get the voltage of a node. Try 'voltage', then 'ac_voltage_magnitude', else default to 1.0."""
    voltage = getattr(component, "voltage", 0.0)
    if voltage and voltage != 0.0:
        return Ok(float(voltage))
    ac_voltage = getattr(component, "ac_voltage_magnitude", 0.0)
    if ac_voltage and ac_voltage != 0.0:
        return Ok(float(ac_voltage))
    return Ok(1.0)


@getter
def get_node_ext(component: PLEXOSNode, context: PluginContext) -> Result[dict[str, Any], Any]:
    """Get the ext dictionary for a node."""
    if context is not None:
        _sync_time_series_for_source(component, context)
    value = {
        "load_participation_factor": getattr(component, "load_participation_factor", None),
    }
    return Ok(value)


@getter
def get_node_number(component: PLEXOSNode, context: PluginContext) -> Result[int, Any]:
    """Return a unique positive node number from Number, the name, or a counter."""
    return Ok(_get_plexos_node_number(component, context))


@getter
def is_slack_bus(component: PLEXOSNode, context: PluginContext) -> Result[ACBusTypes, Any]:
    """Return slack type for explicit or regional reference-node memberships."""
    value = getattr(component, "is_slack_bus", 0)
    is_reference_node = any(
        getattr(membership, "collection", None) == CollectionEnum.ReferenceNode
        for membership in (
            context.source_system.get_supplemental_attributes_with_component(component)
            if context.source_system is not None
            else []
        )
    )
    bustype = ACBusTypes.SLACK if value in (-1, 1) or is_reference_node else ACBusTypes.PQ
    return Ok(bustype)


@getter
def get_line_arc(component: PLEXOSLine | PLEXOSTransformer, context: PluginContext) -> Result[Arc, Any]:
    """Get a line or transformer's arc from node memberships and matching ACBus objects."""
    if context.source_system is None or context.target_system is None:
        raise ValueError("Source and target systems must be set to get line arc")
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

    arc_name = f"{from_node}-{to_node}"

    # Reuse existing Arc if one with the same name already exists in the target system
    existing_arc = _get_target_component_by_name(context.target_system, Arc, arc_name)
    if existing_arc is not None:
        return Ok(existing_arc)

    from_bus = _get_target_component_by_name(context.target_system, ACBus, from_node)
    to_bus = _get_target_component_by_name(context.target_system, ACBus, to_node)

    if from_bus is None or to_bus is None:
        acbuses = list(context.target_system.get_components(ACBus))
        raise ValueError(
            f"Could not find ACBus for names: {from_node}, {to_node}. "
            f"Available: {[bus.name for bus in acbuses]}"
        )

    arc_sense = Arc(name=arc_name, from_to=from_bus, to_from=to_bus)
    return Ok(arc_sense)


@getter
def get_line_conductance(component: PLEXOSLine, context: PluginContext) -> Result[FromTo_ToFrom, Any]:
    """Get the conductance of a line as a FromTo_ToFrom namedtuple (g = 1/r)."""
    r = None
    if hasattr(component, "resistance") and component.resistance:
        r = _first_numeric(component.resistance)
    if r and r != 0.0:
        g = 1.0 / r
        return Ok(FromTo_ToFrom(from_to=g, to_from=g))
    return Ok(FromTo_ToFrom(from_to=0.0, to_from=0.0))


@getter
def get_reactive_power_flow(component: PLEXOSLine, context: PluginContext) -> Result[float, Any]:
    """Get the reactive power flow of a line as a FromTo_ToFrom namedtuple."""
    return Ok(0.0)


@getter
def get_line_angle_limits(component: PLEXOSLine, context: PluginContext) -> Result[MinMax, Any]:
    """Get the angle limits of a line. Defaults to MinMax(-90.0, 90.0) if not found."""
    value = getattr(component, "angle_limits", None)
    if value is not None:
        if isinstance(value, MinMax):
            return Ok(value)
        if isinstance(value, tuple) and len(value) == 2:
            return Ok(MinMax(min=float(value[0]), max=float(value[1])))
    return Ok(MinMax(min=-90.0, max=90.0))


@getter
def get_line_susceptance(component: PLEXOSLine, context: PluginContext) -> Result[FromTo_ToFrom, Any]:
    """Get the susceptance of a line as a FromTo_ToFrom namedtuple."""
    value = None
    if hasattr(component, "susceptance") and component.susceptance:
        value = _first_numeric(component.susceptance)
    if value is not None:
        return Ok(FromTo_ToFrom(from_to=value, to_from=value))
    return Ok(FromTo_ToFrom(from_to=0.0, to_from=0.0))


@getter
def get_line_flow_limits(component: PLEXOSLine, context: PluginContext) -> Result[FromTo_ToFrom, Any]:
    """Get the flow limits (from_to, to_from) of a line as a FromTo_ToFrom namedtuple."""
    min_flow = getattr(component, "min_flow", -100.0)
    max_flow = getattr(component, "max_flow", None)
    base_power = _get_target_system_base_power(context)
    if min_flow is None:
        min_flow = -100.0
    if max_flow is None:
        max_flow = 100.0
    return Ok(
        FromTo_ToFrom(
            from_to=_to_per_unit_power(max_flow, base_power),
            to_from=_to_per_unit_power(min_flow, base_power),
        )
    )


@getter
def get_line_rating(component: PLEXOSLine, context: PluginContext) -> Result[float, Any]:
    """Convert the PLEXOS line rating from MW to per-unit on the system base."""
    max_flow = getattr(component, "max_flow", None)
    return Ok(_to_per_unit_power(max_flow, _get_target_system_base_power(context)))


@getter
def get_line_active_power_flow(component: PLEXOSLine, context: PluginContext) -> Result[float, Any]:
    """Convert fixed PLEXOS line flow from MW to per-unit on the system base."""
    fixed_flow = getattr(component, "fixed_flow", None)
    return Ok(_to_per_unit_power(fixed_flow, _get_target_system_base_power(context)))


@getter
def get_line_losses(component: PLEXOSLine, context: PluginContext) -> Result[float, Any]:
    """Get the losses of a line (if available)."""
    value = getattr(component, "losses", 0.0)
    return Ok(_first_numeric(value))


@getter
def get_active_power_limits_from(component: PLEXOSLine, context: PluginContext) -> Result[MinMax, Any]:
    """Convert PLEXOS HVDC flow limits from MW to per-unit at the 'from' end."""
    return Ok(_get_hvdc_active_power_limits(component, context))


@getter
def get_active_power_limits_to(component: PLEXOSLine, context: PluginContext) -> Result[MinMax, Any]:
    """Convert PLEXOS HVDC flow limits from MW to per-unit at the 'to' end."""
    return Ok(_get_hvdc_active_power_limits(component, context))


@getter
def get_reactive_power_limits_from(component: PLEXOSLine, context: PluginContext) -> Result[MinMax, Any]:
    """Convert reactive power limits at the 'from' end of an HVDC line to per-unit."""
    min_limit = getattr(component, "min_reactive_power_from", 0.0)
    max_limit = getattr(component, "max_reactive_power_from", 0.0)
    base_power = _get_target_system_base_power(context)
    return Ok(
        MinMax(
            min=_to_per_unit_power(min_limit, base_power),
            max=_to_per_unit_power(max_limit, base_power),
        )
    )


@getter
def get_reactive_power_limits_to(component: PLEXOSLine, context: PluginContext) -> Result[MinMax, Any]:
    """Convert reactive power limits at the 'to' end of an HVDC line to per-unit."""
    min_limit = getattr(component, "min_reactive_power_to", 0.0)
    max_limit = getattr(component, "max_reactive_power_to", 0.0)
    base_power = _get_target_system_base_power(context)
    return Ok(
        MinMax(
            min=_to_per_unit_power(min_limit, base_power),
            max=_to_per_unit_power(max_limit, base_power),
        )
    )


@getter
def get_hvdc_line_loss(component: PLEXOSLine, context: PluginContext) -> Result[InputOutputCurve, Any]:
    """Get the losses of an HVDC line as an InputOutputCurve (if available)."""
    loss_incr = getattr(component, "loss_incr", 0.0)
    return Ok(LinearCurve(loss_incr))


def _get_gen_base_power(component: PLEXOSGenerator | PLEXOSBattery) -> float:
    for field_name in ("base_power", "max_capacity", "max_power"):
        value = getattr(component, field_name, None)
        if value is None:
            continue
        try:
            base_power = float(value)
        except (TypeError, ValueError):
            continue
        if base_power > 0.0:
            return base_power
    return 100.0


@getter
def get_gen_active_power(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the active power of a generator on its device base."""
    value = getattr(component, "max_capacity", 0.0)
    return Ok(float(value) / _get_gen_base_power(component))


@getter
def get_device_services(
    component: PLEXOSGenerator | PLEXOSBattery | PLEXOSStorage, context: PluginContext
) -> Result[list[Any], Any]:
    """
    Get the services provided by a device (generator, battery, etc.), returning VariableReserve objects from the target system.
    """
    if context.source_system is None or context.target_system is None:
        return Ok([])
    services = []
    memberships = context.source_system.get_supplemental_attributes_with_component(component)
    valid_collections = {CollectionEnum.Generators, CollectionEnum.Batteries}
    for m in memberships:
        if hasattr(m, "collection") and m.collection in valid_collections and hasattr(m, "parent_object"):
            reserve_obj = m.parent_object
            reserve_uuid = getattr(reserve_obj, "uuid", None)
            reserve_name = getattr(reserve_obj, "name", None)
            match = None
            if reserve_name:
                candidate = _get_target_component_by_name(
                    context.target_system, VariableReserve, reserve_name
                )
                if (
                    candidate is not None
                    and reserve_uuid is not None
                    and getattr(candidate, "uuid", None) == reserve_uuid
                ):
                    match = candidate
            if match is None:
                match = next(
                    (
                        reserve
                        for reserve in context.target_system.get_components(VariableReserve)
                        if (
                            getattr(reserve, "uuid", None) == reserve_uuid
                            or getattr(reserve, "name", None) == reserve_name
                        )
                    ),
                    None,
                )
            if match and match not in services:
                services.append(match)
    return Ok(services)


@getter
def get_gen_bus(
    component: PLEXOSGenerator | PLEXOSBattery, context: PluginContext
) -> Result[ACBus | None, Any]:
    """
    Get the ACBus object for a generator by finding the connected node via memberships,
    then matching the node name to the ACBus in the target system.
    """
    _sync_time_series_for_source(component, context)

    if context.source_system is None or context.target_system is None:
        return Ok(None)

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

    bus = _get_target_component_by_name(context.target_system, ACBus, bus_name)
    return Ok(bus)


@getter
def get_hydro_gen_operation_cost(
    component: PLEXOSGenerator, context: PluginContext
) -> Result[HydroGenerationCost, ValueError]:
    """Return zeroed hydro operation cost."""
    return Ok(
        HydroGenerationCost(
            fixed=0.0,
            variable=CostCurve(
                value_curve=LinearCurve(10), power_units=NATURAL_UNITS, vom_cost=LinearCurve(5.0)
            ),
        )
    )


@getter
def get_hydro_reservoir_operation_cost(
    component: PLEXOSGenerator | PLEXOSStorage, context: PluginContext
) -> Result[HydroReservoirCost, ValueError]:
    """Return zeroed hydro reservoir operation cost."""
    return Ok(HydroReservoirCost(level_shortage_cost=0.0, spillage_cost=0.0, level_surplus_cost=0.0))


@getter
def get_renewable_operation_cost(
    component: PLEXOSGenerator, context: PluginContext
) -> Result[RenewableGenerationCost, ValueError]:
    """Return zeroed renewable operation cost."""
    zero_curve = CostCurve(value_curve=LinearCurve(0.0), power_units=NATURAL_UNITS)
    return Ok(
        RenewableGenerationCost(
            fixed=0.0,
            variable=zero_curve,
            curtailment_cost=zero_curve,
        )
    )


@getter
def get_gen_reactive_power(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the reactive power of a generator on its device base."""
    value = getattr(component, "reactive_power", 0.0)
    return Ok(float(value) / _get_gen_base_power(component))


@getter
def get_gen_start_types(component: PLEXOSGenerator, context: PluginContext) -> Result[int, Any]:
    """Get the start type of a generator as an integer: 1=hot, 2=warm, 3=cold."""
    start_type = getattr(component, "start_type", "hot")
    mapping = {"hot": 1, "warm": 2, "cold": 3}
    value = mapping.get(str(start_type).lower(), 1)
    return Ok(value)


@getter
def get_gen_rating(component: PLEXOSGenerator | PLEXOSBattery, context: PluginContext) -> Result[float, Any]:
    """Get the generator or battery rating on its device base."""
    value = component.max_power if isinstance(component, PLEXOSBattery) else component.max_capacity
    return Ok(float(value) / _get_gen_base_power(component))


@getter
def get_gen_base_power(
    component: PLEXOSGenerator | PLEXOSBattery, context: PluginContext
) -> Result[float, Any]:
    """Use a positive equipment base/rating, or the standard 100 MVA fallback."""
    return Ok(_get_gen_base_power(component))


def _gen_active_power_limits_mw(component: PLEXOSGenerator) -> MinMax:
    """Return min stable level and max capacity in MW.

    If ``min_stable_level`` is zero but ``min_stable_factor`` (% of max_capacity) is set,
    the factor takes precedence.
    """
    max_cap = float(getattr(component, "max_capacity", 0.0) or 0.0)
    min_stable = float(getattr(component, "min_stable_level", 0.0) or 0.0)
    if min_stable == 0.0:
        factor = float(getattr(component, "min_stable_factor", 0.0) or 0.0)
        if factor > 0.0:
            min_stable = factor / 100.0 * max_cap
    return MinMax(min=min_stable, max=max_cap)


def _gen_reactive_power_limits_mvar(component: PLEXOSGenerator) -> MinMax:
    value = getattr(component, "reactive_power_limits", None) or MinMax(min=0.0, max=0.0)
    return MinMax(min=value.min, max=value.max)


def _to_device_base(limits: MinMax, component: PLEXOSGenerator) -> MinMax:
    base_power = _get_gen_base_power(component)
    return MinMax(min=limits.min / base_power, max=limits.max / base_power)


# Sienna fields annotated with ``Unit("pu", base="base_power")`` treat plain structured
# input as natural units and convert it once with r2x-core; unannotated per-unit fields
# store the value as given. The ``*_mw``/``*_mvar`` getters feed the annotated fields.


@getter
def get_gen_active_power_limits(component: PLEXOSGenerator, context: PluginContext) -> Result[MinMax, Any]:
    """Get active power limits on the device base for unannotated per-unit fields."""
    return Ok(_to_device_base(_gen_active_power_limits_mw(component), component))


@getter
def get_gen_active_power_limits_mw(component: PLEXOSGenerator, context: PluginContext) -> Result[MinMax, Any]:
    """Get active power limits in MW for unit-annotated Sienna fields."""
    return Ok(_gen_active_power_limits_mw(component))


@getter
def get_gen_active_power_losses(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the online active power losses on the device base."""
    value = getattr(component, "active_power_losses", 0.0)
    return Ok(float(value) / _get_gen_base_power(component))


@getter
def get_gen_must_run(component: PLEXOSGenerator, context: PluginContext) -> Result[bool, Any]:
    """Map must-run units to a whole-generator commitment requirement."""
    if 0 < component.must_run_units < component.units:
        raise ValueError(f"Partial must-run units cannot be represented for {component.name}")
    return Ok(component.must_run_units > 0)


@getter
def get_gen_reactive_power_limits(component: PLEXOSGenerator, context: PluginContext) -> Result[Any, Any]:
    """Get reactive power limits on the device base for unannotated per-unit fields."""
    return Ok(_to_device_base(_gen_reactive_power_limits_mvar(component), component))


@getter
def get_gen_reactive_power_limits_mvar(
    component: PLEXOSGenerator, context: PluginContext
) -> Result[MinMax, Any]:
    """Get reactive power limits in MVAr for unit-annotated Sienna fields."""
    return Ok(_gen_reactive_power_limits_mvar(component))


@getter
def get_gen_power_factor(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the power factor of a generator."""
    value = getattr(component, "power_factor", 1.0)
    return Ok(float(value))


@getter
def get_prime_mover_type(
    component: PLEXOSGenerator | PLEXOSBattery | PLEXOSStorage, context: PluginContext
) -> Result[str, Any]:
    """Get the prime mover type of a generator by mapping file."""
    category = getattr(component, "category", None)
    value = _get_prime_mover_type(str(category))
    return Ok(value)


@getter
def get_gen_technology_class(component: PLEXOSGenerator, context: PluginContext) -> Result[str, Any]:
    """Classify a generator into a Sienna technology family from its category name.

    Supports both canonical ReEDS-style slugs and descriptive naming
    conventions (e.g. AEMO ISP "Wind SA", "Black Coal QLD", "Hydro TAS").
    """
    return Ok(_classify_generator_category(getattr(component, "category", None)))


@getter
def get_gen_status(component: PLEXOSGenerator, context: PluginContext) -> Result[bool, Any]:
    """Get the commitment status of a generator (True when any units are online)."""
    value = getattr(component, "units", 0)
    return Ok(int(value or 0) > 0)


@getter
def get_available_from_units(component: Any, context: PluginContext) -> Result[bool, Any]:
    """Map a PLEXOS ``units`` count to a boolean availability flag."""
    value = getattr(component, "units", 0)
    return Ok(int(value or 0) > 0)


@getter
def get_time_at_status(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the time at current status of a generator."""
    value = getattr(component, "time_at_status", 0.0)
    return Ok(float(value))


@getter
def get_thermal_operation_cost(
    component: PLEXOSGenerator, context: PluginContext
) -> Result[ThermalGenerationCost, ValueError]:
    """Build thermal cost, preserving banded heat rates as a piecewise curve."""
    heat_rate_value = getattr(component, "heat_rate", 0.0) or 0.0
    if isinstance(heat_rate_value, Mapping):
        band_rate_items = sorted(heat_rate_value.items(), key=lambda item: int(item[0]))
        band_ids = [int(band) for band, rate in band_rate_items if rate is not None]
        band_rates = [float(rate) for _, rate in band_rate_items if rate is not None]
    else:
        band_ids = []
        band_rates = []

    if len(band_rates) > 1:
        min_output = _first_numeric(getattr(component, "min_stable_level", 0.0) or 0.0)
        max_output = _first_numeric(getattr(component, "max_capacity", 0.0) or 0.0)
        if min_output == 0.0:
            factor = _first_numeric(getattr(component, "min_stable_factor", 0.0) or 0.0)
            if factor > 0.0:
                min_output = factor / 100.0 * max_output
        if max_output > min_output:
            load_point_value = getattr(component, "load_point", None)
            has_explicit_load_points = (
                bool(load_point_value)
                if isinstance(load_point_value, Mapping)
                else load_point_value not in (None, 0)
            )
            load_points_by_band: dict[int, float] = {}
            if isinstance(load_point_value, Mapping) and has_explicit_load_points:
                try:
                    load_points_by_band = {
                        int(band): float(point)
                        for band, point in load_point_value.items()
                        if point is not None
                    }
                except (TypeError, ValueError, OverflowError):
                    load_points_by_band = {}
            elif has_explicit_load_points and len(band_ids) == 1:
                try:
                    load_points_by_band[band_ids[0]] = float(load_point_value)
                except (TypeError, ValueError, OverflowError):
                    load_points_by_band = {}

            x_coords = [min_output, *(load_points_by_band.get(band, math.nan) for band in band_ids)]
            valid_load_points = (
                has_explicit_load_points
                and len(load_points_by_band) == len(band_ids)
                and set(load_points_by_band) == set(band_ids)
                and all(math.isfinite(point) for point in x_coords)
                and x_coords[0] <= x_coords[1]
                and all(left < right for left, right in itertools.pairwise(x_coords[1:]))
                and x_coords[-1] <= max_output
            )

            if not valid_load_points and has_explicit_load_points:
                logger.warning(
                    "{} has invalid load-point breakpoints for its heat-rate bands; using band 1",
                    component.name,
                )
            elif not has_explicit_load_points:
                x_coords = [
                    min_output + (max_output - min_output) * index / len(band_rates)
                    for index in range(len(band_rates) + 1)
                ]
                logger.warning(
                    "{} has {} heat-rate bands without explicit capacity breakpoints; "
                    "assuming equal-width bands between {} and {} MW",
                    component.name,
                    len(band_rates),
                    min_output,
                    max_output,
                )

            if valid_load_points or not has_explicit_load_points:
                initial_input = min_output * band_rates[0]
                if x_coords[0] == x_coords[1]:
                    # The first band's fuel input is already represented by initial_input.
                    x_coords = x_coords[1:]
                    band_rates = band_rates[1:]
                value_curve = AverageRateCurve(
                    function_data=PiecewiseStepData(x_coords=x_coords, y_coords=band_rates),
                    initial_input=initial_input,
                )
            else:
                value_curve = LinearCurve(band_rates[0])
        else:
            value_curve = LinearCurve(band_rates[0])
            logger.warning(
                "{} has banded heat rates but invalid output limits; using band 1",
                component.name,
            )
    else:
        heat_rate = band_rates[0] if band_rates else _first_numeric(heat_rate_value)
        value_curve = LinearCurve(heat_rate)

    fuel_price = _first_numeric(getattr(component, "fuel_price", 0.0) or 0.0)
    vom_charge = _first_numeric(getattr(component, "vom_charge", 0.0) or 0.0)
    start_cost = _first_numeric(getattr(component, "start_cost", 0.0) or 0.0)
    return Ok(
        ThermalGenerationCost(
            fixed=0.0,
            shut_down=0.0,
            start_up=start_cost,
            variable=FuelCurve(
                value_curve=value_curve,
                power_units=NATURAL_UNITS,
                fuel_cost=fuel_price,
                vom_cost=LinearCurve(vom_charge),
            ),
        )
    )


@getter
def get_fuel_type(component: PLEXOSGenerator, context: PluginContext) -> Result[ThermalFuels, Any]:
    """Get the fuel type of a generator by mapping its category via defaults.json."""
    category = str(getattr(component, "category", "") or "")
    return Ok(_get_fuel_type(category))


@getter
def get_region_peak_active_power(component: PLEXOSRegion, context: PluginContext) -> Result[float, Any]:
    """Get the peak active power in the area (use 'load' as proxy)."""
    return Ok(
        _to_per_unit_power(
            getattr(component, "load", 0.0),
            _get_target_system_base_power(context),
        )
    )


@getter
def get_region_peak_reactive_power(component: PLEXOSRegion, context: PluginContext) -> Result[float, Any]:
    """Get the peak reactive power in the area (no direct field, default to 0.0)."""
    return Ok(
        _to_per_unit_power(
            getattr(component, "peak_reactive_power", 0.0),
            _get_target_system_base_power(context),
        )
    )


@getter
def get_region_load_response(component: PLEXOSRegion, context: PluginContext) -> Result[float, Any]:
    """Get the load-frequency damping parameter (use 'load_responce' as proxy)."""
    return Ok(float(getattr(component, "load_responce", 0.0)))


@getter
def get_storage_technology_type(
    component: PLEXOSGenerator, context: PluginContext
) -> Result[StorageTechs, Any]:
    """Get the storage technology type. Defaults to StorageTechs.OTHER_CHEM."""
    return Ok(StorageTechs.OTHER_CHEM)


@getter
def get_initial_storage_capacity_level(
    component: PLEXOSGenerator, context: PluginContext
) -> Result[float, Any]:
    """Get the initial storage capacity level (initial_soc), converting percent to decimal if needed."""
    value = float(getattr(component, "initial_soc", 0.0))
    if value > 1.0:
        value = value / 100.0
    return Ok(value)


@getter
def get_storage_capacity(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the storage capacity.

    For PLEXOSBattery converts ``capacity`` (MWh) to the device base.
    For PLEXOSStorage (hydro reservoir) returns ``max_volume`` unchanged in GWh.
    """
    if hasattr(component, "capacity") and not hasattr(component, "max_volume"):
        capacity = float(getattr(component, "capacity", 0.0) or 0.0)
        return Ok(capacity / _get_gen_base_power(component))
    return Ok(float(getattr(component, "max_volume", 0.0) or 0.0))


@getter
def get_storage_level_limits(
    component: PLEXOSGenerator | PLEXOSStorage, context: PluginContext
) -> Result[MinMax, Any]:
    """Get the storage level limits.

    For PLEXOSBattery: returns fractions [0, 1] (Sienna convention for batteries).
    For PLEXOSStorage (hydro): converts min/max_volume from GWh to MWh.
    """
    if hasattr(component, "capacity") and not hasattr(component, "max_volume"):
        return Ok(MinMax(min=0.0, max=1.0))
    min_vol = float(getattr(component, "min_volume", 0.0) or 0.0) * 1000.0
    max_vol = float(getattr(component, "max_volume", 0.0) or 0.0) * 1000.0
    return Ok(MinMax(min=min_vol, max=max_vol))


@getter
def get_storage_charge_power_limits(
    component: PLEXOSGenerator, context: PluginContext
) -> Result[MinMax, Any]:
    """Get the input (charge) active power limits in MW.

    For PLEXOSBattery uses ``max_power``; the unit-annotated Sienna field converts it
    to the device base. For PLEXOSStorage uses ``max_release``.
    """
    if hasattr(component, "max_power") and not hasattr(component, "max_release"):
        power = float(getattr(component, "max_power", 0.0) or 0.0)
        return Ok(MinMax(min=0.0, max=power))
    return Ok(MinMax(min=0.0, max=float(getattr(component, "max_release", 0.0) or 0.0)))


@getter
def get_storage_discharge_power_limits(
    component: PLEXOSGenerator, context: PluginContext
) -> Result[MinMax, Any]:
    """Get the output (discharge) active power limits in MW.

    For PLEXOSBattery uses ``max_power``; the unit-annotated Sienna field converts it
    to the device base.
    For PLEXOSStorage uses ``max_release``.
    """
    if hasattr(component, "max_power") and not hasattr(component, "max_release"):
        power = float(getattr(component, "max_power", 0.0) or 0.0)
        return Ok(MinMax(min=0.0, max=power))
    return Ok(MinMax(min=0.0, max=float(getattr(component, "max_release", 0.0) or 0.0)))


@getter
def get_storage_efficiency(component: PLEXOSGenerator, context: PluginContext) -> Result[InputOutput, Any]:
    """Get the storage efficiency as InputOutput (in/out).

    For PLEXOSBattery reads ``charge_efficiency`` and ``discharge_efficiency`` (both in %).
    For PLEXOSStorage defaults to 1.0 for both.
    """
    if hasattr(component, "charge_efficiency"):
        charge = float(getattr(component, "charge_efficiency", 100.0) or 100.0) / 100.0
        discharge = float(getattr(component, "discharge_efficiency", 100.0) or 100.0) / 100.0
        return Ok(InputOutput(input=charge, output=discharge))
    return Ok(InputOutput(input=1.0, output=1.0))


@getter
def get_storage_conversion_factor(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the conversion factor (use capacity_coefficient as proxy)."""
    return Ok(float(getattr(component, "capacity_coefficient", 1.0)))


@getter
def get_gen_ramp_limits(component: PLEXOSGenerator, context: PluginContext) -> Result[UpDown | None, Any]:
    """Get ramp limits from max_ramp_up / max_ramp_down (MW/min).

    Returns None if both values are at the PLEXOS unconstrained default (1e30).
    """
    _UNCONSTRAINED = 1e30  # noqa: N806
    ramp_up = float(getattr(component, "max_ramp_up", _UNCONSTRAINED) or _UNCONSTRAINED)
    ramp_down = float(getattr(component, "max_ramp_down", _UNCONSTRAINED) or _UNCONSTRAINED)
    up_val = None if ramp_up >= _UNCONSTRAINED else ramp_up
    down_val = None if ramp_down >= _UNCONSTRAINED else ramp_down
    if up_val is None and down_val is None:
        return Ok(None)
    return Ok(UpDown(up=up_val or 0.0, down=down_val or 0.0))


@getter
def get_gen_time_limits(component: PLEXOSGenerator, context: PluginContext) -> Result[UpDown | None, Any]:
    """Get time limits from min_up_time / min_down_time (hours).

    Returns None if both are zero (the PLEXOS default, meaning no constraint).
    """
    min_up = float(getattr(component, "min_up_time", 0.0) or 0.0)
    min_down = float(getattr(component, "min_down_time", 0.0) or 0.0)
    if min_up == 0.0 and min_down == 0.0:
        return Ok(None)
    return Ok(UpDown(up=min_up, down=min_down))


@getter
def get_storage_target(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the storage target (target_level or target)."""
    return Ok(float(getattr(component, "target_level", getattr(component, "target", 0.0))))


@getter
def get_storage_cycle_limits(component: PLEXOSGenerator, context: PluginContext) -> Result[int, Any]:
    """Get the cycle limits as an integer (use 'cycle_limits' if available, else 0)."""
    value = getattr(component, "cycle_limits", 10000)
    return Ok(int(value))


@getter
def get_reserve_time_frame(component: PLEXOSGenerator, context: PluginContext) -> Result[float, Any]:
    """Get the timeframe in which the reserve is required (seconds)."""
    return Ok(float(getattr(component, "timeframe", 0.0)))


@getter
def get_reserve_requirement(component: PLEXOSGenerator, context: PluginContext) -> Result[float | None, Any]:
    """Get the value of required reserves in p.u (SYSTEM_BASE)."""
    _sync_time_series_for_source(component, context)
    return Ok(getattr(component, "requirement", 0.0))


@getter
def get_interface_active_power_flow_limits(
    component: PLEXOSInterface, context: PluginContext
) -> Result[MinMax, Any]:
    """Convert interface flow limits from MW to per-unit on the system base."""
    min_flow = float(getattr(component, "min_flow", 0.0))
    max_flow = float(getattr(component, "max_flow", 0.0))
    base_power = _get_target_system_base_power(context)
    return Ok(
        MinMax(
            min=_to_per_unit_power(min_flow, base_power),
            max=_to_per_unit_power(max_flow, base_power),
        )
    )


@getter
def get_interface_direction_mapping(
    component: PLEXOSInterface, context: PluginContext
) -> Result[dict[str, int], Any]:
    """
    Get the direction mapping for a TransmissionInterface.
    This is a placeholder; actual mapping logic depends on your data model.
    """
    direction_mapping = getattr(component, "direction_mapping", {})
    return Ok(direction_mapping)


@getter
def get_trf_active_power_flow(component: PLEXOSTransformer, context: PluginContext) -> Result[float, Any]:
    """Get the active power flow through the transformer."""
    return Ok(getattr(component, "active_power_flow", 0.0))


@getter
def get_trf_reactive_power_flow(component: PLEXOSTransformer, context: PluginContext) -> Result[float, Any]:
    """Get the reactive power flow through the transformer."""
    return Ok(getattr(component, "reactive_power_flow", 0.0))


@getter
def get_trf_primary_shunt(component: PLEXOSTransformer, context: PluginContext) -> Result[Complex, Any]:
    """Map transformer line-charging susceptance to the Sienna primary shunt."""
    susceptance = float(getattr(component, "ac_line_charging_susceptance", 0.0) or 0.0)
    return Ok(Complex(real=0.0, imag=susceptance))


@getter
def get_trf_phase_angle(component: PLEXOSTransformer, context: PluginContext) -> Result[float, Any]:
    """Convert the fixed PLEXOS phase-shift angle from degrees to radians."""
    return Ok(_get_trf_phase_angle_radians(component))


@getter
def get_trf_phase_angle_limits(component: PLEXOSTransformer, context: PluginContext) -> Result[MinMax, Any]:
    """Constrain the phase-shifting transformer to its fixed PLEXOS angle."""
    angle = _get_trf_phase_angle_radians(component)
    return Ok(MinMax(min=angle, max=angle))


@getter
def get_trf_base_power(component: PLEXOSTransformer, context: PluginContext) -> Result[float, Any]:
    """Get the base power of the transformer."""
    return Ok(_get_transformer_base_power(component))


@getter
def get_trf_rating(component: PLEXOSTransformer, context: PluginContext) -> Result[float, Any]:
    """Convert the transformer rating from MW to per-unit on its base power."""
    rating = getattr(component, "rating", None)
    return Ok(_to_per_unit_power(rating, _get_transformer_base_power(component)))


@getter
def get_trf_winding_group_number(
    component: PLEXOSTransformer, context: PluginContext
) -> Result[WindingGroupNumber, Any]:
    """Get the winding group number of the transformer as a WindingGroupNumber enum."""
    return Ok(WindingGroupNumber.UNDEFINED)


@getter
def get_trf_control_objective(
    component: PLEXOSTransformer, context: PluginContext
) -> Result[TransformerControlObjective, Any]:
    """Get the control objective of the transformer as a TransformerControlObjective enum."""
    return Ok(TransformerControlObjective.UNDEFINED)


@getter
def get_reserve_type(component: PLEXOSReserve, context: PluginContext) -> Result[ReserveType, Any]:
    """Get the reserve type for a PLEXOSReserve component as a ReserveType enum."""
    value = getattr(component, "reserve_type", None)
    try:
        return Ok(ReserveType(value))
    except Exception:
        return Ok(ReserveType.SPINNING)


@getter
def get_reserve_direction(component: PLEXOSReserve, context: PluginContext) -> Result[ReserveDirection, Any]:
    """Get the reserve direction for a PLEXOSReserve component as a ReserveDirection enum."""
    value = getattr(component, "direction", None)
    try:
        return Ok(ReserveDirection(value))
    except Exception:
        return Ok(ReserveDirection.UP)


@getter
def get_reserve_sustained_time(component: PLEXOSReserve, context: PluginContext) -> Result[float, Any]:
    """Get the time in seconds reserve contribution must be sustained."""
    return Ok(float(getattr(component, "duration", 3600.0)))


@getter
def get_reserve_max_participation_factor(
    component: PLEXOSReserve, context: PluginContext
) -> Result[float, Any]:
    """Get the maximum portion [0, 1.0] of the reserve that can be contributed per device."""
    return Ok(float(getattr(component, "max_participation_factor", 1.0)))


@getter
def get_reserve_max_output_fraction(component: PLEXOSReserve, context: PluginContext) -> Result[float, Any]:
    """Get the max output fraction (default 1.0)."""
    return Ok(float(getattr(component, "max_output_fraction", 1.0)))


@getter
def get_reserve_deployed_fraction(component: PLEXOSReserve, context: PluginContext) -> Result[float, Any]:
    """Get the fraction of service procurement assumed to be actually deployed."""
    return Ok(float(getattr(component, "deployed_fraction", 1.0)))
