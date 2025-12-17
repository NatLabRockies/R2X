"""Translation tests."""

from __future__ import annotations

import json
from importlib.resources import files

import pytest


def test_reeds_region_translates_to_area() -> None:
    """Ensure ReEDSRegion produces a Sienna Area with mapped fields and defaults."""
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import Area

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    source.add_component(
        ReEDSRegion(name="R_TEST", category="region-cat", max_active_power=123.0, interconnect="west")
    )

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    areas = list(target.get_components(Area))
    assert len(areas) == 1
    area = areas[0]
    assert area.name == "R_TEST"
    assert area.category == "region-cat"
    assert pytest.approx(123.0) == area.peak_active_power
    assert pytest.approx(0.0) == area.peak_reactive_power
    assert pytest.approx(0.0) == area.load_response


def test_reeds_generators_translate_to_hydro_gen() -> None:
    """Ensure ReEDS thermal/variable generators and interfaces translate to Sienna components."""
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion, ReEDSThermalGenerator, ReEDSVariableGenerator
    from r2x_sienna.models import (
        Area,
        AreaInterchange,
        RenewableDispatch,
        RenewableNonDispatch,
        ThermalStandard,
    )

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="R_GEN", category="region")
    source.add_component(region)
    source.add_component(
        ReEDSThermalGenerator(
            name="THERM1",
            region=region,
            technology="gas-cc",
            capacity=100.0,
            heat_rate=7.5,
            fuel_type="gas",
        )
    )
    source.add_component(
        ReEDSVariableGenerator(
            name="VRE1",
            region=region,
            technology="wind-ons",
            capacity=50.0,
        )
    )
    source.add_component(
        ReEDSVariableGenerator(
            name="DISTPV",
            region=region,
            technology="distpv",
            capacity=25.0,
        )
    )
    source.add_component(ReEDSInterface(name="IFACE", from_region=region, to_region=region))

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    # Region rule should still produce an Area
    assert any(isinstance(comp, Area) for comp in target.get_components(Area))

    thermal_gens = list(target.get_components(ThermalStandard))
    vre_dispatch = list(target.get_components(RenewableDispatch))
    vre_nondispatch = list(target.get_components(RenewableNonDispatch))
    interchanges = list(target.get_components(AreaInterchange))

    assert len(thermal_gens) == 1
    assert len(vre_dispatch) == 1
    assert len(vre_nondispatch) == 1

    assert thermal_gens[0].name == "THERM1"
    assert thermal_gens[0].category == "gas-cc"

    assert vre_dispatch[0].name == "VRE1"
    assert vre_dispatch[0].category == "wind-ons"

    assert vre_nondispatch[0].name == "DISTPV"
    assert vre_nondispatch[0].category == "distpv"
    assert len(interchanges) == 1
    interchange = interchanges[0]
    assert interchange.from_area is not None and interchange.from_area.name == "R_GEN"
    assert interchange.to_area is not None and interchange.to_area.name == "R_GEN"
