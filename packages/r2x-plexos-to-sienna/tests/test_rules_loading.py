"""Smoke tests for packaged PLEXOS-to-Sienna rules."""

from __future__ import annotations

import json
from importlib.resources import files


def test_rules_json_exists_and_loads() -> None:
    """Ensure the packaged rules file is present and valid JSON."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    assert rules_path.is_file(), "rules.json missing"

    rules_data = json.loads(rules_path.read_text())
    assert isinstance(rules_data, list)
    assert len(rules_data) > 0, "Rules list is empty"


def test_defaults_json_exists_and_loads() -> None:
    """Ensure the defaults file is present and valid JSON."""
    defaults_path = files("r2x_plexos_to_sienna.config") / "defaults.json"
    assert defaults_path.is_file(), "defaults.json missing"

    defaults_data = json.loads(defaults_path.read_text())
    assert isinstance(defaults_data, dict)
    assert "prime_mover_types" in defaults_data


def test_has_zone_rule() -> None:
    """Verify PLEXOSZone maps to LoadZone."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "PLEXOSZone" and rule.get("target_type") == "LoadZone"
        for rule in rules_data
    ), "Missing PLEXOSZone -> LoadZone rule"


def test_has_node_to_acbus_rule() -> None:
    """Verify PLEXOSNode maps to ACBus."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "PLEXOSNode" and rule.get("target_type") == "ACBus" for rule in rules_data
    ), "Missing PLEXOSNode -> ACBus rule"


def test_has_region_to_area_rule() -> None:
    """Verify PLEXOSRegion maps to Area."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "PLEXOSRegion" and rule.get("target_type") == "Area" for rule in rules_data
    ), "Missing PLEXOSRegion -> Area rule"


def test_has_region_to_power_load_rule() -> None:
    """Verify PLEXOSRegion maps to PowerLoad."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "PLEXOSRegion" and rule.get("target_type") == "PowerLoad"
        for rule in rules_data
    ), "Missing PLEXOSRegion -> PowerLoad rule"


def test_has_reserve_rule() -> None:
    """Verify PLEXOSReserve maps to VariableReserve."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "PLEXOSReserve" and rule.get("target_type") == "VariableReserve"
        for rule in rules_data
    ), "Missing PLEXOSReserve -> VariableReserve rule"


def test_has_generator_rules() -> None:
    """Verify PLEXOS generators map to Sienna generator types."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    # Thermal
    assert any(
        rule.get("source_type") == "PLEXOSGenerator" and rule.get("target_type") == "ThermalStandard"
        for rule in rules_data
    ), "Missing PLEXOSGenerator -> ThermalStandard rule"

    # Thermal Multi-Start
    assert any(
        rule.get("source_type") == "PLEXOSGenerator" and rule.get("target_type") == "ThermalMultiStart"
        for rule in rules_data
    ), "Missing PLEXOSGenerator -> ThermalMultiStart rule"

    # Hydro Dispatch
    assert any(
        rule.get("source_type") == "PLEXOSGenerator" and rule.get("target_type") == "HydroDispatch"
        for rule in rules_data
    ), "Missing PLEXOSGenerator -> HydroDispatch rule"

    # Hydro Turbine
    assert any(
        rule.get("source_type") == "PLEXOSGenerator" and rule.get("target_type") == "HydroTurbine"
        for rule in rules_data
    ), "Missing PLEXOSGenerator -> HydroTurbine rule"

    # Renewable Dispatch
    assert any(
        rule.get("source_type") == "PLEXOSGenerator" and rule.get("target_type") == "RenewableDispatch"
        for rule in rules_data
    ), "Missing PLEXOSGenerator -> RenewableDispatch rule"

    # Renewable Non-Dispatch
    assert any(
        rule.get("source_type") == "PLEXOSGenerator" and rule.get("target_type") == "RenewableNonDispatch"
        for rule in rules_data
    ), "Missing PLEXOSGenerator -> RenewableNonDispatch rule"

    # Synchronous Condenser
    assert any(
        rule.get("source_type") == "PLEXOSGenerator" and rule.get("target_type") == "SynchronousCondenser"
        for rule in rules_data
    ), "Missing PLEXOSGenerator -> SynchronousCondenser rule"


def test_has_storage_rules() -> None:
    """Verify PLEXOS storage components map to Sienna storage types."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    # Battery Storage
    assert any(
        rule.get("source_type") == "PLEXOSBattery" and rule.get("target_type") == "EnergyReservoirStorage"
        for rule in rules_data
    ), "Missing PLEXOSBattery -> EnergyReservoirStorage rule"

    # Hydro Reservoir
    assert any(
        rule.get("source_type") == "PLEXOSStorage" and rule.get("target_type") == "HydroReservoir"
        for rule in rules_data
    ), "Missing PLEXOSStorage -> HydroReservoir rule"


