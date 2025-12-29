from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_core import Rule


@pytest.fixture(scope="session")
def default_rules() -> list[Rule]:
    """Load the default S2P rules directly from the package config."""
    from r2x_core import Rule

    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules_data = json.loads(rules_path.read_text())
    return Rule.from_records(rules_data)


@pytest.fixture
def source_system(request):
    """Proxy fixture so parametrized tests can reference existing systems."""
    return request.getfixturevalue(request.param)


def run_translation(source_system, rules):
    """Create a TranslationContext and apply the package rules."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters_utils import (
        ensure_battery_node_memberships,
        ensure_generator_node_memberships,
        ensure_interface_line_memberships,
        ensure_node_zone_memberships,
        ensure_pumped_hydro_storage_memberships,
        ensure_region_node_memberships,
        ensure_reserve_generator_memberships,
        ensure_transformer_node_memberships,
    )

    from r2x_core import System, TranslationContext, apply_rules_to_context

    target_system = System(name="TargetSystem", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=rules,
    )
    result = apply_rules_to_context(context)

    # Apply all membership ensuring functions
    ensure_region_node_memberships(context)
    ensure_generator_node_memberships(context)
    ensure_battery_node_memberships(context)
    ensure_node_zone_memberships(context)
    ensure_reserve_generator_memberships(context)
    ensure_transformer_node_memberships(context)
    ensure_interface_line_memberships(context)
    ensure_pumped_hydro_storage_memberships(context)

    return result, context


TRANSLATION_CASES = [
    pytest.param("sienna_system_empty", False, id="empty"),
    pytest.param("system_with_5_buses", True, id="five-buses"),
    pytest.param("system_with_thermal_generators", True, id="thermal"),
    pytest.param("system_complete", True, id="complete"),
]


@pytest.mark.parametrize(
    ("source_system", "expect_conversions"),
    TRANSLATION_CASES,
    indirect=["source_system"],
)
def test_translation_pipeline_uses_package_rules(default_rules, source_system, expect_conversions):
    """End-to-end translation validation using only package-provided rules."""
    result, target_system = run_translation(source_system, default_rules)

    assert result.total_rules > 0, "Rules from the package config should execute"

    converted_components = sum(rule_result.converted for rule_result in result.rule_results)
    generated_targets = sum(1 for _ in target_system.iter_all_components())

    if expect_conversions:
        assert converted_components > 0, "Populated systems should convert at least one component"
        assert generated_targets > 0, "Translated systems should emit target components"
    else:
        assert converted_components == 0, "Empty sources should not produce conversions"
        assert generated_targets == 0, "No target components should be emitted for empty sources"


def test_s2p_nodes_created_from_buses(default_rules, system_with_5_buses):
    """Test that ACBus components are translated to PLEXOSNode."""
    from r2x_plexos.models import PLEXOSNode
    from r2x_sienna.models import ACBus

    result, context = run_translation(system_with_5_buses, default_rules)

    source_buses = list(system_with_5_buses.get_components(ACBus))
    target_nodes = list(context.target_system.get_components(PLEXOSNode))

    assert len(target_nodes) == len(source_buses), "Each bus should create a node"

    source_names = {bus.name for bus in source_buses}
    target_names = {node.name for node in target_nodes}
    assert source_names == target_names, "Node names should match bus names"


def test_s2p_generators_created_from_thermals(default_rules, system_with_thermal_generators):
    """Test that thermal generators are translated to PLEXOSGenerator."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_sienna.models import ThermalStandard

    result, context = run_translation(system_with_thermal_generators, default_rules)

    source_thermals = list(system_with_thermal_generators.get_components(ThermalStandard))
    target_generators = list(context.target_system.get_components(PLEXOSGenerator))

    assert len(target_generators) >= len(
        source_thermals
    ), "Should have at least as many generators as thermals"

    thermal_names = {gen.name for gen in source_thermals}
    generator_names = {gen.name for gen in target_generators}
    assert thermal_names.issubset(generator_names), "All thermal names should be in generators"


