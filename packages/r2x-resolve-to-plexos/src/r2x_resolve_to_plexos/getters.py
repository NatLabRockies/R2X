"""Getters used by Resolve-to-PLEXOS translation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from infrasys import Component
from plexosdb import CollectionEnum
from r2x_plexos.models import PLEXOSNode, PLEXOSRegion
from r2x_resolve import (
    InvestmentComponent,
    ReserveDirection,
    ResolveFuelType,
    ResolveGenerator,
    ResolveGroupedInterface,
    ResolveLoad,
    ResolvePrimeMover,
    ResolveReserve,
    ResolveTechnology,
    ResolveTransmissionLine,
    ResolveZone,
)

from r2x_core import Err, Ok, Result
from r2x_core.getters import getter

if TYPE_CHECKING:
    from r2x_core import PluginContext

T = TypeVar("T", bound=Component)

# PLEXOS Generator category for every technology except Gas & FO, which is
# named from its fuel and prime mover below.
CATEGORY_BY_TECHNOLOGY: dict[ResolveTechnology, str] = {
    ResolveTechnology.NUCLEAR: "Nuclear",
    ResolveTechnology.ZERO_CARBON_FIRM: "Zero-Carbon Firm",
    ResolveTechnology.BIOMASS: "Biomass",
    ResolveTechnology.IN_STATE_HYDRO: "Hydro",
    ResolveTechnology.HYDRO_IMPORTS_EXISTING: "Hydro Imports",
    ResolveTechnology.HYDRO_IMPORTS_NEW: "Hydro Imports",
    ResolveTechnology.WIND: "Wind",
    ResolveTechnology.WIND_IMPORTS: "Wind Imports",
    ResolveTechnology.OFFSHORE_WIND: "Offshore Wind",
    ResolveTechnology.SOLAR: "Solar",
    ResolveTechnology.BATTERY_STORAGE: "Battery Storage",
    ResolveTechnology.PUMPED_STORAGE: "Pumped Storage",
}
# Gas & FO units split by existing resource type carry their fuel and prime mover;
# new and unsplit units are the mixed aggregate.
GAS_FO_CATEGORY_BY_CLASSIFICATION: dict[tuple[ResolveFuelType, ResolvePrimeMover], str] = {
    (ResolveFuelType.NATURAL_GAS, ResolvePrimeMover.CC): "Gas CC",
    (ResolveFuelType.NATURAL_GAS, ResolvePrimeMover.ST): "Gas ST",
    (ResolveFuelType.NATURAL_GAS, ResolvePrimeMover.CT): "Gas CT",
    (ResolveFuelType.FUEL_OIL, ResolvePrimeMover.ST): "Oil ST",
    (ResolveFuelType.FUEL_OIL, ResolvePrimeMover.CT): "Oil CT",
    (ResolveFuelType.GAS_FUEL_OIL, ResolvePrimeMover.MIXED): "Gas & FO",
}


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
    """Name the generator's type: fuel and prime mover for Gas & FO, else its technology."""
    if component.technology is not ResolveTechnology.GAS_FO:
        return Ok(CATEGORY_BY_TECHNOLOGY[component.technology])
    if not isinstance(component, ResolveGenerator):
        return Err(ValueError(f"Gas & FO unit '{component.name}' is not a ResolveGenerator"))
    category = GAS_FO_CATEGORY_BY_CLASSIFICATION.get((component.fuel_type, component.prime_mover_type))
    if category is None:
        return Err(
            ValueError(
                f"No PLEXOS category for Gas & FO unit '{component.name}' with fuel "
                f"{component.fuel_type.value} and prime mover {component.prime_mover_type.value}"
            )
        )
    return Ok(category)


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


# PLEXOS Reserve Type: 1 raises, 2 lowers. Every reserve uses only these two so that
# no capacity counts toward two reserve types at once.
RESERVE_TYPE_BY_DIRECTION: dict[ReserveDirection, int] = {
    ReserveDirection.UP: 1,
    ReserveDirection.DOWN: 2,
}


@getter(name="resolve_reserve_type")
def reserve_type(component: ResolveReserve, context: PluginContext) -> Result[int, ValueError]:
    """Return PLEXOS Reserve Type 1 (raise) for Up reserves and 2 (lower) for Down."""
    return Ok(RESERVE_TYPE_BY_DIRECTION[component.direction])


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


@getter(name="resolve_collection_node_from")
def collection_node_from(component: Any, context: PluginContext) -> Result[CollectionEnum, ValueError]:
    """Return the Line.NodeFrom collection."""
    return Ok(CollectionEnum.NodeFrom)


@getter(name="resolve_collection_node_to")
def collection_node_to(component: Any, context: PluginContext) -> Result[CollectionEnum, ValueError]:
    """Return the Line.NodeTo collection."""
    return Ok(CollectionEnum.NodeTo)
