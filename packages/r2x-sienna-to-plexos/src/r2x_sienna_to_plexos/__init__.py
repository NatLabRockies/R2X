"""R2X Sienna to PLEXOS Translation Plugin.

A plugin for translating Sienna model systems to PLEXOS format within the R2X framework.
"""

from importlib.metadata import version

from loguru import logger

from .getters import (
    membership_line_from_parent_node,
    membership_line_to_parent_node,
    membership_region_child_node,
    membership_region_parent_node,
)
from .getters_utils import (
    ensure_region_node_memberships,
)
from .plugin_config import SiennaToPlexosConfig

__version__ = version("r2x_sienna_to_plexos")


logger.disable("r2x_sienna_to_plexos")


__all__ = [
    "SiennaToPlexosConfig",
    "__version__",
    "ensure_region_node_memberships",
    "membership_region_parent_node",
    "membership_region_child_node",
    "membership_line_from_parent_node",
    "membership_line_to_parent_node",
]
