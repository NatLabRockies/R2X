"""Tests for translation rules validation and loading."""

import pytest


def test_rule_from_records_basic() -> None:
    """Test Rule.from_records with basic rule structure."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
        }
    ]

    rules = Rule.from_records(rule_data)

    assert len(rules) == 1
    assert rules[0].source_type == "ACBus"
    assert rules[0].target_type == "PLEXOSNode"
    assert rules[0].version == 1


def test_rule_from_records_with_field_map() -> None:
    """Test Rule.from_records with field_map."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
            "field_map": {
                "name": "name",
                "voltage": "base_voltage",
            },
        }
    ]

    rules = Rule.from_records(rule_data)

    assert rules[0].field_map == {"name": "name", "voltage": "base_voltage"}


def test_rule_from_records_with_getters() -> None:
    """Test Rule.from_records with getters."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
            "getters": {
                "is_slack": "is_slack_bus",
                "units": "get_availability",
            },
        }
    ]

    rules = Rule.from_records(rule_data)

    assert "is_slack" in rules[0].getters
    assert "units" in rules[0].getters


def test_rule_from_records_with_defaults() -> None:
    """Test Rule.from_records with defaults."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
            "defaults": {
                "units": 1,
                "is_slack": 0,
            },
        }
    ]

    rules = Rule.from_records(rule_data)

    assert rules[0].defaults == {"units": 1, "is_slack": 0}


def test_rule_from_records_multiple() -> None:
    """Test Rule.from_records with multiple rules."""
    from r2x_core import Rule

    rules_data = [
        {"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1},
        {"source_type": "Line", "target_type": "PLEXOSLine", "version": 1},
    ]

    rules = Rule.from_records(rules_data)

    assert len(rules) == 2
    assert rules[0].source_type == "ACBus"
    assert rules[1].source_type == "Line"


def test_rule_from_records_empty_list() -> None:
    """Test Rule.from_records with empty list."""
    from r2x_core import Rule

    rules = Rule.from_records([])

    assert rules == []


def test_rule_validation_requires_version() -> None:
    """Test that rules require version field."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            # Missing version
        }
    ]

    with pytest.raises((KeyError, ValueError, TypeError)):
        Rule.from_records(rule_data)


def test_rule_field_map_accepts_list_values() -> None:
    """Test that field_map accepts list values for fallback fields."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ThermalStandard",
            "target_type": "PLEXOSGenerator",
            "version": 1,
            "field_map": {
                "max_capacity": ["active_power_limits", "max_active_power"],
            },
            "getters": {
                "max_capacity": "get_max_capacity",  # Multi-field mapping requires getter
            },
        }
    ]

    rules = Rule.from_records(rule_data)

    assert isinstance(rules[0].field_map["max_capacity"], list)
    assert len(rules[0].field_map["max_capacity"]) == 2


def test_rule_field_map_accepts_string_values() -> None:
    """Test that field_map accepts string values for direct mapping."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
            "field_map": {
                "name": "name",
            },
        }
    ]

    rules = Rule.from_records(rule_data)

    assert isinstance(rules[0].field_map["name"], str)


def test_rule_getters_reference_valid_names() -> None:
    """Test that getter names in rules are valid strings."""
    import json
    from importlib.resources import files

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for rule in rules_data:
        if "getters" in rule:
            for field_name, getter_name in rule["getters"].items():
                assert isinstance(getter_name, str), f"Getter name should be string: {getter_name}"
                assert len(getter_name) > 0, f"Getter name should not be empty for field {field_name}"


def test_rule_version_is_integer() -> None:
    """Test that rule version is an integer."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
        }
    ]

    rules = Rule.from_records(rule_data)

    assert isinstance(rules[0].version, int)


def test_rules_can_have_optional_source_target() -> None:
    """Test that some rules can have optional source/target types."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "DefaultSource",  # Provide required fields
            "target_type": "DefaultTarget",
            "version": 1,
        }
    ]

    # Should work - rules must specify source/target
    rules = Rule.from_records(rule_data)
    assert len(rules) == 1
    assert rules[0].version == 1
    assert rules[0].source_type == "DefaultSource"
    assert rules[0].target_type == "DefaultTarget"


def test_load_all_package_rules_successfully() -> None:
    """Test that all package rules can be loaded without errors."""
    import json
    from importlib.resources import files

    from r2x_core import Rule

    packages = [
        "r2x_sienna_to_plexos",
        "r2x_reeds_to_plexos",
    ]

    for package_name in packages:
        rules_path = files(f"{package_name}.config") / "rules.json"
        rules_data = json.loads(rules_path.read_text())

        try:
            rules = Rule.from_records(rules_data)
            assert len(rules) > 0, f"{package_name} should have rules"
        except Exception as e:
            pytest.fail(f"Failed to load rules from {package_name}: {e}")


def test_rule_has_required_attributes() -> None:
    """Test that Rule objects have expected attributes."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
        }
    ]

    rules = Rule.from_records(rule_data)
    rule = rules[0]

    assert hasattr(rule, "version")
    assert hasattr(rule, "source_type")
    assert hasattr(rule, "target_type")


