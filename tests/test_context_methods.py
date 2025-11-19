import pytest


def test_get_rule_by_types_and_version(context):
    """Retrieve rule by source type, target type, and explicit version."""
    rule = context.get_rule("ACBus", "PLEXOSNode", version=1)

    assert rule.source_type == "ACBus"
    assert rule.target_type == "PLEXOSNode"
    assert rule.version == 1


def test_get_rule_not_found_raises_keyerror(context):
    """Retrieve non-existent rule raises KeyError."""
    with pytest.raises(KeyError, match="No rule found"):
        context.get_rule("NonExistent", "Type", version=99)


def test_get_rule_version_mismatch_raises_keyerror(context):
    """Request non-existent version of existing rule raises KeyError."""
    with pytest.raises(KeyError, match="No rule found"):
        context.get_rule("ACBus", "PLEXOSNode", version=99)


def test_get_rule_with_different_versions(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
):
    """Retrieve different versions of same conversion."""
    from r2x_sienna_to_plexos import Rule, TranslationContext

    rule_v1 = Rule(source_type="Bus", target_type="Node", version=1, field_map={"name": "name"})
    rule_v2 = Rule(
        source_type="Bus",
        target_type="Node",
        version=2,
        field_map={"name": "name", "extra": "extra"},
    )
    ctx = TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=[rule_v1, rule_v2],
    )

    retrieved_v1 = ctx.get_rule("Bus", "Node", version=1)
    retrieved_v2 = ctx.get_rule("Bus", "Node", version=2)

    assert retrieved_v1.version == 1
    assert retrieved_v2.version == 2
    assert len(retrieved_v1.field_map) == 1
    assert len(retrieved_v2.field_map) == 2


def test_list_rules_returns_all_rules(context):
    """List all rules in context."""
    from r2x_sienna_to_plexos import Rule

    rules = context.list_rules()

    assert len(rules) == 3
    assert all(isinstance(r, Rule) for r in rules)


def test_list_rules_includes_all_types(context):
    """list_rules includes rules for all component types."""
    rules = context.list_rules()
    source_types = {r.source_type for r in rules}

    assert "ACBus" in source_types
    assert "ThermalStandard" in source_types
    assert "Bus" in source_types


def test_list_available_conversions_structure(context):
    """list_available_conversions returns correct structure."""
    conversions = context.list_available_conversions()

    assert isinstance(conversions, dict)
    assert all(isinstance(k, str) for k in conversions.keys())
    assert all(isinstance(v, list) for v in conversions.values())
    assert all(isinstance(item, tuple) and len(item) == 2 for items in conversions.values() for item in items)


def test_list_available_conversions_content(context):
    """list_available_conversions returns correct content."""
    conversions = context.list_available_conversions()

    assert "ACBus" in conversions
    assert "ThermalStandard" in conversions
    assert "Bus" in conversions
    assert conversions["ACBus"] == [("PLEXOSNode", 1)]
    assert conversions["ThermalStandard"] == [("PLEXOSGenerator", 1)]


def test_list_available_conversions_is_sorted(context):
    """list_available_conversions returns sorted target types and versions."""
    conversions = context.list_available_conversions()

    for targets in conversions.values():
        assert targets == sorted(targets)


def test_list_available_conversions_with_multiple_versions(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
):
    """list_available_conversions with multiple versions of same type."""
    from r2x_sienna_to_plexos import Rule, TranslationContext

    rule_v1 = Rule(source_type="Bus", target_type="Node", version=1, field_map={"name": "name"})
    rule_v2 = Rule(source_type="Bus", target_type="Node", version=2, field_map={"name": "name"})
    ctx = TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=[rule_v1, rule_v2],
    )

    conversions = ctx.list_available_conversions()

    assert len(conversions["Bus"]) == 2
    assert ("Node", 1) in conversions["Bus"]
    assert ("Node", 2) in conversions["Bus"]


def test_list_available_conversions_with_multiple_targets(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
):
    """list_available_conversions with same source type but different targets."""
    from r2x_sienna_to_plexos import Rule, TranslationContext

    rule_1 = Rule(source_type="Bus", target_type="Node", version=1, field_map={"name": "name"})
    rule_2 = Rule(
        source_type="Bus",
        target_type="PLEXOSNode",
        version=1,
        field_map={"name": "name"},
    )
    ctx = TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=[rule_1, rule_2],
    )

    conversions = ctx.list_available_conversions()

    assert len(conversions["Bus"]) == 2
    assert conversions["Bus"] == [("Node", 1), ("PLEXOSNode", 1)]


