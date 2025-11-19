"""R2X ReEDS to PLEXOS Translation Plugin."""

from importlib.metadata import version

from loguru import logger

from .plugin_config import ReedsToPlexosConfig

__version__ = version("r2x_reeds_to_plexos")


logger.disable("r2x_reeds_to_plexos")


__all__ = [
    "ReedsToPlexosConfig",
    "__version__",
]
