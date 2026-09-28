"""Resolve-to-PLEXOS translation entry point."""

from __future__ import annotations

import json
from importlib.resources import files

from r2x_core import PluginContext, Rule, System, apply_rules_to_context, expose_plugin

from .attach import add_interface_lines, attach_generator_profiles, attach_region_load
from .plugin_config import ResolveToPlexosConfig
from .validation import validate_component_counts


@expose_plugin
def resolve_to_plexos(system: System, config: ResolveToPlexosConfig) -> System:
    """Translate a Resolve system into PLEXOS component models."""
    context = PluginContext(source_system=system, config=config)
    rules_path = files("r2x_resolve_to_plexos.config") / "translation_rules.json"
    context.rules = tuple(Rule.from_records(json.loads(rules_path.read_text())))
    context.target_system = System(name="PLEXOS", auto_add_composed_components=True)

    translation_result = apply_rules_to_context(context)
    if translation_result.failed_rules:
        failures = "; ".join(
            result.error or str(result.rule)
            for result in translation_result.rule_results
            if not result.success
        )
        raise ValueError(f"Resolve-to-PLEXOS translation failed: {failures}")

    attach_region_load(context)
    attach_generator_profiles(context)
    add_interface_lines(context)

    validation = validate_component_counts(system, context.target_system)
    if validation.is_err():
        raise ValueError(validation.error)
    return context.target_system
