"""ReEDS to Sienna translation plugin placeholder."""

from __future__ import annotations

from importlib.metadata import version

from . import getters as _getters  # noqa: F401  # ensure getter registration
from .plugin_config import ReEDSToSiennaConfig
from .translation import reeds_to_sienna

__version__ = version("r2x_reeds_to_sienna")


__all__ = ["__version__", "ReEDSToSiennaConfig", "reeds_to_sienna"]