def test_get_rules_for_source(context):
    """Get all rules for a specific source type."""
    bus_rules = context.get_rules_for_source("Bus")

    assert len(bus_rules) == 1
    assert all(r.source_type == "Bus" for r in bus_rules)


def test_get_rules_for_source_multiple_versions(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
):
    """Get rules for source with multiple versions."""
    from r2x_sienna_to_plexos import Rule, TranslationContext

    rule_v1 = Rule(source_type="Bus", target_type="Node", version=1, field_map={"name": "name"})
    rule_v2 = Rule(source_type="Bus", target_type="Node", version=2, field_map={"name": "name"})
    ctx = TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=[rule_v1, rule_v2],
    )

    bus_rules = ctx.get_rules_for_source("Bus")

    assert len(bus_rules) == 2
    assert all(r.source_type == "Bus" for r in bus_rules)


def test_get_rules_for_source_not_found():
    """Get rules for non-existent source returns empty list."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig, TranslationContext

    from r2x_core import System

    ctx = TranslationContext(
        source_system=System(name="sienna"),
        target_system=System(name="plexos"),
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    rules = ctx.get_rules_for_source("NonExistent")
    assert rules == []


def test_get_rules_for_conversion(context):
    """Get all versions of a specific conversion."""
    rules = context.get_rules_for_conversion("Bus", "Node")

    assert len(rules) == 1
    assert all(r.source_type == "Bus" and r.target_type == "Node" for r in rules)


def test_get_rules_for_conversion_multiple_versions(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
):
    """Get multiple versions of a conversion."""
    from r2x_sienna_to_plexos import Rule, TranslationContext

    rule_v1 = Rule(source_type="Bus", target_type="Node", version=1, field_map={"name": "name"})
    rule_v2 = Rule(source_type="Bus", target_type="Node", version=2, field_map={"name": "name"})
    rule_v3 = Rule(source_type="Bus", target_type="Node", version=3, field_map={"name": "name"})
    ctx = TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=[rule_v1, rule_v2, rule_v3],
    )

    rules = ctx.get_rules_for_conversion("Bus", "Node")

    assert len(rules) == 3
    assert [r.version for r in rules] == [1, 2, 3]


def test_get_rules_for_conversion_not_found():
    """Get conversion that doesn't exist returns empty list."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig, TranslationContext

    from r2x_core import System

    ctx = TranslationContext(
        source_system=System(name="sienna"),
        target_system=System(name="plexos"),
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    rules = ctx.get_rules_for_conversion("Bus", "Node")
    assert rules == []


def test_rule_retrieved_from_context_is_usable(context):
    """Rule retrieved from context can be used immediately."""
    rule = context.get_rule("ThermalStandard", "PLEXOSGenerator", version=1)

    # Verify rule has all expected attributes
    assert rule.source_type == "ThermalStandard"
    assert rule.target_type == "PLEXOSGenerator"
    assert "Max Capacity" in rule.field_map
    assert callable(rule.getters["Max Capacity"])


def test_creating_context_with_rule_from_fixture(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
    rule_simple,
):
    """Create context with a rule fixture."""
    from r2x_sienna_to_plexos import TranslationContext

    rules = [rule_simple]
    ctx = TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=rules,
    )

    retrieved_rule = ctx.get_rule("ACBus", "PLEXOSNode", version=1)
    assert retrieved_rule is rule_simple


def test_context_with_versioned_rules_fixture(context_with_versioned_rules):
    """Test context with versioned rules demonstrates version selection."""
    # Get active version (should be 2 based on config)
    rule_active = context_with_versioned_rules.get_rule("Bus", "Node")
    assert rule_active.version == 1  # Config has version 1 as active

    # Override and get different version
    rule_v2 = context_with_versioned_rules.get_rule("Bus", "Node", version=2)
    assert rule_v2.version == 2


def test_rules_list_preserves_order(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
):
    """Rules are returned in the order they were provided."""
    from r2x_sienna_to_plexos import Rule, TranslationContext

    rule_a = Rule(source_type="A", target_type="X", version=1, field_map={"f": "f"})
    rule_b = Rule(source_type="B", target_type="Y", version=1, field_map={"f": "f"})
    rule_c = Rule(source_type="C", target_type="Z", version=1, field_map={"f": "f"})

    ctx = TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=[rule_a, rule_b, rule_c],
    )

    listed_rules = ctx.list_rules()
    assert listed_rules == [rule_a, rule_b, rule_c]
