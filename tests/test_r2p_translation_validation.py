from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_core import ExecutionResult, Rule, TranslationContext


@pytest.fixture(scope="session")
def r2p_default_rules() -> list[Rule]:
    """Load the packaged ReEDS-to-PLEXOS rules."""
    from r2x_core import Rule

    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    return Rule.from_records(json.loads(rules_path.read_text()))


def build_r2p_context(source_system, rules) -> TranslationContext:
    """Helper to construct a translation context for ReEDS-to-PLEXOS."""
    from r2x_reeds_to_plexos import ReedsToPlexosConfig

    from r2x_core import System, TranslationContext

    target_system = System(name="plexos_target", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=rules,
    )
    return context


@pytest.fixture
def translated_r2p_context(
    r2p_default_rules, reeds_system_example
) -> tuple[TranslationContext, ExecutionResult]:
    from r2x_reeds_to_plexos import (
        attach_emissions_to_generators,
        attach_region_load_profiles,
        convert_pumped_storage_generators,
    )

    from r2x_core import apply_rules_to_context

    context = build_r2p_context(reeds_system_example, r2p_default_rules)
    result = apply_rules_to_context(context)
    attach_region_load_profiles(context)
    attach_emissions_to_generators(context)
    convert_pumped_storage_generators(context)
    return context, result


def test_r2p_translation_executes_with_package_rules(translated_r2p_context) -> None:
    """End-to-end smoke test that runs the packaged default ReEDS rules."""
    _, result = translated_r2p_context

    assert result.total_rules > 0, "Rules from the package config should run"

    converted = sum(rule_result.converted for rule_result in result.rule_results)
    assert converted > 0, "ReEDS systems with generators should emit PLEXOS components"


def test_r2p_generators_carry_capacity_and_outage_data(translated_r2p_context, reeds_system_example) -> None:
    """Verify generator attributes make it into the translated PLEXOS components."""
    from r2x_plexos.models.generator import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSGenerator

    context, result = translated_r2p_context
    assert result.total_rules > 0

    target_generators = list(context.target_system.get_components(PLEXOSGenerator))
    assert target_generators, "ReEDS generators should produce at least one PLEXOS generator"

    reeds_capacity = {gen.name: gen.capacity for gen in reeds_system_example.get_components(ReEDSGenerator)}
    reeds_outage = {
        gen.name: gen.forced_outage_rate for gen in reeds_system_example.get_components(ReEDSGenerator)
    }

    for plexos_gen in target_generators:
        expected_capacity = reeds_capacity.get(plexos_gen.name)
        expected_outage = reeds_outage.get(plexos_gen.name)
        assert expected_capacity is not None, f"Unexpected generator {plexos_gen.name} created"
        assert pytest.approx(expected_capacity) == plexos_gen.max_capacity, "Capacity should carry over"
        if expected_outage is not None:
            assert (
                pytest.approx(expected_outage * 100.0) == plexos_gen.forced_outage_rate
            ), "Forced outage rate should be converted to %"


def test_r2p_regions_generate_nodes_with_memberships(translated_r2p_context, reeds_system_example) -> None:
    """Ensure every ReEDS region produces a node and membership."""
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSRegion
    from r2x_reeds.models.components import ReEDSRegion

    context, _ = translated_r2p_context

    target_regions = list(context.target_system.get_components(PLEXOSRegion))
    target_nodes = list(context.target_system.get_components(PLEXOSNode))
    reeds_regions = list(reeds_system_example.get_components(ReEDSRegion))

    assert len(target_regions) == len(reeds_regions), "Each ReEDS region should map to a PLEXOS region"
    assert len(target_nodes) >= len(reeds_regions), "Each ReEDS region should map to a PLEXOS node"

    nodes_by_name = {node.name: node for node in target_nodes}
    for region in target_regions:
        node = nodes_by_name.get(region.name)
        assert node is not None, f"No node found for region {region.name}"
        memberships = context.target_system.get_supplemental_attributes_with_component(
            region, PLEXOSMembership
        )
        assert any(
            m.child_object == node for m in memberships
        ), f"Region {region.name} is missing membership to node {region.name}"