def test_s2p_region_node_memberships_created(default_rules, system_complete):
    """Test that Region->Node memberships are created via ensure_region_node_memberships."""
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSRegion

    result, context = run_translation(system_complete, default_rules)

    regions = list(context.target_system.get_components(PLEXOSRegion))
    nodes = list(context.target_system.get_components(PLEXOSNode))

    if not regions or not nodes:
        pytest.skip("No regions or nodes created in translation")

    # Get all memberships
    all_memberships = list(context.target_system.get_supplemental_attributes(PLEXOSMembership))

    # Check that region-node memberships exist
    region_node_memberships = [
        m
        for m in all_memberships
        if isinstance(m.parent_object, PLEXOSNode) and isinstance(m.child_object, PLEXOSRegion)
    ]

    assert len(region_node_memberships) > 0, "Should have region-node memberships"


def test_s2p_generator_node_memberships_created(default_rules, system_with_thermal_generators):
    """Test that Generator->Node memberships are created via ensure_generator_node_memberships."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSMembership, PLEXOSNode

    result, context = run_translation(system_with_thermal_generators, default_rules)

    generators = list(context.target_system.get_components(PLEXOSGenerator))
    nodes = list(context.target_system.get_components(PLEXOSNode))

    if not generators or not nodes:
        pytest.skip("No generators or nodes created in translation")

    # Get all memberships
    all_memberships = list(context.target_system.get_supplemental_attributes(PLEXOSMembership))

    # Check that generator-node memberships exist
    gen_node_memberships = [
        m
        for m in all_memberships
        if isinstance(m.parent_object, PLEXOSGenerator)
        and isinstance(m.child_object, PLEXOSNode)
        and m.collection == CollectionEnum.Nodes
    ]

    assert len(gen_node_memberships) > 0, "Should have generator-node memberships"


def test_s2p_line_node_memberships_created(default_rules, system_complete):
    """Test that Line->Node (from/to) memberships are created."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSLine, PLEXOSMembership, PLEXOSNode

    result, context = run_translation(system_complete, default_rules)

    lines = list(context.target_system.get_components(PLEXOSLine))
    nodes = list(context.target_system.get_components(PLEXOSNode))

    if not lines or not nodes:
        pytest.skip("No lines or nodes created in translation")

    # Get all memberships
    all_memberships = list(context.target_system.get_supplemental_attributes(PLEXOSMembership))

    # Check that line-node memberships exist (both from and to)
    line_from_memberships = [
        m
        for m in all_memberships
        if isinstance(m.parent_object, PLEXOSLine)
        and isinstance(m.child_object, PLEXOSNode)
        and m.collection == CollectionEnum.NodeFrom
    ]

    line_to_memberships = [
        m
        for m in all_memberships
        if isinstance(m.parent_object, PLEXOSLine)
        and isinstance(m.child_object, PLEXOSNode)
        and m.collection == CollectionEnum.NodeTo
    ]

    # Each line should have both from and to memberships
    assert len(line_from_memberships) > 0, "Should have line NodeFrom memberships"
    assert len(line_to_memberships) > 0, "Should have line NodeTo memberships"


def test_s2p_node_zone_memberships_created(default_rules, system_complete):
    """Test that Node->Zone memberships are created via ensure_node_zone_memberships."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSZone

    result, context = run_translation(system_complete, default_rules)

    nodes = list(context.target_system.get_components(PLEXOSNode))
    zones = list(context.target_system.get_components(PLEXOSZone))

    if not nodes or not zones:
        pytest.skip("No nodes or zones created in translation")

    # Get all memberships
    all_memberships = list(context.target_system.get_supplemental_attributes(PLEXOSMembership))

    # Check that node-zone memberships exist
    node_zone_memberships = [
        m
        for m in all_memberships
        if isinstance(m.parent_object, PLEXOSNode)
        and isinstance(m.child_object, PLEXOSZone)
        and m.collection == CollectionEnum.Zone
    ]

    assert len(node_zone_memberships) > 0, "Should have node-zone memberships"


def test_s2p_battery_node_memberships_created(default_rules, system_complete):
    """Test that Battery->Node memberships are created via ensure_battery_node_memberships."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSBattery, PLEXOSMembership, PLEXOSNode

    result, context = run_translation(system_complete, default_rules)

    batteries = list(context.target_system.get_components(PLEXOSBattery))
    nodes = list(context.target_system.get_components(PLEXOSNode))

    if not batteries or not nodes:
        pytest.skip("No batteries or nodes created in translation")

    # Get all memberships
    all_memberships = list(context.target_system.get_supplemental_attributes(PLEXOSMembership))

    # Check that battery-node memberships exist
    battery_node_memberships = [
        m
        for m in all_memberships
        if isinstance(m.parent_object, PLEXOSBattery)
        and isinstance(m.child_object, PLEXOSNode)
        and m.collection == CollectionEnum.Nodes
    ]

    if batteries:
        assert len(battery_node_memberships) > 0, "Should have battery-node memberships if batteries exist"


