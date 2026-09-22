"""Getters used by Resolve-to-PLEXOS translation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infrasys import Component
from plexosdb import CollectionEnum

from r2x_core import Err, Ok, Result
from r2x_core.getters import getter

if TYPE_CHECKING:
    from r2x_core import PluginContext


def _target_by_name(context: PluginContext, component_type: type[Any], name: str) -> Any | None:
    """Find a target component by its public name."""
    if context.target_system is None:
        return None
    return next(
        (item for item in context.target_system.get_components(component_type) if item.name == name),
        None,
    )


def _source_by_type_name(context: PluginContext, type_name: str, name: str) -> Any | None:
    """Find a source component by class name and public name."""
    if context.source_system is None:
        return None
    return next(
        (
            item
            for item in context.source_system.get_components(Component)
            if type(item).__name__ == type_name and item.name == name
        ),
        None,
    )


@getter(name="resolve_get_units")
def get_units(component: Any, context: PluginContext) -> Result[int, ValueError]:
    """Return the PLEXOS in-service flag for a Resolve component."""
    return Ok(1)


@getter(name="resolve_get_generator_capacity")
def get_generator_capacity(component: Any, context: PluginContext) -> Result[float, ValueError]:
    """Map Resolve generator capacity to PLEXOS capacity fields."""
    return Ok(float(component.capacity_mw))


@getter(name="resolve_get_generator_category")
def get_generator_category(component: Any, context: PluginContext) -> Result[str, ValueError]:
    """Return the Resolve technology as the PLEXOS generator category."""
    technology = (getattr(component, "ext", None) or {}).get("technology")
    return Ok(str(technology or "resolve-generator"))


def _resolve_generator_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Resolve a generator's zone to its translated PLEXOS node."""
    from r2x_plexos.models import PLEXOSNode

    zone_name = getattr(getattr(component, "zone", None), "name", None)
    if zone_name is None:
        return Err(ValueError(f"Resolve generator '{component.name}' has no zone"))
    node = _target_by_name(context, PLEXOSNode, zone_name)
    if node is None:
        return Err(ValueError(f"No PLEXOSNode found for Resolve zone '{zone_name}'"))
    return Ok(node)


@getter(name="resolve_get_generator_node")
def get_generator_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Resolve a generator's zone to its translated PLEXOS node."""
    return _resolve_generator_node(component, context)


@getter(name="resolve_get_load_value")
def get_load_value(component: Any, context: PluginContext) -> Result[float, ValueError]:
    """Map Resolve load demand to the PLEXOS purchaser maximum load."""
    return Ok(float(component.demand_mw))


def _resolve_load_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Resolve a load's zone to its translated PLEXOS node."""
    from r2x_plexos.models import PLEXOSNode

    zone_name = getattr(getattr(component, "zone", None), "name", None)
    if zone_name is None:
        return Err(ValueError(f"Resolve load '{component.name}' has no zone"))
    node = _target_by_name(context, PLEXOSNode, zone_name)
    if node is None:
        return Err(ValueError(f"No PLEXOSNode found for Resolve zone '{zone_name}'"))
    return Ok(node)


@getter(name="resolve_get_load_node")
def get_load_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Resolve a load's zone to its translated PLEXOS node."""
    return _resolve_load_node(component, context)


@getter(name="resolve_get_interface_max_flow")
def get_interface_max_flow(component: Any, context: PluginContext) -> Result[float, ValueError]:
    """Map the Resolve transfer limit to PLEXOS maximum flow."""
    return Ok(float(component.transfer_limit_mw))


@getter(name="resolve_get_interface_min_flow")
def get_interface_min_flow(component: Any, context: PluginContext) -> Result[float, ValueError]:
    """Map a Resolve transfer limit to a symmetric PLEXOS minimum flow."""
    return Ok(-float(component.transfer_limit_mw))


def _interface_node(component: Any, context: PluginContext, *, from_side: bool) -> Result[Any, ValueError]:
    """Resolve one interface endpoint to a translated PLEXOS node."""
    from r2x_plexos.models import PLEXOSNode

    zone_attr = "from_zone" if from_side else "to_zone"
    zone_name = getattr(getattr(component, zone_attr, None), "name", None)
    if zone_name is None:
        return Err(ValueError(f"Resolve interface '{component.name}' has incomplete zone data"))
    node = _target_by_name(context, PLEXOSNode, zone_name)
    if node is None:
        return Err(ValueError(f"No PLEXOSNode found for Resolve zone '{zone_name}'"))
    return Ok(node)


def _resolve_interface_from_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the translated origin node for a Resolve interface."""
    return _interface_node(component, context, from_side=True)


@getter(name="resolve_get_interface_from_node")
def get_interface_from_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the translated origin node for a Resolve interface."""
    return _resolve_interface_from_node(component, context)


def _resolve_interface_to_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the translated destination node for a Resolve interface."""
    return _interface_node(component, context, from_side=False)


@getter(name="resolve_get_interface_to_node")
def get_interface_to_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the translated destination node for a Resolve interface."""
    return _resolve_interface_to_node(component, context)


@getter(name="resolve_membership_parent_component")
def membership_parent_component(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the target component as the membership parent."""
    return Ok(component)


@getter(name="resolve_generator_membership_child_node")
def generator_membership_child_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Resolve a PLEXOS generator membership child from its Resolve source."""
    source = _source_by_type_name(context, "ResolveGenerator", component.name)
    if source is None:
        return Err(ValueError(f"No Resolve generator found for '{component.name}'"))
    return _resolve_generator_node(source, context)


@getter(name="resolve_interface_membership_child_from_node")
def interface_membership_child_from_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Resolve an interface membership's origin node from its Resolve source."""
    source = _source_by_type_name(context, "ResolveInterface", component.name)
    if source is None:
        return Err(ValueError(f"No Resolve interface found for '{component.name}'"))
    return _resolve_interface_from_node(source, context)


@getter(name="resolve_interface_membership_child_to_node")
def interface_membership_child_to_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Resolve an interface membership's destination node from its Resolve source."""
    source = _source_by_type_name(context, "ResolveInterface", component.name)
    if source is None:
        return Err(ValueError(f"No Resolve interface found for '{component.name}'"))
    return _resolve_interface_to_node(source, context)


@getter(name="resolve_load_membership_child_node")
def load_membership_child_node(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Resolve a PLEXOS purchaser's zone node from its Resolve source."""
    source = _source_by_type_name(context, "ResolveLoad", component.name)
    if source is None:
        return Err(ValueError(f"No Resolve load found for '{component.name}'"))
    return _resolve_load_node(source, context)


@getter(name="resolve_membership_nodes_collection")
def membership_nodes_collection(component: Any, context: PluginContext) -> Result[CollectionEnum, ValueError]:
    """Return the PLEXOS Nodes collection."""
    return Ok(CollectionEnum.Nodes)


@getter(name="resolve_membership_node_from_collection")
def membership_node_from_collection(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the PLEXOS NodeFrom collection."""
    return Ok(CollectionEnum.NodeFrom)


@getter(name="resolve_membership_node_to_collection")
def membership_node_to_collection(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the PLEXOS NodeTo collection."""
    return Ok(CollectionEnum.NodeTo)
