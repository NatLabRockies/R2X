"""R2X PLEXOS to Sienna Translation Plugin.

A plugin for translating PLEXOS model systems to Sienna format within the R2X framework.
"""

from importlib.metadata import version

from loguru import logger

from .getters import *  # noqa: F403
from .plugin_config import PlexosToSiennaConfig
from .translation import plexos_to_sienna

__version__ = version("r2x_plexos_to_sienna")


logger.disable("r2x_plexos_to_sienna")


__all__ = [
    "PlexosToSiennaConfig",
    "plexos_to_sienna",
    "__version__",
]


def hello() -> str:
    return "Hello from r2x-plexos-to-sienna!"