def test_r2p_transmission_lines_and_memberships(translated_r2p_context) -> None:
    """Confirm transmission lines are created and wired to nodes."""
    from r2x_plexos.models import PLEXOSLine, PLEXOSMembership, PLEXOSNode

    context, _ = translated_r2p_context
    lines = list(context.target_system.get_components(PLEXOSLine))
    assert lines, "Translation should emit at least one PLEXOSLine"

    nodes_by_name = {node.name: node for node in context.target_system.get_components(PLEXOSNode)}
    for line in lines:
        memberships = context.target_system.get_supplemental_attributes_with_component(line, PLEXOSMembership)
        node_from = nodes_by_name.get("R_WEST")
        node_to = nodes_by_name.get("R_EAST")
        assert any(m.parent_object == node_from for m in memberships), "Line missing NodeFrom membership"
        assert any(m.parent_object == node_to for m in memberships), "Line missing NodeTo membership"


def test_r2p_region_load_profiles(translated_r2p_context) -> None:
    """The translated region should receive the demand profile."""
    from r2x_plexos.models import PLEXOSRegion

    context, _ = translated_r2p_context
    region = next(r for r in context.target_system.get_components(PLEXOSRegion) if r.name == "R_WEST")
    assert region.fixed_load == pytest.approx(650.0)


def test_r2p_demand_time_series_attached(translated_r2p_context) -> None:
    """Load profiles should be attached to both the region and its node."""
    from r2x_plexos.models import PLEXOSNode, PLEXOSRegion

    context, _ = translated_r2p_context
    region = next(r for r in context.target_system.get_components(PLEXOSRegion) if r.name == "R_WEST")
    node = next(n for n in context.target_system.get_components(PLEXOSNode) if n.name == region.name)

    region_metadata = context.target_system.time_series.list_time_series_metadata(region)
    node_metadata = context.target_system.time_series.list_time_series_metadata(node)

    assert any(ts.name == "max_active_power" for ts in region_metadata)
    assert any(ts.name == "max_active_power" for ts in node_metadata)
    assert node.load == pytest.approx(region.fixed_load)


def test_r2p_emission_metadata_is_copied(translated_r2p_context) -> None:
    """Generators that carried emission metadata should keep it."""
    from r2x_plexos.models.generator import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSEmission

    context, _ = translated_r2p_context
    generator = next(
        gen for gen in context.target_system.get_components(PLEXOSGenerator) if gen.name == "WEST_CC"
    )
    emissions = context.target_system.get_supplemental_attributes_with_component(generator, ReEDSEmission)
    assert emissions, "Expected emission supplemental attribute on WEST_CC"


def test_r2p_creates_reserve_components(translated_r2p_context) -> None:
    """Reserve requirements should translate into PLEXOS reserves."""
    from r2x_plexos.models import PLEXOSReserve

    context, _ = translated_r2p_context
    reserves = list(context.target_system.get_components(PLEXOSReserve))
    assert reserves, "Translation should emit at least one PLEXOSReserve"
    reserve = reserves[0]
    assert reserve.timeframe == pytest.approx(900.0)
    assert reserve.duration == pytest.approx(600.0)


def test_r2p_battery_generators_are_translated(translated_r2p_context, reeds_system_example) -> None:
    """Battery-category ReEDS generators should create PLEXOS batteries."""
    from r2x_plexos.models import PLEXOSBattery
    from r2x_reeds.models.components import ReEDSGenerator

    context, _ = translated_r2p_context
    source_battery_names = {
        gen.name
        for gen in reeds_system_example.get_components(ReEDSGenerator)
        if (getattr(gen, "category", "") or "").casefold().startswith("battery_")
    }
    batteries = list(context.target_system.get_components(PLEXOSBattery))

    assert len(batteries) == len(
        source_battery_names
    ), "Battery generators should map 1:1 to PLEXOS batteries"
    assert source_battery_names == {battery.name for battery in batteries}


