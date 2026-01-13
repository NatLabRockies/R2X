from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

if TYPE_CHECKING:
    from r2x_core import TranslationContext


def perform_translation(system: System) -> System:
    """
    Perform the ReEDS to Sienna translation.

    Args:
        system: The input ReEDS system to be translated.

    Returns:
        The translated Sienna system.
    """
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    sienna_system = System(name="Sienna", auto_add_composed_components=True)

    plugin_config = PluginConfig(
        models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters")
    )

    context = TranslationContext(
        source_system=system,
        target_system=sienna_system,
        config=plugin_config,
        rules=rules,
    )

    apply_rules_to_context(context)

    return context.target_system
