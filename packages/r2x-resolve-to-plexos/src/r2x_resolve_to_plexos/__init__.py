"""R2X Resolve-to-PLEXOS translation plugin."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from loguru import logger

from . import getters as _getters  # noqa: F401
from .plugin_config import ResolveToPlexosConfig
from .translation import resolve_to_plexos
from .validation import validate_component_counts

logger.disable("r2x_resolve_to_plexos")

try:
    __version__ = version("r2x-resolve-to-plexos")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = [
    "ResolveToPlexosConfig",
    "__version__",
    "resolve_to_plexos",
    "validate_component_counts",
]
