import pytest


def test_simple_rule_creation(rule_simple):
    """Create and verify simple rule with single-field mapping."""
    assert rule_simple.source_type == "ACBus"
    assert rule_simple.target_type == "PLEXOSNode"
    assert rule_simple.version == 1
    assert rule_simple.field_map == {"name": "name", "uuid": "uuid"}
    assert rule_simple.getters == {}
    assert rule_simple.defaults == {}


def test_multifield_rule_creation(rule_multifield):
    """Create and verify multi-field rule with getter function."""
    rule = rule_multifield

    assert rule.source_type == "ThermalStandard"
    assert rule.target_type == "PLEXOSGenerator"
    assert rule.version == 1
    assert "Max Capacity" in rule.field_map
    assert isinstance(rule.field_map["Max Capacity"], list)
    assert "Max Capacity" in rule.getters
    assert callable(rule.getters["Max Capacity"])


def test_rule_with_defaults_creation(rule_with_defaults):
    """Create and verify rule with default values."""
    rule = rule_with_defaults

    assert rule.source_type == "Bus"
    assert rule.target_type == "Node"
    assert "category" in rule.defaults
    assert rule.defaults["category"] == "other"


def test_rule_with_all_features(rule_with_all_features):
    """Create and verify rule using all Rule features."""
    rule = rule_with_all_features

    assert len(rule.field_map) > 1
    assert len(rule.getters) > 0
    assert len(rule.defaults) > 0

    assert callable(rule.getters["total_rating"])
    assert rule.defaults["category"] == "standard"


def test_multifield_rule_requires_getter():
    """Multi-field mapping without getter raises ValueError."""
    from r2x_sienna_to_plexos import Rule

    with pytest.raises(ValueError, match="Multi-field mapping .* requires a getter"):
        Rule(
            source_type="Gen",
            target_type="PGen",
            version=1,
            field_map={
                "rating": ["power_a", "power_b"],  # Multi-field without getter
            },
            getters={},  # Missing getter for rating
        )


def test_multifield_rule_validation_passes_with_getter(rule_multifield):
    """Multi-field mapping with getter passes validation."""
    assert "Max Capacity" in rule_multifield.field_map
    assert "Max Capacity" in rule_multifield.getters


def test_validation_with_multiple_multifield_mappings():
    """Validation checks all multi-field mappings."""
    from r2x_sienna_to_plexos import Rule

    with pytest.raises(ValueError, match="Multi-field mapping .* requires a getter"):
        Rule(
            source_type="Multi",
            target_type="PMulti",
            version=1,
            field_map={
                "field1": ["src_a", "src_b"],
                "field2": ["src_c", "src_d"],
            },
            getters={
                "field1": lambda c: 0,  # Only field1 has getter
            },
        )


def test_rule_is_frozen(rule_simple):
    """Verify rule is frozen (immutable)."""
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        rule_simple.version = 2
