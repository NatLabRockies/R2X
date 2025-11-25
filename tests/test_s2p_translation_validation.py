from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_core import Rule


@pytest.fixture(scope="session")
def default_rules() -> list[Rule]:
    """Load the default S2P rules directly from the package config."""
    from r2x_core import Rule

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    return Rule.from_records(rules_data)


@pytest.fixture
def source_system(request):
    """Proxy fixture so parametrized tests can reference existing systems."""
    return request.getfixturevalue(request.param)


def run_translation(source_system, rules):
    """Create a TranslationContext and apply the package rules."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig

    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=rules,
    )
    result = apply_rules_to_context(context)
    return result, target_system


TRANSLATION_CASES = [
    pytest.param("sienna_system_empty", False, id="empty"),
    pytest.param("system_with_5_buses", True, id="five-buses"),
    pytest.param("system_with_thermal_generators", True, id="thermal"),
    pytest.param("system_complete", True, id="complete"),
]


@pytest.mark.parametrize(
    ("source_system", "expect_conversions"),
    TRANSLATION_CASES,
    indirect=["source_system"],
)
def test_translation_pipeline_uses_package_rules(default_rules, source_system, expect_conversions):
    """End-to-end translation validation using only package-provided rules."""
    result, target_system = run_translation(source_system, default_rules)

    assert result.total_rules > 0, "Rules from the package config should execute"

    converted_components = sum(rule_result.converted for rule_result in result.rule_results)
    generated_targets = sum(1 for _ in target_system.iter_all_components())

    if expect_conversions:
        assert converted_components > 0, "Populated systems should convert at least one component"
        assert generated_targets > 0, "Translated systems should emit target components"
    else:
        assert converted_components == 0, "Empty sources should not produce conversions"
        assert generated_targets == 0, "No target components should be emitted for empty sources"