def test_r2p_pumped_storage_converted(translated_r2p_context) -> None:
    """Pumped-storage generators should become PLEXOS storage components."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSStorage
    from r2x_plexos.models.generator import PLEXOSGenerator

    context, _ = translated_r2p_context

    storages = list(context.target_system.get_components(PLEXOSStorage))
    assert len(storages) == 1, "Only pumped-hydro should produce a PLEXOSStorage"
    storage = storages[0]

    generators = list(context.target_system.get_components(PLEXOSGenerator))
    generator = next((g for g in generators if g.name == "WEST_PSH"), None)
    assert generator is not None, "Pumped storage should also remain as a generator"

    memberships_storage = context.target_system.get_supplemental_attributes_with_component(
        storage, PLEXOSMembership
    )
    memberships_generator = context.target_system.get_supplemental_attributes_with_component(
        generator, PLEXOSMembership
    )
    node_memberships_storage = [m for m in memberships_storage if m.collection == CollectionEnum.Nodes]
    node_memberships_generator = [m for m in memberships_generator if m.collection == CollectionEnum.Nodes]
    assert node_memberships_storage, "Storage should inherit node membership from its generator counterpart"
    assert node_memberships_generator, "Generator should have a node membership for pumped-hydro"

    target_nodes = {node.name: node for node in context.target_system.get_components(PLEXOSNode)}
    expected_node = target_nodes.get("R_WEST")
    assert expected_node is not None, "Expected node for region R_WEST"
    assert any(
        m.parent_object == generator and m.child_object == expected_node for m in node_memberships_generator
    )
    assert any(
        m.parent_object == storage and m.child_object == expected_node for m in node_memberships_storage
    )


def test_r2p_thermal_generators_translate_with_heat_rate(
    translated_r2p_context, reeds_system_example
) -> None:
    """Thermal generators should translate with heat rate preserved."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models import ReEDSGenerator

    context, _ = translated_r2p_context
    source_thermal = next(
        gen
        for gen in reeds_system_example.get_components(ReEDSGenerator)
        if gen.name == "EAST_COAL" and getattr(gen, "heat_rate", None) is not None
    )

    target_gen = next(
        gen for gen in context.target_system.get_components(PLEXOSGenerator) if gen.name == "EAST_COAL"
    )
    assert target_gen.heat_rate == pytest.approx(source_thermal.heat_rate), "Heat rate should be preserved"
    assert target_gen.max_capacity == pytest.approx(source_thermal.capacity), "Capacity should be translated"


def test_r2p_variable_generators_have_time_series(translated_r2p_context) -> None:
    """Variable generators with time series should have them transferred to PLEXOS."""
    from r2x_plexos.models import PLEXOSGenerator

    context, _ = translated_r2p_context
    wind_gens_in_target = [
        gen
        for gen in context.target_system.get_components(PLEXOSGenerator)
        if gen.category and "wind" in gen.category.lower()
    ]
    assert len(wind_gens_in_target) > 0, "Should have at least one wind generator translated"

    gens_with_ts = []
    for gen in wind_gens_in_target:
        ts_metadata = context.target_system.list_time_series_metadata(gen)
        if ts_metadata:
            gens_with_ts.append(gen.name)

    assert len(gens_with_ts) > 0, "At least one wind generator should have time series"


def test_r2p_storage_translates_to_batteries(translated_r2p_context, reeds_system_example) -> None:
    """Battery storage generators should translate to PLEXOSBattery components."""
    from r2x_plexos.models import PLEXOSBattery

    context, _ = translated_r2p_context

    target_batteries = list(context.target_system.get_components(PLEXOSBattery))
    assert len(target_batteries) > 0, "Should have at least one battery"
    for battery in target_batteries:
        assert battery.max_power is not None and battery.max_power > 0, "Battery should have power capacity"


