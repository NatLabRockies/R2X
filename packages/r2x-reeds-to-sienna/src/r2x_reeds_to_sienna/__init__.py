"""ReEDS to Sienna translation plugin placeholder."""

from __future__ import annotations

from importlib.metadata import version

from . import getters as _getters  # noqa: F401  # ensure getter registration
from .translation import ReedsToSiennaTranslation

__version__ = version("r2x_reeds_to_sienna")


def hello() -> str:
    """Simple stub to verify package wiring."""
    return "Hello from r2x-reeds-to-sienna!"


__all__ = ["__version__", "ReedsToSiennaTranslation", "hello"]