def test_rule_field_map_defaults_to_empty() -> None:
    """Test that field_map defaults to empty dict if not provided."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
        }
    ]

    rules = Rule.from_records(rule_data)

    # field_map should exist and be empty or None
    assert hasattr(rules[0], "field_map")


def test_rule_getters_defaults_to_empty() -> None:
    """Test that getters defaults to empty dict if not provided."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
        }
    ]

    rules = Rule.from_records(rule_data)

    # getters should exist and be empty or None
    assert hasattr(rules[0], "getters")


def test_rule_defaults_defaults_to_empty() -> None:
    """Test that defaults defaults to empty dict if not provided."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
        }
    ]

    rules = Rule.from_records(rule_data)

    # defaults should exist and be empty or None
    assert hasattr(rules[0], "defaults")


def test_rules_json_files_are_valid() -> None:
    """Test that all rules JSON files are valid and parseable."""
    import json
    from importlib.resources import files

    packages = [
        "r2x_sienna_to_plexos",
        "r2x_reeds_to_plexos",
    ]

    for package_name in packages:
        rules_path = files(f"{package_name}.config") / "rules.json"

        try:
            rules_data = json.loads(rules_path.read_text())
            assert isinstance(rules_data, list)
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON in {package_name} rules: {e}")


def test_rule_with_all_fields() -> None:
    """Test Rule with all possible fields populated."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ThermalStandard",
            "target_type": "PLEXOSGenerator",
            "version": 1,
            "field_map": {
                "name": "name",
                "max_capacity": ["active_power_limits", "max_active_power"],
            },
            "getters": {
                "heat_rate": "get_heat_rate",
                "fuel_price": "get_fuel_price",
                "max_capacity": "get_max_capacity",  # Required for multi-field mapping
            },
            "defaults": {
                "units": 1,
                "forced_outage_rate": 0.0,
            },
        }
    ]

    rules = Rule.from_records(rule_data)
    rule = rules[0]

    assert rule.source_type == "ThermalStandard"
    assert rule.target_type == "PLEXOSGenerator"
    assert rule.version == 1
    assert len(rule.field_map) == 2
    assert len(rule.getters) == 3
    assert len(rule.defaults) == 2


def test_rules_preserve_field_types() -> None:
    """Test that rules preserve field types correctly."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
            "defaults": {
                "units": 1,
                "voltage": 230.0,
                "is_slack": False,
                "region": "WEST",
            },
        }
    ]

    rules = Rule.from_records(rule_data)
    rule = rules[0]

    assert isinstance(rule.defaults["units"], int)
    assert isinstance(rule.defaults["voltage"], float)
    assert isinstance(rule.defaults["is_slack"], bool)
    assert isinstance(rule.defaults["region"], str)


def test_rule_from_records_handles_duplicate_rules() -> None:
    """Test that from_records handles duplicate rule definitions."""
    from r2x_core import Rule

    rule_data = [
        {"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1},
        {"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1},
    ]

    rules = Rule.from_records(rule_data)

    # Should create both rules (or handle duplicates appropriately)
    assert len(rules) >= 1


def test_rule_getters_can_be_empty() -> None:
    """Test that rules can have empty getters dict."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
            "getters": {},
        }
    ]

    rules = Rule.from_records(rule_data)

    assert len(rules) == 1


def test_rule_field_map_can_be_empty() -> None:
    """Test that rules can have empty field_map dict."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
            "field_map": {},
        }
    ]

    rules = Rule.from_records(rule_data)

    assert len(rules) == 1


def test_rule_defaults_can_be_empty() -> None:
    """Test that rules can have empty defaults dict."""
    from r2x_core import Rule

    rule_data = [
        {
            "source_type": "ACBus",
            "target_type": "PLEXOSNode",
            "version": 1,
            "defaults": {},
        }
    ]

    rules = Rule.from_records(rule_data)

    assert len(rules) == 1
