"""R2X ReEDS to PLEXOS Translation Plugin."""

from __future__ import annotations

from importlib.metadata import version

from loguru import logger

from . import getters as _getters  # noqa: F401  # ensure getter registration
from .getters_utils import (
    attach_emissions_to_generators,
    attach_region_load_time_series,
    attach_reserve_time_series,
    attach_time_series_to_generators,
    convert_pumped_storage_generators,
    ensure_generator_node_memberships,
    ensure_region_node_memberships,
    link_line_memberships,
)
from .plugin_config import ReedsToPlexosConfig
from .translation import reeds_to_plexos

__version__ = version("r2x_reeds_to_plexos")


logger.disable("r2x_reeds_to_plexos")


__all__ = [
    "ReedsToPlexosConfig",
    "__version__",
    "attach_region_load_time_series",
    "attach_reserve_time_series",
    "attach_emissions_to_generators",
    "convert_pumped_storage_generators",
    "ensure_generator_node_memberships",
    "ensure_region_node_memberships",
    "link_line_memberships",
    "attach_time_series_to_generators",
    "reeds_to_plexos",
]