def test_r2p_all_time_series_transferred_to_generators(translated_r2p_context) -> None:
    """Time series on ReEDS generators should be transferred to PLEXOS generators."""
    from r2x_plexos.models import PLEXOSGenerator

    context, _ = translated_r2p_context
    plexos_gens_with_ts = []
    for gen in context.target_system.get_components(PLEXOSGenerator):
        ts_metadata = context.target_system.list_time_series_metadata(gen)
        if ts_metadata:
            plexos_gens_with_ts.append(gen.name)

    assert (
        len(plexos_gens_with_ts) >= 1
    ), "Should have transferred time series from at least one source generator"


def test_r2p_time_series_data_integrity(translated_r2p_context) -> None:
    """Time series metadata should be preserved during translation."""
    from r2x_plexos.models import PLEXOSGenerator

    context, _ = translated_r2p_context
    target_gen = next(
        gen for gen in context.target_system.get_components(PLEXOSGenerator) if gen.name == "TEXAS_SOLAR"
    )

    ts_metadata_list = context.target_system.list_time_series_metadata(target_gen)
    assert len(ts_metadata_list) > 0, "TEXAS_SOLAR should have time series"

    ts_metadata = ts_metadata_list[0]
    assert ts_metadata.length == 24, "Time series should have 24 data points"


def test_r2p_generator_unit_conversions_accuracy(translated_r2p_context, reeds_system_example) -> None:
    """Verify forced outage rate conversion (fraction→%) and heat rate preservation."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models import ReEDSGenerator

    context, _ = translated_r2p_context

    # Test forced outage rate conversion: fraction -> percent on EAST_COAL
    source_coal = next(
        gen
        for gen in reeds_system_example.get_components(ReEDSGenerator)
        if gen.name == "EAST_COAL" and getattr(gen, "forced_outage_rate", None) is not None
    )
    target_coal = next(
        gen for gen in context.target_system.get_components(PLEXOSGenerator) if gen.name == "EAST_COAL"
    )

    expected_outage_percent = source_coal.forced_outage_rate * 100.0
    assert target_coal.forced_outage_rate == pytest.approx(
        expected_outage_percent
    ), "Outage rate should be in percent"

    # Test heat rate preservation
    assert target_coal.heat_rate == pytest.approx(source_coal.heat_rate), "Heat rate should be preserved"


def test_r2p_all_generators_have_node_memberships(translated_r2p_context) -> None:
    """All translated generators should have node memberships."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSMembership

    context, _ = translated_r2p_context

    generators = list(context.target_system.get_components(PLEXOSGenerator))
    for gen in generators:
        memberships = context.target_system.get_supplemental_attributes_with_component(gen, PLEXOSMembership)
        node_memberships = [m for m in memberships if m.collection == CollectionEnum.Nodes]
        assert len(node_memberships) > 0, f"Generator {gen.name} should have node membership"


def test_r2p_generator_and_battery_counts(translated_r2p_context, reeds_system_example) -> None:
    """Verify generator and battery component counts from base ReEDS model."""
    from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator
    from r2x_reeds.models import ReEDSGenerator

    context, _ = translated_r2p_context

    # Count source ReEDS generators
    source_generators = list(reeds_system_example.get_components(ReEDSGenerator))
    assert len(source_generators) > 0, "Test fixture should have generators"

    # Count target components
    target_generators = list(context.target_system.get_components(PLEXOSGenerator))
    target_batteries = list(context.target_system.get_components(PLEXOSBattery))

    # All base generators should translate to at least a PLEXOS component
    assert len(target_generators) > 0, "Should have at least one PLEXOS generator"

    # Count battery-category generators in source
    battery_gens = [
        g for g in source_generators if (getattr(g, "category", "") or "").casefold().startswith("battery_")
    ]
    assert len(target_batteries) == len(
        battery_gens
    ), "Battery count should match battery-category source generators"