def test_s2p_transformer_node_memberships_created(default_rules, system_complete):
    """Test that Transformer->Node (from/to) memberships are created."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSTransformer

    result, context = run_translation(system_complete, default_rules)

    transformers = list(context.target_system.get_components(PLEXOSTransformer))
    nodes = list(context.target_system.get_components(PLEXOSNode))

    if not transformers or not nodes:
        pytest.skip("No transformers or nodes created in translation")

    # Get all memberships
    all_memberships = list(context.target_system.get_supplemental_attributes(PLEXOSMembership))

    # Check that transformer-node memberships exist (both from and to)
    transformer_from_memberships = [
        m
        for m in all_memberships
        if isinstance(m.parent_object, PLEXOSTransformer)
        and isinstance(m.child_object, PLEXOSNode)
        and m.collection == CollectionEnum.NodeFrom
    ]

    transformer_to_memberships = [
        m
        for m in all_memberships
        if isinstance(m.parent_object, PLEXOSTransformer)
        and isinstance(m.child_object, PLEXOSNode)
        and m.collection == CollectionEnum.NodeTo
    ]

    # Each transformer should have both from and to memberships
    assert len(transformer_from_memberships) > 0, "Should have transformer NodeFrom memberships"
    assert len(transformer_to_memberships) > 0, "Should have transformer NodeTo memberships"


def test_s2p_heat_rate_data_transferred(default_rules, system_with_thermal_generators):
    """Test that heat rate data is transferred to PLEXOS generators."""
    from r2x_plexos.models import PLEXOSGenerator

    result, context = run_translation(system_with_thermal_generators, default_rules)

    generators = list(context.target_system.get_components(PLEXOSGenerator))

    if not generators:
        pytest.skip("No generators created in translation")

    # Check that at least one generator has heat rate data
    generators_with_heat_rate = [
        gen
        for gen in generators
        if hasattr(gen, "heat_rate") and gen.heat_rate is not None and gen.heat_rate > 0
    ]

    # Thermal generators should have heat rate
    assert len(generators_with_heat_rate) > 0, "At least one thermal generator should have heat rate"


def test_s2p_capacity_data_transferred(default_rules, system_with_thermal_generators):
    """Test that capacity data is transferred to PLEXOS generators."""
    from r2x_plexos.models import PLEXOSGenerator

    result, context = run_translation(system_with_thermal_generators, default_rules)

    generators = list(context.target_system.get_components(PLEXOSGenerator))

    if not generators:
        pytest.skip("No generators created in translation")

    # Check that generators have capacity
    generators_with_capacity = [
        gen
        for gen in generators
        if hasattr(gen, "max_capacity") and gen.max_capacity is not None and gen.max_capacity > 0
    ]

    assert len(generators_with_capacity) > 0, "Generators should have capacity data"


def test_s2p_no_duplicate_components(default_rules, system_complete):
    """Test that no duplicate components are created."""
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSLine, PLEXOSNode

    result, context = run_translation(system_complete, default_rules)

    # Check nodes
    nodes = list(context.target_system.get_components(PLEXOSNode))
    node_names = [n.name for n in nodes]
    assert len(node_names) == len(set(node_names)), "No duplicate nodes should exist"

    # Check generators
    generators = list(context.target_system.get_components(PLEXOSGenerator))
    gen_names = [g.name for g in generators]
    assert len(gen_names) == len(set(gen_names)), "No duplicate generators should exist"

    # Check lines
    lines = list(context.target_system.get_components(PLEXOSLine))
    line_names = [line.name for line in lines]
    assert len(line_names) == len(set(line_names)), "No duplicate lines should exist"


def test_s2p_all_components_have_names(default_rules, system_complete):
    """Test that all translated components have valid names."""
    result, context = run_translation(system_complete, default_rules)

    for component in context.target_system.iter_all_components():
        assert hasattr(component, "name"), f"Component {component} missing name attribute"
        assert component.name is not None, f"Component {component} has None name"
        assert len(component.name) > 0, f"Component {component} has empty name"


def test_s2p_membership_collections_correct(default_rules, system_complete):
    """Test that memberships have correct collection types."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership

    result, context = run_translation(system_complete, default_rules)

    all_memberships = list(context.target_system.get_supplemental_attributes(PLEXOSMembership))

    if not all_memberships:
        pytest.skip("No memberships created in translation")

    # Check that all memberships have valid collections
    for membership in all_memberships:
        assert isinstance(
            membership.collection, CollectionEnum
        ), f"Membership has invalid collection type: {type(membership.collection)}"


