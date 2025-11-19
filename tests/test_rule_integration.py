from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from r2x_core.plugin_config import SiennaToPlexosConfig

if TYPE_CHECKING:
    from r2x_core import Rule


@pytest.fixture
def default_rules() -> list[Rule]:
    import json
    from importlib.resources import files

    from r2x_core import Rule

    config_files = files("r2x_core.config")
    rules_file = config_files / "rules.json"
    rules_json = json.loads(rules_file.read_text())
    return Rule.from_records(rules_json)


@pytest.fixture
def source_system(request) -> list[int]:
    return request.getfixturevalue(request.param)


@pytest.mark.parametrize(
    "source_system",
    [
        pytest.param("sienna_system_empty"),
        pytest.param("sienna_system_with_area_and_zone"),
        pytest.param("sienna_system_with_buses"),
        pytest.param("sienna_system_with_buses_and_power_load"),
        pytest.param("sienna_system_with_thermal_generators"),
        pytest.param("system_with_zones"),
        pytest.param("system_with_5_buses"),
        pytest.param("system_with_loads"),
        pytest.param("system_with_thermal_generators"),
        pytest.param("system_with_renewables"),
        pytest.param("system_with_hydro"),
        pytest.param("system_with_storage"),
        pytest.param("system_with_network"),
        pytest.param("system_with_reserves"),
        pytest.param("system_complete"),
    ],
    indirect=True,
)
def test_rules_from_config(default_rules, source_system, caplog):
    from r2x_core import System, TranslationContext, TranslationResult, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=source_system, target_system=target_system, config=config, rules=default_rules
    )

    result = apply_rules_to_context(context)

    assert isinstance(result, TranslationResult), "Result should be a TranslationResult object"
    assert result.total_rules > 0, "Should have processed at least some rules"

    from r2x_sienna.models import ACBus

    acbus_rule_key = "ACBus->PLEXOSNode(v1)"
    acbus_results = [r for r in result.rule_results if r.rule == acbus_rule_key]
    assert acbus_results, f"ACBus->PLEXOSNode rule missing. Rules: {[r.rule for r in result.rule_results]}"

    converted_count = acbus_results[0].converted
    has_buses = bool(list(source_system.get_components(ACBus)))
    if has_buses:
        assert converted_count > 0, (
            f"ACBus->PLEXOSNode rule should convert buses when present. Converted: {converted_count}"
        )
    else:
        assert converted_count == 0


def test_system_with_zones_component_count(system_with_zones) -> None:
    """Advanced system with zones has correct component count."""
    components = list(system_with_zones.iter_all_components())
    assert len(components) == 2, f"Expected 2 components, got {len(components)}"


def test_system_with_5_buses_component_count(system_with_5_buses) -> None:
    """Advanced system with 5 buses has correct component count."""
    components = list(system_with_5_buses.iter_all_components())
    assert len(components) == 7, f"Expected 7 components, got {len(components)}"


def test_system_with_loads_component_count(system_with_loads) -> None:
    """Advanced system with loads has correct component count."""
    components = list(system_with_loads.iter_all_components())
    assert len(components) == 9, f"Expected 9 components, got {len(components)}"


def test_system_with_thermal_generators_component_count(
    system_with_thermal_generators,
) -> None:
    """Advanced system with thermal generators has correct component count."""
    components = list(system_with_thermal_generators.iter_all_components())
    assert len(components) == 14, f"Expected 14 components, got {len(components)}"


def test_system_with_renewables_component_count(system_with_renewables) -> None:
    """Advanced system with renewables has correct component count."""
    components = list(system_with_renewables.iter_all_components())
    assert len(components) == 17, f"Expected 17 components, got {len(components)}"


def test_system_with_hydro_component_count(system_with_hydro) -> None:
    """Advanced system with hydro has correct component count."""
    components = list(system_with_hydro.iter_all_components())
    assert len(components) == 20, f"Expected 20 components, got {len(components)}"


def test_system_with_storage_component_count(system_with_storage) -> None:
    """Advanced system with storage has correct component count."""
    components = list(system_with_storage.iter_all_components())
    assert len(components) == 21, f"Expected 21 components, got {len(components)}"


def test_system_with_network_component_count(system_with_network) -> None:
    """Advanced system with network has correct component count."""
    components = list(system_with_network.iter_all_components())
    assert len(components) == 32, f"Expected 32 components, got {len(components)}"


def test_system_with_reserves_component_count(system_with_reserves) -> None:
    """Advanced system with reserves has correct component count."""
    components = list(system_with_reserves.iter_all_components())
    assert len(components) == 34, f"Expected 34 components, got {len(components)}"


def test_system_complete_component_count(system_complete) -> None:
    """Complete advanced system has correct component count."""
    components = list(system_complete.iter_all_components())
    total = len(components)
    assert total == 34, f"Expected 34 components, got {total}"


