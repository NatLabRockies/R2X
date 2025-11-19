"""R2X Sienna to PLEXOS Translation Plugin.

A plugin for translating Sienna model systems to PLEXOS format within the R2X framework.
"""

from importlib.metadata import version

from loguru import logger

from .plugin_config import SiennaToPlexosConfig

__version__ = version("r2x_sienna_to_plexos")


logger.disable("r2x_sienna_to_plexos")


__all__ = [
    "Rule",
    "RuleResult",
    "SiennaToPlexosConfig",
    "__version__",
]
