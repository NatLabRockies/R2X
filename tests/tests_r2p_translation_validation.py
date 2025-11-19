from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_core import Rule


@pytest.fixture(scope="session")
def r2p_default_rules() -> list[Rule]:
    """Load the packaged ReEDS-to-PLEXOS rules."""
    from r2x_core import Rule

    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    return Rule.from_records(json.loads(rules_path.read_text()))


def build_r2p_context(source_system, rules):
    """Helper to construct a translation context for ReEDS-to-PLEXOS."""
    from r2x_reeds_to_plexos import ReedsToPlexosConfig

    from r2x_core import System, TranslationContext

    target_system = System(name="plexos_target", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=rules,
    )
    return context


def test_r2p_translation_executes_with_package_rules(r2p_default_rules, reeds_system_example):
    """End-to-end smoke test that runs only the packaged default ReEDS rules."""
    from r2x_core import apply_rules_to_context

    context = build_r2p_context(reeds_system_example, r2p_default_rules)
    result = apply_rules_to_context(context)

    assert result.total_rules > 0, "Rules from the package config should run"

    converted = sum(rule_result.converted for rule_result in result.rule_results)
    assert converted > 0, "ReEDS systems with generators should emit PLEXOS components"


def test_r2p_generators_carry_capacity_and_outage_data(r2p_default_rules, reeds_system_example):
    """Verify generator attributes make it into the translated PLEXOS components."""
    from r2x_plexos.models.generator import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSGenerator

    from r2x_core import apply_rules_to_context

    context = build_r2p_context(reeds_system_example, r2p_default_rules)
    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    target_generators = list(context.target_system.get_components(PLEXOSGenerator))
    assert target_generators, "ReEDS generators should produce at least one PLEXOS generator"

    reeds_capacity = {gen.name: gen.capacity for gen in reeds_system_example.get_components(ReEDSGenerator)}
    reeds_outage = {
        gen.name: gen.forced_outage_rate for gen in reeds_system_example.get_components(ReEDSGenerator)
    }

    for plexos_gen in target_generators:
        expected_capacity = reeds_capacity.get(plexos_gen.name)
        expected_outage = reeds_outage.get(plexos_gen.name)
        assert expected_capacity is not None, f"Unexpected generator {plexos_gen.name} created"
        assert pytest.approx(expected_capacity) == plexos_gen.max_capacity, "Capacity should carry over"
        if expected_outage is not None:
            assert pytest.approx(expected_outage * 100.0) == plexos_gen.forced_outage_rate, (
                "Forced outage rate should be converted to %"
            )