def test_system_with_zones_conversion(default_rules, system_with_zones, caplog):
    """Verify zones and areas are converted successfully."""
    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=system_with_zones,
        target_system=target_system,
        config=config,
        rules=default_rules,
    )

    result = apply_rules_to_context(context)

    assert result.total_rules > 0, "Should have processed rules"
    assert result.total_rules > 0, "Should have processed at least some rules"


def test_system_with_5_buses_conversion(default_rules, system_with_5_buses, caplog):
    """Verify buses are converted successfully."""
    from r2x_sienna.models import ACBus

    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=system_with_5_buses,
        target_system=target_system,
        config=config,
        rules=default_rules,
    )

    result = apply_rules_to_context(context)

    # Check that buses were converted
    acbus_results = [r for r in result.rule_results if "ACBus->PLEXOSNode" in r.rule]
    assert acbus_results, "ACBus->PLEXOSNode rule should be present"

    converted_count = acbus_results[0].converted
    buses = list(system_with_5_buses.get_components(ACBus))
    assert len(buses) == 5, f"Expected 5 buses, got {len(buses)}"
    assert converted_count == 5, f"Expected 5 buses converted, got {converted_count}"


def test_system_with_loads_conversion(default_rules, system_with_loads, caplog):
    """Verify loads are processed without errors."""
    from r2x_sienna.models import PowerLoad

    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=system_with_loads,
        target_system=target_system,
        config=config,
        rules=default_rules,
    )

    result = apply_rules_to_context(context)

    # Verify the system processed without errors
    assert result.total_rules > 0, "Should have processed rules"

    loads = list(system_with_loads.get_components(PowerLoad))
    assert len(loads) == 2, f"Expected 2 loads, got {len(loads)}"


def test_system_with_thermal_generators_conversion(default_rules, system_with_thermal_generators, caplog):
    """Verify thermal generators are converted successfully."""
    from r2x_sienna.models import ThermalStandard

    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=system_with_thermal_generators,
        target_system=target_system,
        config=config,
        rules=default_rules,
    )

    result = apply_rules_to_context(context)

    # Check that thermal generators were converted
    thermal_results = [r for r in result.rule_results if "ThermalStandard->PLEXOSGenerator" in r.rule]
    assert thermal_results, "ThermalStandard->PLEXOSGenerator rule should be present"

    converted_count = thermal_results[0].converted
    thermals = list(system_with_thermal_generators.get_components(ThermalStandard))
    assert len(thermals) == 5, f"Expected 5 thermal generators, got {len(thermals)}"
    assert converted_count == 5, f"Expected 5 thermal generators converted, got {converted_count}"


def test_system_with_renewables_conversion(default_rules, system_with_renewables, caplog):
    """Verify renewable generators are processed (may skip if rules not implemented)."""
    from r2x_sienna.models import RenewableDispatch

    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=system_with_renewables,
        target_system=target_system,
        config=config,
        rules=default_rules,
    )

    result = apply_rules_to_context(context)

    # Verify the system processed without errors
    assert result.total_rules > 0, "Should have processed rules"

    renewables = list(system_with_renewables.get_components(RenewableDispatch))
    assert len(renewables) == 3, f"Expected 3 renewable generators, got {len(renewables)}"


def test_system_with_network_conversion(default_rules, system_with_network, caplog):
    """Verify network components are processed."""
    from r2x_sienna.models import Line, Transformer2W

    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=system_with_network,
        target_system=target_system,
        config=config,
        rules=default_rules,
    )

    result = apply_rules_to_context(context)

    # Verify the system processed without errors
    assert result.total_rules > 0, "Should have processed rules"

    lines = list(system_with_network.get_components(Line))
    assert len(lines) == 4, f"Expected 4 lines, got {len(lines)}"

    transformers = list(system_with_network.get_components(Transformer2W))
    assert len(transformers) == 1, f"Expected 1 transformer, got {len(transformers)}"


def test_system_complete_conversion(default_rules, system_complete, caplog):
    """Verify complete advanced system is processed successfully."""
    from r2x_sienna.models import ACBus, ThermalStandard

    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=system_complete,
        target_system=target_system,
        config=config,
        rules=default_rules,
    )

    result = apply_rules_to_context(context)

    assert result.total_rules > 0, "Should have processed rules"
    assert result.total_rules > 0, "Should have processed at least some rules"

    # Verify key component types were processed
    acbus_results = [r for r in result.rule_results if "ACBus->PLEXOSNode" in r.rule]
    assert acbus_results, "ACBus->PLEXOSNode rule should be present"

    thermal_results = [r for r in result.rule_results if "ThermalStandard->PLEXOSGenerator" in r.rule]
    assert thermal_results, "ThermalStandard->PLEXOSGenerator rule should be present"

    # Verify component counts in source
    buses = list(system_complete.get_components(ACBus))
    assert len(buses) == 5, f"Expected 5 buses, got {len(buses)}"

    thermals = list(system_complete.get_components(ThermalStandard))
    assert len(thermals) == 5, f"Expected 5 thermal generators, got {len(thermals)}"