def test_has_line_rules() -> None:
    """Verify PLEXOSLine maps to various line types."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    # AC Line
    assert any(
        rule.get("source_type") == "PLEXOSLine" and rule.get("target_type") == "Line" for rule in rules_data
    ), "Missing PLEXOSLine -> Line rule"

    # Monitored Line
    assert any(
        rule.get("source_type") == "PLEXOSLine" and rule.get("target_type") == "MonitoredLine"
        for rule in rules_data
    ), "Missing PLEXOSLine -> MonitoredLine rule"

    # HVDC Line
    assert any(
        rule.get("source_type") == "PLEXOSLine" and rule.get("target_type") == "TwoTerminalGenericHVDCLine"
        for rule in rules_data
    ), "Missing PLEXOSLine -> TwoTerminalGenericHVDCLine rule"

    # HVDC Generic
    assert any(
        rule.get("source_type") == "PLEXOSLine" and rule.get("target_type") == "TwoTerminalGenericHVDCLine"
        for rule in rules_data
    ), "Missing PLEXOSLine -> TwoTerminalGenericHVDCLine rule"


def test_has_transformer_rules() -> None:
    """Verify PLEXOSTransformer maps to transformer types."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    # 2-Winding Transformer
    assert any(
        rule.get("source_type") == "PLEXOSTransformer" and rule.get("target_type") == "Transformer2W"
        for rule in rules_data
    ), "Missing PLEXOSTransformer -> Transformer2W rule"

    # Tap Transformer
    assert any(
        rule.get("source_type") == "PLEXOSTransformer" and rule.get("target_type") == "TapTransformer"
        for rule in rules_data
    ), "Missing PLEXOSTransformer -> TapTransformer rule"

    # Phase Shifting Transformer
    assert any(
        rule.get("source_type") == "PLEXOSTransformer"
        and rule.get("target_type") == "PhaseShiftingTransformer"
        for rule in rules_data
    ), "Missing PLEXOSTransformer -> PhaseShiftingTransformer rule"


def test_has_interface_rule() -> None:
    """Verify PLEXOSInterface maps to TransmissionInterface."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "PLEXOSInterface" and rule.get("target_type") == "TransmissionInterface"
        for rule in rules_data
    ), "Missing PLEXOSInterface -> TransmissionInterface rule"


def test_rules_have_required_fields() -> None:
    """Verify all rules have essential structure."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for i, rule in enumerate(rules_data):
        assert "source_type" in rule, f"Rule {i} missing source_type"
        assert "target_type" in rule, f"Rule {i} missing target_type"
        assert "version" in rule, f"Rule {i} missing version"
        # Either field_map or getters should be present
        assert "field_map" in rule or "getters" in rule, f"Rule {i} missing field_map and getters"


def test_filter_rules_have_valid_structure() -> None:
    """Verify rules with filters have valid filter structure."""
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())

    for rule in rules_data:
        if "filter" in rule:
            filter_obj = rule["filter"]
            assert "field" in filter_obj, f"Filter in rule {rule.get('name', 'unknown')} missing 'field'"
            assert "op" in filter_obj, f"Filter in rule {rule.get('name', 'unknown')} missing 'op'"
            assert "values" in filter_obj, f"Filter in rule {rule.get('name', 'unknown')} missing 'values'"
            assert isinstance(filter_obj["values"], list), "Filter values must be a list"


def test_prime_mover_mappings_exist() -> None:
    """Verify prime mover type mappings are complete."""
    defaults_path = files("r2x_plexos_to_sienna.config") / "defaults.json"
    defaults_data = json.loads(defaults_path.read_text())

    prime_movers = defaults_data.get("prime_mover_types", {})

    # Check some key mappings exist
    expected_categories = [
        "battery",
        "coal",
        "gas-cc",
        "gas-ct",
        "nuclear",
        "hydro-dispatch",
        "wind-ons",
        "upv",
        "distpv",
        "pumped-hydro",
    ]

    for category in expected_categories:
        assert category in prime_movers, f"Missing prime mover mapping for {category}"
