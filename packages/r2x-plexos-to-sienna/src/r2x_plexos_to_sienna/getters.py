"""Getter functions for rules."""

from __future__ import annotations

from typing import Any

from infrasys.cost_curves import FuelCurve
from infrasys.value_curves import LinearCurve
from r2x_plexos.models import PLEXOSGenerator, PLEXOSLine, PLEXOSNode
from r2x_sienna.models import ACBus, Arc
from r2x_sienna.models.costs import ThermalGenerationCost
from r2x_sienna.models.enums import ACBusTypes, PrimeMoversType, ThermalFuels
from r2x_sienna.models.named_tuples import FromTo_ToFrom, MinMax

from r2x_core import Ok, Result, TranslationContext, UnitSystem
from r2x_core.getters import getter


@getter
def get_base_voltage(_: TranslationContext, component: PLEXOSNode) -> Result[float, Any]:
    """Get the voltage of a node."""
    value = getattr(component, "voltage", 0.0)
    return Ok(value)


@getter
def get_node_ext(_: TranslationContext, component: PLEXOSNode) -> Result[dict[str, Any], Any]:
    """Get the ext dictionary for a node."""
    value = {
        "load_participation_factor": getattr(component, "load_participation_factor", None),
    }
    return Ok(value)


@getter
def get_node_number(_: TranslationContext, component: PLEXOSNode) -> Result[int, Any]:
    """Assign sequential node numbers starting from 1 if not present."""
    _node_number_counter = 1
    if hasattr(component, "number") and component.number is not None:
        return Ok(component.number)
    value = _node_number_counter
    _node_number_counter += 1
    return Ok(value)  # TODO: look for actual number in the name of the node


@getter
def is_slack_bus(_: TranslationContext, component: PLEXOSNode) -> Result[ACBusTypes, Any]:
    """Return ACBusTypes.SLACK if component.bustype == 1, else ACBusTypes.PQ."""
    value = getattr(component, "is_slack_bus", 0)
    bustype = ACBusTypes.SLACK if value == 1 else ACBusTypes.PQ
    return Ok(bustype)


@getter
def get_line_arc(context: TranslationContext, component: PLEXOSLine) -> Result[Arc, Any]:
    """Get the arc of a line by querying PlexosDB for node memberships and matching to ACBus objects."""
    memberships: list[dict[str, Any]] = []
    from_node = None
    to_node = None
    for m in memberships:
        if m.get("child_class_name") == "Node":
            if m.get("collection_name") == "Node From":
                from_node = m.get("child_name")
            elif m.get("collection_name") == "Node To":
                to_node = m.get("child_name")
        if from_node and to_node:
            break

    if not from_node or not to_node:
        raise ValueError(
            f"Could not find both nodes for line {component.name}. " f"Memberships: {memberships}"
        )

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
def get_gen_active_power(_: TranslationContext, component: PLEXOSGenerator) -> Result[float, Any]:
    """Get the active power of a generator."""
    value = getattr(component, "max_capacity", 0.0)
    return Ok(float(value))


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
def get_gen_must_run(_: TranslationContext, component: PLEXOSGenerator) -> Result[bool, Any]:
    """Get the must-run status of a generator."""
    value = getattr(component, "must_run", True)
    return Ok(bool(value))


@getter
def get_prime_mover_type(_: TranslationContext, component: PLEXOSGenerator) -> Result[str, Any]:
    """Get the prime mover type of a generator. If thermal, set to PrimeMoversType.CC."""
    value = PrimeMoversType.CC if getattr(component, "category", None) == "thermal" else PrimeMoversType.HY
    return Ok(str(value))


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
