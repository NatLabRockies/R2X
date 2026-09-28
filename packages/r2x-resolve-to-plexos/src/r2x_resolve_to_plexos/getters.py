"""Getters used by Resolve-to-PLEXOS translation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from infrasys import Component
from plexosdb import CollectionEnum
from r2x_plexos.models import PLEXOSFuel, PLEXOSNode, PLEXOSRegion
from r2x_resolve import (
    InvestmentComponent,
    ResolveFuel,
    ResolveGroupedInterface,
    ResolveLoad,
    ResolveTechnology,
    ResolveTransmissionLine,
    ResolveZone,
)

from r2x_core import Err, Ok, Result
from r2x_core.getters import getter

if TYPE_CHECKING:
    from r2x_core import PluginContext

T = TypeVar("T", bound=Component)

# Fuel burned by each fuel-using technology. Gas & FO burns the natural gas or,
# for oil units (FO_ST, FO_CT), the residual fuel oil priced for its zone group.
FUEL_BY_TECHNOLOGY: dict[ResolveTechnology, str] = {
    ResolveTechnology.ZERO_CARBON_FIRM: "RNG_Tier_1",
    ResolveTechnology.NUCLEAR: "Nuclear",
    ResolveTechnology.BIOMASS: "Biomass",
}
OIL_RESOURCE_PREFIX = "FO_"


def _source(context: PluginContext, component_type: type[T], name: str) -> Result[T, ValueError]:
    """Find a source component by name, including subclasses of ``component_type``."""
    assert context.source_system is not None
    for component in context.source_system.get_components(component_type):
        if component.name == name:
            return Ok(component)
    return Err(ValueError(f"No {component_type.__name__} named '{name}' in the Resolve system"))


def _target(context: PluginContext, component_type: type[T], name: str) -> Result[T, ValueError]:
    """Find a translated component by name."""
    assert context.target_system is not None
    for component in context.target_system.get_components(component_type):
        if component.name == name:
            return Ok(component)
    return Err(ValueError(f"No {component_type.__name__} named '{name}' in the PLEXOS system"))


@getter(name="resolve_zone_category")
def zone_category(component: ResolveZone, context: PluginContext) -> Result[str, ValueError]:
    """Separate the Resolve zones from the external regions they trade with."""
    return Ok("external-zone" if component.ext.get("external") else "resolve-zone")


@getter(name="resolve_region_load")
def region_load(component: ResolveZone, context: PluginContext) -> Result[float, ValueError]:
    """Return the zone's peak demand, or zero for zones without load."""
    assert context.source_system is not None
    demand = (
        load.demand
        for load in context.source_system.get_components(ResolveLoad)
        if load.zone.name == component.name
    )
    return Ok(float(next(demand, 0.0)))


@getter(name="resolve_generator_category")
def generator_category(component: InvestmentComponent, context: PluginContext) -> Result[str, ValueError]:
    """Return the Resolve technology label as the PLEXOS category."""
    return Ok(component.technology.value)


@getter(name="resolve_generator_units")
def generator_units(component: InvestmentComponent, context: PluginContext) -> Result[int, ValueError]:
    """Put units with capacity in service."""
    return Ok(1 if component.capacity > 0 else 0)


@getter(name="resolve_line_max_flow")
def line_max_flow(component: ResolveTransmissionLine, context: PluginContext) -> Result[float, ValueError]:
    """Return the From-to-To rating as Max Flow."""
    return Ok(float(component.max_active_power.from_to))


@getter(name="resolve_line_min_flow")
def line_min_flow(component: ResolveTransmissionLine, context: PluginContext) -> Result[float, ValueError]:
    """Return the negative To-to-From rating as Min Flow."""
    return Ok(-float(component.max_active_power.to_from))


@getter(name="resolve_interface_max_flow")
def interface_max_flow(
    component: ResolveGroupedInterface, context: PluginContext
) -> Result[float, ValueError]:
    """Return the forward limit, or no limit when Resolve has none."""
    return Ok(1e30 if component.forward_limit is None else float(component.forward_limit))


