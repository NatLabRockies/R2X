"""Plugin registration for R2X translations.

DEPRECATED: This module is deprecated. Use `r2x.modifiers` instead.
This module now re-exports from modifiers for backwards compatibility.
"""

from r2x.modifiers import (
    plexos_to_sienna_modifier as _plexos_to_sienna_modifier,
)
from r2x.modifiers import (
    validate_plexos_modifier as _validate_plexos_modifier,
)

__all__ = [
    "_plexos_to_sienna_modifier",
    "_validate_plexos_modifier",
    "register_plugin",
]


def register_plugin() -> None:
    """Register all translation system modifiers.

    This function is a no-op as modifiers are auto-registered at import time.
    Kept for backwards compatibility.

    Registered modifiers:
    - plexos_to_sienna: PLEXOS → Sienna translation
    - validate_plexos: PLEXOS system validation
    """