def test_ensure_head_storage_generator_membership_matches_base_name():
    """Test that ensure_head_storage_generator_membership matches base names correctly."""
    from plexosdb.enums import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSMembership, PLEXOSStorage
    from r2x_sienna_to_plexos.getters_utils import ensure_head_storage_generator_membership

    from r2x_core import System, TranslationContext

    # Setup systems
    target_system = System(name="target")
    context = TranslationContext(
        source_system=None,
        target_system=target_system,
        config=None,
        rules=[],
    )

    # Add generator and storage with matching base name
    gen = PLEXOSGenerator(name="AmistadDamPower_1_ERC_1_Turbine")
    storage = PLEXOSStorage(name="AmistadDamPower_1_ERC_1_Reservoir_head")
    target_system.add_component(gen)
    target_system.add_component(storage)

    ensure_head_storage_generator_membership(context)

    memberships = list(target_system.get_supplemental_attributes(PLEXOSMembership))
    assert any(
        m.parent_object == gen and m.child_object == storage and m.collection == CollectionEnum.HeadStorage
        for m in memberships
    ), "HeadStorage membership should be created for matching base names"


def test_ensure_tail_storage_generator_membership_matches_base_name():
    """Test that ensure_tail_storage_generator_membership matches base names correctly."""
    from plexosdb.enums import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSMembership, PLEXOSStorage
    from r2x_sienna_to_plexos.getters_utils import ensure_tail_storage_generator_membership

    from r2x_core import System, TranslationContext

    # Setup systems
    target_system = System(name="target")
    context = TranslationContext(
        source_system=None,
        target_system=target_system,
        config=None,
        rules=[],
    )

    # Add generator and storage with matching base name
    gen = PLEXOSGenerator(name="AmistadDamPower_1_ERC_1_Turbine")
    storage = PLEXOSStorage(name="AmistadDamPower_1_ERC_1_Reservoir_tail")
    target_system.add_component(gen)
    target_system.add_component(storage)

    ensure_tail_storage_generator_membership(context)

    memberships = list(target_system.get_supplemental_attributes(PLEXOSMembership))
    assert any(
        m.parent_object == gen and m.child_object == storage and m.collection == CollectionEnum.TailStorage
        for m in memberships
    ), "TailStorage membership should be created for matching base names"


def test_get_storage_initial_level_returns_value():
    from r2x_sienna_to_plexos.getters import get_storage_initial_level

    from r2x_core import TranslationContext

    class DummyReservoir:
        initial_level = 42.5

    context = TranslationContext(source_system=None, target_system=None, rules=[])
    result = get_storage_initial_level(context, DummyReservoir())
    assert result.is_ok()
    assert result.unwrap() == 42.5


def test_get_storage_initial_level_returns_default():
    from r2x_sienna_to_plexos.getters import get_storage_initial_level

    from r2x_core import TranslationContext

    class DummyReservoir:
        pass

    context = TranslationContext(source_system=None, target_system=None, rules=[])
    result = get_storage_initial_level(context, DummyReservoir())
    assert result.is_ok()
    assert result.unwrap() == 0.0


def test_get_storage_max_level_returns_value():
    from r2x_sienna.models import MinMax
    from r2x_sienna_to_plexos.getters import get_storage_max_volume

    from r2x_core import TranslationContext

    class DummyReservoir:
        storage_level_limits = MinMax(min=0.0, max=123.4)

    context = TranslationContext(source_system=None, target_system=None, rules=[])
    result = get_storage_max_volume(context, DummyReservoir())
    assert result.is_ok()
    assert result.unwrap() == 123.4


def test_get_storage_max_level_returns_default():
    from r2x_sienna_to_plexos.getters import get_storage_max_volume

    from r2x_core import TranslationContext

    class DummyReservoir:
        pass

    context = TranslationContext(source_system=None, target_system=None, rules=[])
    result = get_storage_max_volume(context, DummyReservoir())
    assert result.is_ok()
    assert result.unwrap() == 0.0
