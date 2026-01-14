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


def test_has_region_to_area_rule() -> None:
    """Verify ReEDSRegion maps to Sienna Area."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSRegion" and rule.get("target_type") == "Area" for rule in rules_data
    ), "Missing ReEDSRegion -> Area rule"


def test_has_generator_rules() -> None:
    """Verify ReEDS generators map to Sienna generator placeholders."""
    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules_data = json.loads(rules_path.read_text())

    assert any(
        rule.get("source_type") == "ReEDSThermalGenerator" and rule.get("target_type") == "ThermalStandard"
        for rule in rules_data
    ), "Missing ReEDSThermalGenerator -> ThermalStandard rule"

    assert any(
        rule.get("source_type") == "ReEDSVariableGenerator" and rule.get("target_type") == "RenewableDispatch"
        for rule in rules_data
    ), "Missing ReEDSVariableGenerator -> RenewableDispatch rule"

    assert any(
        rule.get("source_type") == "ReEDSVariableGenerator"
        and rule.get("target_type") == "RenewableNonDispatch"
        and rule.get("filter", {}).get("op") in ("eq", "startswith")
        for rule in rules_data
    ), "Missing ReEDSVariableGenerator -> RenewableNonDispatch (distpv) rule"

    assert any(
        rule.get("source_type") == "ReEDSInterface" and rule.get("target_type") == "AreaInterchange"
        for rule in rules_data
    ), "Missing ReEDSInterface -> AreaInterchange rule"
