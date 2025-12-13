"""Transformation rule fixtures for converter testing.

Provides reusable Rule instances with various configurations:
- Simple single-field rules
- Multi-field rules with getters
- Rules with default values
- Complete rule lists for TranslationContext

These fixtures demonstrate the full range of rule capabilities and serve
as templates for defining new conversion rules in the codebase.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_core import Rule


@pytest.fixture
def rule_simple() -> Rule:
    """Single-field transformation rule (ACBus → PLEXOSNode)."""
    from r2x_core import Rule

    return Rule(
        source_type="ACBus",
        target_type="PLEXOSNode",
        version=1,
        field_map={
            "name": "name",
            "uuid": "uuid",
        },
        getters={},
        defaults={},
    )


@pytest.fixture
def rule_multifield() -> Rule:
    """Multi-field transformation rule with getter (Generator → PLEXOSGenerator)."""
    from r2x_core import Rule

    def aggregate_load(ctx, component):
        """Aggregate multiple power fields into single total."""
        from r2x_core import Ok

        result = getattr(component, "rating", 0.0) * component.base_power
        return Ok(result)

    return Rule(
        source_type="ThermalStandard",
        target_type="PLEXOSGenerator",
        version=1,
        field_map={
            "name": "name",
            "Max Capacity": ["rating", "base_power"],
        },
        getters={
            "Max Capacity": aggregate_load,
        },
        defaults={},
    )


@pytest.fixture
def rule_with_defaults() -> Rule:
    """Rule with default values (Bus → Node)."""
    from r2x_core import Rule

    return Rule(
        source_type="Bus",
        target_type="Node",
        version=1,
        field_map={
            "name": "name",
            "category": "category",
        },
        getters={},
        defaults={
            "category": "other",
        },
    )


@pytest.fixture
def rule_with_all_features() -> Rule:
    """Comprehensive rule demonstrating all Rule features."""
    from r2x_core import Rule

    def compute_total_rating(ctx, component):
        from r2x_core import Ok

        base = getattr(component, "base_rating", 0.0)
        premium = getattr(component, "premium_rating", 0.0)
        return Ok(float(base + premium))

    return Rule(
        source_type="Equipment",
        target_type="PLEXOSEquipment",
        version=1,
        field_map={
            "name": "name",
            "uuid": "uuid",
            "total_rating": ["base_rating", "premium_rating"],
            "category": "category",
        },
        getters={
            "total_rating": compute_total_rating,
        },
        defaults={
            "category": "standard",
        },
    )


@pytest.fixture
def rules_list(rule_simple, rule_multifield, rule_with_defaults) -> list[Rule]:
    """List of multiple rules for TranslationContext initialization."""
    return [
        rule_simple,
        rule_multifield,
        rule_with_defaults,
    ]


@pytest.fixture
def rule_list_versioned() -> list[Rule]:
    """List of rules with multiple versions for same conversion."""
    from r2x_core import Rule

    rule_v1 = Rule(
        source_type="Bus",
        target_type="Node",
        version=1,
        field_map={
            "name": "name",
        },
    )

    rule_v2 = Rule(
        source_type="Bus",
        target_type="Node",
        version=2,
        field_map={
            "name": "name",
            "extra": "extra",
        },
    )

    return [rule_v1, rule_v2]


@pytest.fixture
def rules_from_config() -> list[Rule]:
    """Load the real transformation rules from the packaged config file."""
    from r2x_core import Rule

    config_dir = files("r2x_sienna_to_plexos.config")
    rules_file = config_dir / "rules.json"
    rules_data = json.loads(rules_file.read_text())
    return Rule.from_records(rules_data)
