"""R2X ReEDS to PLEXOS Translation Plugin."""

from importlib.metadata import version

from loguru import logger

from . import getters as _getters  # noqa: F401  # ensure getter registration
from .getters_utils import (
    attach_emissions_to_generators,
    attach_region_load_profiles,
    convert_pumped_storage_generators,
    ensure_region_node_memberships,
    link_line_memberships,
)
from .plugin_config import ReedsToPlexosConfig

__version__ = version("r2x_reeds_to_plexos")


logger.disable("r2x_reeds_to_plexos")


__all__ = [
    "ReedsToPlexosConfig",
    "__version__",
    "attach_emissions_to_generators",
    "attach_region_load_profiles",
    "convert_pumped_storage_generators",
    "ensure_region_node_memberships",
    "link_line_memberships",
]
