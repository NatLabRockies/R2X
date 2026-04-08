"""Smoke tests for packaged Sienna-to-PLEXOS rules."""

from __future__ import annotations

import json
from importlib.resources import files

import pytest


def test_rules_json_exists_and_loads() -> None:
    """Ensure the packaged rules file is present and valid JSON."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    assert rules_path.is_file(), "rules.json missing"

    rules_data = json.loads(rules_path.read_text())
    assert isinstance(rules_data, list)
    assert len(rules_data) > 0, "Rules list is empty"


def test_has_acbus_to_node_rule() -> None:
    """Verify ACBus maps to PLEXOSNode."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    assert any(
        rule.get("source_type") == "ACBus" and rule.get("target_type") == "PLEXOSNode" for rule in rules_data
    ), "Missing ACBus -> PLEXOSNode rule"


def test_has_line_to_plexosline_rule() -> None:
    """Verify Line maps to PLEXOSLine."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    assert any(
        rule.get("source_type") == "Line" and rule.get("target_type") == "PLEXOSLine" for rule in rules_data
    ), "Missing Line -> PLEXOSLine rule"


def test_has_thermal_to_generator_rule() -> None:
    """Verify ThermalStandard maps to PLEXOSGenerator."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    assert any(
        rule.get("source_type") == "ThermalStandard" and rule.get("target_type") == "PLEXOSGenerator"
        for rule in rules_data
    ), "Missing ThermalStandard -> PLEXOSGenerator rule"


def test_has_hydro_to_generator_rule() -> None:
    """Verify HydroReservoir maps to PLEXOSGenerator or PLEXOSStorage."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    assert any(
        rule.get("source_type") == "HydroReservoir"
        and (rule.get("target_type") == "PLEXOSGenerator" or rule.get("target_type") == "PLEXOSStorage")
        for rule in rules_data
    ), "Missing HydroReservoir -> PLEXOSGenerator/PLEXOSStorage rule"


def test_has_storage_to_battery_rule() -> None:
    """Verify EnergyReservoirStorage maps to PLEXOSBattery."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    assert any(
        rule.get("source_type") == "EnergyReservoirStorage" and rule.get("target_type") == "PLEXOSBattery"
        for rule in rules_data
    ), "Missing EnergyReservoirStorage -> PLEXOSBattery rule"


def test_synchronous_condenser_rule_defaults_to_units_zero() -> None:
    """Verify SynchronousCondenser generators are exported deactivated for PLEXOS."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    syn_cond_rule = next(
        (
            rule
            for rule in rules_data
            if rule.get("source_type") == "SynchronousCondenser"
            and rule.get("target_type") == "PLEXOSGenerator"
        ),
        None,
    )

    assert syn_cond_rule is not None, "Missing SynchronousCondenser -> PLEXOSGenerator rule"
    assert syn_cond_rule.get("defaults", {}).get("units") == 0


def test_rules_have_required_fields() -> None:
    """Verify all rules have essential structure."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for i, rule in enumerate(rules_data):
        assert "source_type" in rule, f"Rule {i} missing source_type"
        assert "target_type" in rule, f"Rule {i} missing target_type"
        assert "version" in rule, f"Rule {i} missing version"
        assert "field_map" in rule or "getters" in rule, f"Rule {i} missing field_map and getters"


def test_dependency_rules() -> None:
    """Verify rules with dependencies reference valid rule names."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    rule_names = {rule.get("name") for rule in rules_data if "name" in rule}

    for rule in rules_data:
        if "depends_on" in rule:
            for dependency in rule["depends_on"]:
                assert (
                    dependency in rule_names
                ), f"Rule {rule.get('name', 'unknown')} depends on unknown rule: {dependency}"


def test_node_rule_is_first() -> None:
    """Verify ACBus->PLEXOSNode rule comes before dependent rules."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    node_rule_index = None
    for i, rule in enumerate(rules_data):
        if rule.get("source_type") == "ACBus" and rule.get("target_type") == "PLEXOSNode":
            node_rule_index = i
            break

    assert node_rule_index is not None, "ACBus->PLEXOSNode rule not found"

    # Check that rules with depends_on: ["acbus_to_node"] come after
    for i, rule in enumerate(rules_data):
        if "depends_on" in rule and "acbus_to_node" in rule["depends_on"]:
            assert (
                i > node_rule_index
            ), f"Rule {rule.get('name', 'unknown')} depends on acbus_to_node but comes before it"


def test_rule_from_records_basic() -> None:
    from r2x_core import Rule

    rules = Rule.from_records([{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1}])
    assert len(rules) == 1
    assert rules[0].source_type == "ACBus"
    assert rules[0].target_type == "PLEXOSNode"
    assert rules[0].version == 1


def test_rule_from_records_with_field_map() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {
                "source_type": "ACBus",
                "target_type": "PLEXOSNode",
                "version": 1,
                "field_map": {"name": "name", "voltage": "base_voltage"},
            }
        ]
    )
    assert rules[0].field_map == {"name": "name", "voltage": "base_voltage"}


def test_rule_from_records_with_getters() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {
                "source_type": "ACBus",
                "target_type": "PLEXOSNode",
                "version": 1,
                "getters": {"is_slack": "is_slack_bus", "units": "get_availability"},
            }
        ]
    )
    assert "is_slack" in rules[0].getters
    assert "units" in rules[0].getters


def test_rule_from_records_with_defaults() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {
                "source_type": "ACBus",
                "target_type": "PLEXOSNode",
                "version": 1,
                "defaults": {"units": 1, "is_slack": 0},
            }
        ]
    )
    assert rules[0].defaults == {"units": 1, "is_slack": 0}


