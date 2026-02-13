"""Smoke tests for packaged Sienna-to-PLEXOS rules."""

from __future__ import annotations

import json
from importlib.resources import files


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


def test_has_area_to_zone_rule() -> None:
    """Verify Area maps to PLEXOSZone."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    assert any(
        rule.get("source_type") == "LoadZone" and rule.get("target_type") == "PLEXOSZone"
        for rule in rules_data
    ), "Missing LoadZone -> PLEXOSZone rule"


def test_has_storage_to_battery_rule() -> None:
    """Verify EnergyReservoirStorage maps to PLEXOSBattery."""
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    assert any(
        rule.get("source_type") == "EnergyReservoirStorage" and rule.get("target_type") == "PLEXOSBattery"
        for rule in rules_data
    ), "Missing EnergyReservoirStorage -> PLEXOSBattery rule"


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
