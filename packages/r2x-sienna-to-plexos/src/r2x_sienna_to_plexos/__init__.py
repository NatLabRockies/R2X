"""R2X Sienna to PLEXOS Translation Plugin.

A plugin for translating Sienna model systems to PLEXOS format within the R2X framework.
"""

from importlib.metadata import version

from loguru import logger

from .getters import (
    SOURCE_GENERATOR_TYPES,
    membership_component_child_node,
    membership_interface_child_line,
    membership_line_from_parent_node,
    membership_line_to_parent_node,
    membership_region_child_node,
    membership_region_parent_node,
    membership_reserve_child_battery,
    membership_reserve_child_generator,
)
from .getters_utils import (
    ensure_battery_node_memberships,
    ensure_generator_node_memberships,
    ensure_head_storage_generator_membership,
    ensure_interface_line_memberships,
    ensure_node_zone_memberships,
    ensure_region_node_memberships,
    ensure_reserve_battery_memberships,
    ensure_reserve_generator_memberships,
    ensure_tail_storage_generator_membership,
    ensure_transformer_node_memberships,
)
from .plugin_config import SiennaToPlexosConfig

__version__ = version("r2x_sienna_to_plexos")


logger.disable("r2x_sienna_to_plexos")


__all__ = [
    "SiennaToPlexosConfig",
    "__version__",
    "SOURCE_GENERATOR_TYPES",
    "ensure_region_node_memberships",
    "ensure_interface_line_memberships",
    "ensure_generator_node_memberships",
    "ensure_battery_node_memberships",
    "ensure_node_zone_memberships",
    "ensure_reserve_battery_memberships",
    "ensure_reserve_generator_memberships",
    "ensure_transformer_node_memberships",
    "ensure_head_storage_generator_membership",
    "ensure_tail_storage_generator_membership",
    "membership_region_parent_node",
    "membership_region_child_node",
    "membership_reserve_child_generator",
    "membership_reserve_child_battery",
    "membership_line_from_parent_node",
    "membership_line_to_parent_node",
    "membership_component_child_node",
    "membership_interface_child_line",
]
