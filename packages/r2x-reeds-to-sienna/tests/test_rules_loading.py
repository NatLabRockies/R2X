"""Smoke tests for packaged ReEDS-to-Sienna rules."""

from __future__ import annotations

import json
from importlib.resources import files


def test_rules_json_exists_and_loads() -> None:
    """Ensure the packaged rules file is present and valid JSON."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    assert rules_path.is_file(), "translation_rules.json missing"

    rules_data = json.loads(rules_path.read_text())
    assert isinstance(rules_data, list)
    assert len(rules_data) > 0, "Rules list is empty"


def test_has_region_bus_rule() -> None:
    """Verify ReEDSRegion maps to ACBus."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSRegion" and rule.get("target_type") == "ACBus" for rule in rules_data
    ), "Missing ReEDSRegion -> ACBus rule"


def test_has_region_to_area_rule() -> None:
    """Verify ReEDSRegion maps to Sienna Area."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSRegion" and rule.get("target_type") == "Area" for rule in rules_data
    ), "Missing ReEDSRegion -> Area rule"


def test_has_variable_reserve_rule() -> None:
    """Verify ReEDSReserve maps to VariableReserve."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSReserve" and rule.get("target_type") == "VariableReserve"
        for rule in rules_data
    ), "Missing ReEDSReserve -> VariableReserve rule"


def test_has_generator_rules() -> None:
    """Verify ReEDS generators map to Sienna generator types."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    # Thermal generator
    assert any(
        rule.get("source_type") == "ReEDSThermalGenerator" and rule.get("target_type") == "ThermalStandard"
        for rule in rules_data
    ), "Missing ReEDSThermalGenerator -> ThermalStandard rule"

    # Renewable dispatch (upv, wind-ons)
    assert any(
        rule.get("source_type") == "ReEDSVariableGenerator"
        and rule.get("target_type") == "RenewableDispatch"
        and "filter" in rule
        for rule in rules_data
    ), "Missing ReEDSVariableGenerator -> RenewableDispatch rule"

    # Renewable non-dispatch (distpv)
    assert any(
        rule.get("source_type") == "ReEDSVariableGenerator"
        and rule.get("target_type") == "RenewableNonDispatch"
        and rule.get("filter", {}).get("values") == ["distpv"]
        for rule in rules_data
    ), "Missing ReEDSVariableGenerator -> RenewableNonDispatch (distpv) rule"

    # Hydro generator
    assert any(
        rule.get("source_type") == "ReEDSHydroGenerator" and rule.get("target_type") == "HydroDispatch"
        for rule in rules_data
    ), "Missing ReEDSHydroGenerator -> HydroDispatch rule"


def test_has_storage_rule() -> None:
    """Verify ReEDSStorage maps to EnergyReservoirStorage."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSStorage" and rule.get("target_type") == "EnergyReservoirStorage"
        for rule in rules_data
    ), "Missing ReEDSStorage -> EnergyReservoirStorage rule"


def test_has_interface_rule() -> None:
    """Verify ReEDSInterface maps to AreaInterchange."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSInterface" and rule.get("target_type") == "AreaInterchange"
        for rule in rules_data
    ), "Missing ReEDSInterface -> AreaInterchange rule"


def test_has_demand_rule() -> None:
    """Verify ReEDSDemand maps to PowerLoad."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSDemand" and rule.get("target_type") == "PowerLoad"
        for rule in rules_data
    ), "Missing ReEDSDemand -> PowerLoad rule"


def test_has_transmission_line_rule() -> None:
    """Verify ReEDSTransmissionLine maps to Line."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSTransmissionLine" and rule.get("target_type") == "Line"
        for rule in rules_data
    ), "Missing ReEDSTransmissionLine -> Line rule"


def test_rules_have_required_fields() -> None:
    """Verify all rules have essential structure."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    for i, rule in enumerate(rules_data):
        assert "source_type" in rule, f"Rule {i} missing source_type"
        assert "target_type" in rule, f"Rule {i} missing target_type"
        assert "version" in rule, f"Rule {i} missing version"
        # Either field_map or getters should be present
        assert "field_map" in rule or "getters" in rule, f"Rule {i} missing field_map and getters"


def test_dependency_rules() -> None:
    """Verify rules with dependencies reference valid rule names."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    rule_names = {rule.get("name") for rule in rules_data if "name" in rule}

    for rule in rules_data:
        if "depends_on" in rule:
            for dependency in rule["depends_on"]:
                assert (
                    dependency in rule_names
                ), f"Rule {rule.get('name', 'unknown')} depends on unknown rule: {dependency}"


def test_bus_rule_is_first() -> None:
    """Verify region_bus rule comes before dependent rules."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    bus_rule_index = None
    for i, rule in enumerate(rules_data):
        if rule.get("name") == "region_bus":
            bus_rule_index = i
            break

    assert bus_rule_index is not None, "region_bus rule not found"

    # Check that rules with depends_on: ["region_bus"] come after
    for i, rule in enumerate(rules_data):
        if "depends_on" in rule and "region_bus" in rule["depends_on"]:
            assert (
                i > bus_rule_index
            ), f"Rule {rule.get('name', 'unknown')} depends on region_bus but comes before it"
