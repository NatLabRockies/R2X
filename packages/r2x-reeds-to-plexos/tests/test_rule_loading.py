"""Smoke tests for packaged ReEDS-to-PLEXOS rules."""

from __future__ import annotations

import json
import sys
from importlib.resources import files
from pathlib import Path


def test_rules_json_exists_and_loads() -> None:
    """Ensure the packaged rules file is present and valid JSON."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    assert rules_path.is_file(), "rules.json missing"

    rules_data = json.loads(rules_path.read_text())
    assert isinstance(rules_data, list)
    assert len(rules_data) > 0, "Rules list is empty"


def test_has_region_node_rule() -> None:
    """Verify ReEDSRegion maps to PLEXOSNode."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSRegion" and rule.get("target_type") == "PLEXOSNode"
        for rule in rules_data
    ), "Missing ReEDSRegion -> PLEXOSNode rule"


def test_has_region_to_zone_rule() -> None:
    """Verify ReEDSRegion maps to PLEXOSZone."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSRegion" and rule.get("target_type") == "PLEXOSZone"
        for rule in rules_data
    ), "Missing ReEDSRegion -> PLEXOSZone rule"


def test_has_reserve_rule() -> None:
    """Verify ReEDSReserve maps to PLEXOSReserve."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSReserve" and rule.get("target_type") == "PLEXOSReserve"
        for rule in rules_data
    ), "Missing ReEDSReserve -> PLEXOSReserve rule"


def test_has_generator_rules() -> None:
    """Verify ReEDS generators map to PLEXOS generator types."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    # Thermal generator
    assert any(
        rule.get("source_type") == "ReEDSThermalGenerator" and rule.get("target_type") == "PLEXOSGenerator"
        for rule in rules_data
    ), "Missing ReEDSThermalGenerator -> PLEXOSGenerator rule"

    # Variable generator
    assert any(
        rule.get("source_type") == "ReEDSVariableGenerator" and rule.get("target_type") == "PLEXOSGenerator"
        for rule in rules_data
    ), "Missing ReEDSVariableGenerator -> PLEXOSGenerator rule"

    # Hydro generator
    assert any(
        rule.get("source_type") == "ReEDSHydroGenerator" and rule.get("target_type") == "PLEXOSGenerator"
        for rule in rules_data
    ), "Missing ReEDSHydroGenerator -> PLEXOSGenerator rule"


def test_has_storage_rule() -> None:
    """Verify ReEDSStorage maps to PLEXOSBattery or PLEXOSGenerator."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSStorage"
        and rule.get("target_type") in ("PLEXOSBattery", "PLEXOSGenerator")
        for rule in rules_data
    ), "Missing ReEDSStorage -> PLEXOSBattery or PLEXOSGenerator rule"


def test_has_interface_rule() -> None:
    """Verify ReEDSInterface maps to PLEXOSInterface."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSInterface" and rule.get("target_type") == "PLEXOSInterface"
        for rule in rules_data
    ), "Missing ReEDSInterface -> PLEXOSInterface rule"


def test_has_transmission_line_rule() -> None:
    """Verify ReEDSTransmissionLine maps to PLEXOSLine."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSTransmissionLine" and rule.get("target_type") == "PLEXOSLine"
        for rule in rules_data
    ), "Missing ReEDSTransmissionLine -> PLEXOSLine rule"


def test_rules_have_required_fields() -> None:
    """Verify all rules have essential structure."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for i, rule in enumerate(rules_data):
        assert "source_type" in rule, f"Rule {i} missing source_type"
        assert "target_type" in rule, f"Rule {i} missing target_type"
        assert "version" in rule, f"Rule {i} missing version"
        assert "field_map" in rule or "getters" in rule, f"Rule {i} missing field_map and getters"


def test_dependency_rules() -> None:
    """Verify rules with dependencies reference valid rule names."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    rule_names = {rule.get("name") for rule in rules_data if "name" in rule}

    for rule in rules_data:
        if "depends_on" in rule:
            for dependency in rule["depends_on"]:
                assert (
                    dependency in rule_names
                ), f"Rule {rule.get('name', 'unknown')} depends on unknown rule: {dependency}"


def test_node_rule_is_first() -> None:
    """Verify the first PLEXOSNode rule comes before dependent rules."""
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    node_rule_index = None
    for i, rule in enumerate(rules_data):
        if rule.get("target_type") == "PLEXOSNode":
            node_rule_index = i
            break

    assert node_rule_index is not None, "PLEXOSNode rule not found"

    for i, rule in enumerate(rules_data):
        if "depends_on" in rule and "region_node" in rule["depends_on"]:
            assert (
                i > node_rule_index
            ), f"Rule {rule.get('name', 'unknown')} depends on region_node but comes before it"


def test_dependency_rules_with_synthetic_depends_on(monkeypatch, tmp_path: Path) -> None:
    rules = [
        {
            "name": "region_node",
            "source_type": "A",
            "target_type": "PLEXOSNode",
            "version": "1",
            "field_map": {},
        },
        {
            "name": "dependent",
            "source_type": "B",
            "target_type": "C",
            "version": "1",
            "field_map": {},
            "depends_on": ["region_node"],
        },
    ]
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "rules.json").write_text(json.dumps(rules))

    monkeypatch.setattr(sys.modules[__name__], "files", lambda _pkg: cfg_dir)
    test_dependency_rules()


def test_node_rule_order_with_synthetic_dependency(monkeypatch, tmp_path: Path) -> None:
    rules = [
        {
            "name": "region_node",
            "source_type": "A",
            "target_type": "PLEXOSNode",
            "version": "1",
            "field_map": {},
        },
        {
            "name": "needs_node",
            "source_type": "B",
            "target_type": "D",
            "version": "1",
            "field_map": {},
            "depends_on": ["region_node"],
        },
    ]
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "rules.json").write_text(json.dumps(rules))

    monkeypatch.setattr(sys.modules[__name__], "files", lambda _pkg: cfg_dir)
    test_node_rule_is_first()
