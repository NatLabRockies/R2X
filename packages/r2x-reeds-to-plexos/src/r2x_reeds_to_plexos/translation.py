from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

from r2x_core import Rule, System, TranslationContext, apply_rules_to_context

from .getters_utils import (
    attach_region_load_time_series,
    attach_reserve_time_series,
    attach_time_series_to_generators,
)
from .plugin_config import ReedsToPlexosConfig

if TYPE_CHECKING:
    from r2x_core import Rule, TranslationContext


def perform_translation(system: System):
    """
    Perform the ReEDS to PLEXOS translation.

    Args:
        reeds_system: The input ReEDS system to be translated.

    Returns:
        The translated PLEXOS system.
    """
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    plexos_system = System(name="PLEXOS", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=system,
        target_system=plexos_system,
        config=ReedsToPlexosConfig(),
        rules=rules,
    )
    apply_rules_to_context(context)
    attach_reserve_time_series(context)
    attach_time_series_to_generators(context)
    attach_region_load_time_series(context)

    return context.target_system
