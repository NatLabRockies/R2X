"""R2X PLEXOS to Sienna Translation Plugin.

A plugin for translating PLEXOS model systems to Sienna format within the R2X framework.
"""

from importlib.metadata import version

from loguru import logger

from .getters import *  # noqa: F403
from .plugin_config import PlexosToSiennaConfig
from .translation import plexos_to_sienna
from .utils import (
    attach_constant_load_time_series as attach_constant_load_time_series,
)
from .utils import (
    extract_number_from_name as extract_number_from_name,
)
from .utils import (
    normalize_renewable_max_active_power_time_series as normalize_renewable_max_active_power_time_series,
)
from .utils import (
    normalize_reserve_requirement_time_series as normalize_reserve_requirement_time_series,
)

__version__ = version("r2x_plexos_to_sienna")


logger.disable("r2x_plexos_to_sienna")


__all__ = [
    "PlexosToSiennaConfig",
    "__version__",
    "plexos_to_sienna",
]


def hello() -> str:
    return "Hello from r2x-plexos-to-sienna!"