@getter(name="resolve_interface_min_flow")
def interface_min_flow(
    component: ResolveGroupedInterface, context: PluginContext
) -> Result[float, ValueError]:
    """Return the negative reverse limit, or no limit when Resolve has none."""
    return Ok(-1e30 if component.reverse_limit is None else -float(component.reverse_limit))


@getter(name="resolve_membership_parent")
def membership_parent(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the translated component itself as the membership parent."""
    return Ok(component)


@getter(name="resolve_node_region")
def node_region(component: PLEXOSNode, context: PluginContext) -> Result[PLEXOSRegion, ValueError]:
    """Return the Region translated from the same zone as the Node."""
    return _target(context, PLEXOSRegion, component.name)


@getter(name="resolve_generator_node")
def generator_node(component: Any, context: PluginContext) -> Result[PLEXOSNode, ValueError]:
    """Return the Node of the generator's Resolve zone."""
    return _source(context, InvestmentComponent, component.name).and_then(
        lambda unit: _target(context, PLEXOSNode, unit.zone.name)
    )


def _fuel_name(unit: InvestmentComponent, context: PluginContext) -> Result[str, ValueError]:
    """Name the Resolve fuel a unit burns."""
    if unit.technology is not ResolveTechnology.GAS_FO:
        fuel = FUEL_BY_TECHNOLOGY.get(unit.technology)
        if fuel is None:
            return Err(ValueError(f"No fuel defined for {unit.technology.value} unit '{unit.name}'"))
        return Ok(fuel)

    resource_type = str(unit.ext.get("resource_type") or "")
    fuel_type = "RFO" if resource_type.startswith(OIL_RESOURCE_PREFIX) else "NG"
    assert context.source_system is not None
    for fuel in context.source_system.get_components(ResolveFuel):
        zones = fuel.ext.get("zones")
        if fuel.fuel_type == fuel_type and isinstance(zones, list) and unit.zone.name in zones:
            return Ok(fuel.name)
    return Err(ValueError(f"No {fuel_type} fuel priced for zone '{unit.zone.name}' (unit '{unit.name}')"))


@getter(name="resolve_generator_fuel")
def generator_fuel(component: Any, context: PluginContext) -> Result[PLEXOSFuel, ValueError]:
    """Return the Fuel the generator burns."""
    return (
        _source(context, InvestmentComponent, component.name)
        .and_then(lambda unit: _fuel_name(unit, context))
        .and_then(lambda name: _target(context, PLEXOSFuel, name))
    )


@getter(name="resolve_line_from_node")
def line_from_node(component: Any, context: PluginContext) -> Result[PLEXOSNode, ValueError]:
    """Return the Node the line flows from."""
    return _source(context, ResolveTransmissionLine, component.name).and_then(
        lambda line: _target(context, PLEXOSNode, line.from_zone.name)
    )


@getter(name="resolve_line_to_node")
def line_to_node(component: Any, context: PluginContext) -> Result[PLEXOSNode, ValueError]:
    """Return the Node the line flows to."""
    return _source(context, ResolveTransmissionLine, component.name).and_then(
        lambda line: _target(context, PLEXOSNode, line.to_zone.name)
    )


@getter(name="resolve_collection_region")
def collection_region(component: Any, context: PluginContext) -> Result[CollectionEnum, ValueError]:
    """Return the Node.Region collection."""
    return Ok(CollectionEnum.Region)


@getter(name="resolve_collection_nodes")
def collection_nodes(component: Any, context: PluginContext) -> Result[CollectionEnum, ValueError]:
    """Return the Generator.Nodes collection."""
    return Ok(CollectionEnum.Nodes)


@getter(name="resolve_collection_fuels")
def collection_fuels(component: Any, context: PluginContext) -> Result[CollectionEnum, ValueError]:
    """Return the Generator.Fuels collection."""
    return Ok(CollectionEnum.Fuels)


@getter(name="resolve_collection_node_from")
def collection_node_from(component: Any, context: PluginContext) -> Result[CollectionEnum, ValueError]:
    """Return the Line.NodeFrom collection."""
    return Ok(CollectionEnum.NodeFrom)


@getter(name="resolve_collection_node_to")
def collection_node_to(component: Any, context: PluginContext) -> Result[CollectionEnum, ValueError]:
    """Return the Line.NodeTo collection."""
    return Ok(CollectionEnum.NodeTo)
