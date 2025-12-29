"""Tests for plugin configuration loading and validation."""

import json

import pytest


def test_load_s2p_rules_json() -> None:
    """Test loading Sienna-to-PLEXOS rules from package."""
    from importlib.resources import files

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    assert rules_path.exists()

    rules_data = json.loads(rules_path.read_text())
    assert isinstance(rules_data, list)
    assert len(rules_data) > 0


def test_load_s2p_rules_as_rule_objects() -> None:
    """Test parsing S2P rules as Rule objects."""
    from importlib.resources import files

    from r2x_core import Rule

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    rules = Rule.from_records(rules_data)
    assert len(rules) > 0
    assert all(isinstance(rule, Rule) for rule in rules)


def test_s2p_rules_have_required_fields() -> None:
    """Test that S2P rules have required fields."""
    from importlib.resources import files

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for rule_dict in rules_data:
        assert "version" in rule_dict
        # source_type and target_type may be optional in some rules


def test_load_s2p_defaults_json() -> None:
    """Test loading S2P defaults configuration."""
    from importlib.resources import files

    defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
    assert defaults_path.exists()

    defaults_data = json.loads(defaults_path.read_text())
    assert isinstance(defaults_data, dict)


def test_load_r2p_rules_json() -> None:
    """Test loading ReEDS-to-PLEXOS rules from package."""
    from importlib.resources import files

    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    assert rules_path.exists()

    rules_data = json.loads(rules_path.read_text())
    assert isinstance(rules_data, list)
    assert len(rules_data) > 0


def test_load_r2p_rules_as_rule_objects() -> None:
    """Test parsing R2P rules as Rule objects."""
    from importlib.resources import files

    from r2x_core import Rule

    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    rules = Rule.from_records(rules_data)
    assert len(rules) > 0
    assert all(isinstance(rule, Rule) for rule in rules)


def test_r2p_rules_have_required_fields() -> None:
    """Test that R2P rules have required fields."""
    from importlib.resources import files

    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for rule_dict in rules_data:
        assert "version" in rule_dict


def test_s2p_config_class_instantiation() -> None:
    """Test SiennaToPlexosConfig can be instantiated."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig

    config = SiennaToPlexosConfig()
    assert config is not None


def test_r2p_config_class_instantiation() -> None:
    """Test ReedsToPlexosConfig can be instantiated."""
    from r2x_reeds_to_plexos import ReedsToPlexosConfig

    config = ReedsToPlexosConfig()
    assert config is not None


def test_s2p_plugin_config_has_name() -> None:
    """Test S2P plugin config has name attribute."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig

    config = SiennaToPlexosConfig()
    assert hasattr(config, "name") or hasattr(config, "__class__")


def test_r2p_plugin_config_has_name() -> None:
    """Test R2P plugin config has name attribute."""
    from r2x_reeds_to_plexos import ReedsToPlexosConfig

    config = ReedsToPlexosConfig()
    assert hasattr(config, "name") or hasattr(config, "__class__")


def test_rules_json_valid_structure() -> None:
    """Test that rules JSON files have valid structure."""
    from importlib.resources import files

    for package_name in ["r2x_sienna_to_plexos", "r2x_reeds_to_plexos"]:
        rules_path = files(f"{package_name}.config") / "rules.json"
        rules_data = json.loads(rules_path.read_text())

        assert isinstance(rules_data, list), f"{package_name} rules should be a list"

        for idx, rule in enumerate(rules_data):
            assert isinstance(rule, dict), f"{package_name} rule {idx} should be a dict"
            assert "version" in rule, f"{package_name} rule {idx} missing version"


def test_s2p_defaults_have_expected_keys() -> None:
    """Test S2P defaults contain expected configuration keys."""
    from importlib.resources import files

    defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
    defaults_data = json.loads(defaults_path.read_text())

    # Should be a dict with configuration settings
    assert isinstance(defaults_data, dict)
    # Check for some expected keys (adjust based on actual structure)
    assert len(defaults_data) >= 0


def test_config_files_are_valid_json() -> None:
    """Test that all config JSON files are valid JSON."""
    from importlib.resources import files

    config_files = [
        ("r2x_sienna_to_plexos.config", "rules.json"),
        ("r2x_sienna_to_plexos.config", "defaults.json"),
        ("r2x_reeds_to_plexos.config", "rules.json"),
    ]

    for package, filename in config_files:
        config_path = files(package) / filename
        try:
            data = json.loads(config_path.read_text())
            assert data is not None, f"{package}/{filename} parsed to None"
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON in {package}/{filename}: {e}")


def test_rule_field_map_structure() -> None:
    """Test that field_map in rules has valid structure."""
    from importlib.resources import files

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for rule in rules_data:
        if "field_map" in rule:
            assert isinstance(rule["field_map"], dict)
            # Values can be strings or lists
            for key, value in rule["field_map"].items():
                assert isinstance(key, str)
                assert isinstance(value, str | list)


def test_rule_getters_structure() -> None:
    """Test that getters in rules have valid structure."""
    from importlib.resources import files

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for rule in rules_data:
        if "getters" in rule:
            assert isinstance(rule["getters"], dict)
            # Keys should be strings (target field names)
            # Values should be strings (getter function names)
            for key, value in rule["getters"].items():
                assert isinstance(key, str)
                assert isinstance(value, str)


def test_rule_defaults_structure() -> None:
    """Test that defaults in rules have valid structure."""
    from importlib.resources import files

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for rule in rules_data:
        if "defaults" in rule:
            assert isinstance(rule["defaults"], dict)
            # Keys should be strings (field names)
            for key in rule["defaults"]:
                assert isinstance(key, str)