def test_rule_from_records_multiple() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1},
            {"source_type": "Line", "target_type": "PLEXOSLine", "version": 1},
        ]
    )
    assert len(rules) == 2
    assert rules[0].source_type == "ACBus"
    assert rules[1].source_type == "Line"


def test_rule_from_records_empty_list() -> None:
    from r2x_core import Rule

    assert Rule.from_records([]) == []


def test_rule_validation_requires_version() -> None:
    from r2x_core import Rule

    with pytest.raises((KeyError, ValueError, TypeError)):
        Rule.from_records([{"source_type": "ACBus", "target_type": "PLEXOSNode"}])


def test_rule_field_map_accepts_list_values() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {
                "source_type": "ThermalStandard",
                "target_type": "PLEXOSGenerator",
                "version": 1,
                "field_map": {"max_capacity": ["active_power_limits", "max_active_power"]},
                "getters": {"max_capacity": "get_max_capacity"},
            }
        ]
    )
    assert isinstance(rules[0].field_map["max_capacity"], list)
    assert len(rules[0].field_map["max_capacity"]) == 2


def test_rule_field_map_accepts_string_values() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1, "field_map": {"name": "name"}}]
    )
    assert isinstance(rules[0].field_map["name"], str)


def test_rule_version_is_integer() -> None:
    from r2x_core import Rule

    rules = Rule.from_records([{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1}])
    assert isinstance(rules[0].version, int)


def test_rules_can_have_optional_source_target() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [{"source_type": "DefaultSource", "target_type": "DefaultTarget", "version": 1}]
    )
    assert len(rules) == 1
    assert rules[0].source_type == "DefaultSource"
    assert rules[0].target_type == "DefaultTarget"


def test_rule_has_required_attributes() -> None:
    from r2x_core import Rule

    rules = Rule.from_records([{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1}])
    rule = rules[0]
    assert hasattr(rule, "version")
    assert hasattr(rule, "source_type")
    assert hasattr(rule, "target_type")


def test_rule_field_map_defaults_to_empty() -> None:
    from r2x_core import Rule

    rules = Rule.from_records([{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1}])
    assert hasattr(rules[0], "field_map")


def test_rule_getters_defaults_to_empty() -> None:
    from r2x_core import Rule

    rules = Rule.from_records([{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1}])
    assert hasattr(rules[0], "getters")


def test_rule_defaults_defaults_to_empty() -> None:
    from r2x_core import Rule

    rules = Rule.from_records([{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1}])
    assert hasattr(rules[0], "defaults")


def test_rule_with_all_fields() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
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
                    "max_capacity": "get_max_capacity",
                },
                "defaults": {"units": 1, "forced_outage_rate": 0.0},
            }
        ]
    )
    rule = rules[0]
    assert rule.source_type == "ThermalStandard"
    assert rule.target_type == "PLEXOSGenerator"
    assert rule.version == 1
    assert len(rule.field_map) == 2
    assert len(rule.getters) == 3
    assert len(rule.defaults) == 2


def test_rules_preserve_field_types() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {
                "source_type": "ACBus",
                "target_type": "PLEXOSNode",
                "version": 1,
                "defaults": {"units": 1, "voltage": 230.0, "is_slack": False, "region": "WEST"},
            }
        ]
    )
    rule = rules[0]
    assert isinstance(rule.defaults["units"], int)
    assert isinstance(rule.defaults["voltage"], float)
    assert isinstance(rule.defaults["is_slack"], bool)
    assert isinstance(rule.defaults["region"], str)


def test_rule_from_records_handles_duplicate_rules() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1},
            {"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1},
        ]
    )
    assert len(rules) >= 1


def test_rule_getters_can_be_empty() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1, "getters": {}}]
    )
    assert len(rules) == 1


def test_rule_field_map_can_be_empty() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1, "field_map": {}}]
    )
    assert len(rules) == 1


def test_rule_defaults_can_be_empty() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [{"source_type": "ACBus", "target_type": "PLEXOSNode", "version": 1, "defaults": {}}]
    )
    assert len(rules) == 1


def test_rule_with_storage_properties() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {
                "source_type": "HydroReservoir",
                "target_type": "PLEXOSStorage",
                "version": 1,
                "getters": {
                    "initial_level": "get_storage_initial_level",
                    "max_level": "get_storage_max_level",
                },
            }
        ]
    )
    assert "initial_level" in rules[0].getters
    assert "max_level" in rules[0].getters


def test_rule_with_head_tail_storage_memberships() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {
                "source_type": "PLEXOSGenerator",
                "target_type": "PLEXOSMembership",
                "version": 1,
                "getters": {
                    "parent_object": "membership_head_storage_generator",
                    "child_object": "membership_head_storage",
                    "collection": "membership_collection_head_storage",
                },
            },
            {
                "source_type": "PLEXOSGenerator",
                "target_type": "PLEXOSMembership",
                "version": 2,
                "getters": {
                    "parent_object": "membership_tail_storage_generator",
                    "child_object": "membership_tail_storage",
                    "collection": "membership_collection_tail_storage",
                },
            },
        ]
    )
    assert "parent_object" in rules[0].getters
    assert "parent_object" in rules[1].getters


def test_rule_with_storage_properties_and_field_map() -> None:
    from r2x_core import Rule

    rules = Rule.from_records(
        [
            {
                "source_type": "HydroReservoir",
                "target_type": "PLEXOSStorage",
                "version": 1,
                "field_map": {"name": "name", "uuid": "uuid"},
                "getters": {
                    "initial_level": "get_storage_initial_level",
                    "max_level": "get_storage_max_level",
                },
            }
        ]
    )
    assert "initial_level" in rules[0].getters
    assert "name" in rules[0].field_map
