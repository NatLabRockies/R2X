"""Tests for PLEXOS to Sienna dry-run functionality."""

import pytest
from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator, PLEXOSLine, PLEXOSNode, PLEXOSRegion

from r2x.common.config import PLEXOSToSiennaConfig
from r2x.translations.plexos_to_sienna import dry_run
from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings
from r2x_core import System


@pytest.fixture(autouse=True)
def setup_mappings():
    initialize_all_mappings()


@pytest.fixture
def simple_system():
    system = System(name="dry_run_test")
    gen = PLEXOSGenerator(name="Gen1", category="Coal", max_capacity=100.0, units=1)
    system.add_component(gen)
    return system


@pytest.fixture
def system_with_multiple_components():
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership

    system = System(name="multi_test")

    gen1 = PLEXOSGenerator(name="Coal_Gen", category="Coal", max_capacity=100.0, units=1)
    gen2 = PLEXOSGenerator(name="Gas_Gen", category="Gas", max_capacity=150.0, units=1)
    battery = PLEXOSBattery(name="Battery1", capacity=100.0, max_power=50.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    region = PLEXOSRegion(name="Region1", object_id=2)

    system.add_component(gen1)
    system.add_component(gen2)
    system.add_component(battery)
    system.add_component(node)
    system.add_component(region)

    gen1_membership = PLEXOSMembership(parent_object=gen1, child_object=node, collection=CollectionEnum.Nodes)
    gen2_membership = PLEXOSMembership(parent_object=gen2, child_object=node, collection=CollectionEnum.Nodes)
    battery_membership = PLEXOSMembership(
        parent_object=battery, child_object=node, collection=CollectionEnum.Nodes
    )

    system.add_supplemental_attribute(gen1, gen1_membership)
    system.add_supplemental_attribute(node, gen1_membership)
    system.add_supplemental_attribute(gen2, gen2_membership)
    system.add_supplemental_attribute(node, gen2_membership)
    system.add_supplemental_attribute(battery, battery_membership)
    system.add_supplemental_attribute(node, battery_membership)

    return system


def test_dry_run_simple_system(simple_system):
    result = dry_run(simple_system)

    assert result.is_ok()
    preview = result.unwrap()
    assert len(preview.skipped_components) >= 1
    assert any("Gen1" in skip[1] for skip in preview.skipped_components)


def test_dry_run_shows_mappings_used(simple_system):
    result = dry_run(simple_system)

    assert result.is_ok()
    preview = result.unwrap()
    assert len(preview.skipped_components) >= 1


def test_dry_run_summary_format(simple_system):
    result = dry_run(simple_system)

    assert result.is_ok()
    preview = result.unwrap()
    summary = preview.summary()

    assert "Translation Preview" in summary
    assert "Skipped Components" in summary or "skipped" in summary.lower()


def test_dry_run_multiple_component_types(system_with_multiple_components):
    result = dry_run(system_with_multiple_components)

    assert result.is_ok()
    preview = result.unwrap()

    counts = preview.component_counts
    assert ("PLEXOSBattery", "EnergyReservoirStorage") in counts
    assert ("PLEXOSNode", "ACBus") in counts
    assert ("PLEXOSRegion", "Area") in counts
    assert len(counts) >= 3


def test_dry_run_skips_zero_capacity_generator():
    system = System(name="zero_cap_test")
    gen = PLEXOSGenerator(name="ZeroCap", category="Coal", max_capacity=0.0, units=1)
    system.add_component(gen)

    result = dry_run(system)

    assert result.is_ok()
    preview = result.unwrap()

    assert any("ZeroCap" in skip[1] for skip in preview.skipped_components)
    assert any("Zero capacity" in skip[2] for skip in preview.skipped_components)


def test_dry_run_skips_unknown_category():
    system = System(name="unknown_test")
    gen = PLEXOSGenerator(name="Unknown_Gen", category="UnknownCategory")
    system.add_component(gen)

    result = dry_run(system)

    assert result.is_ok()
    preview = result.unwrap()

    skipped_names = [skip[1] for skip in preview.skipped_components]
    assert "Unknown_Gen" in skipped_names


def test_dry_run_skips_missing_category():
    system = System(name="no_cat_test")
    gen = PLEXOSGenerator(name="No_Cat", category=None)
    system.add_component(gen)

    result = dry_run(system)

    assert result.is_ok()
    preview = result.unwrap()

    skipped_names = [skip[1] for skip in preview.skipped_components]
    assert "No_Cat" in skipped_names


def test_dry_run_with_custom_config(simple_system):
    config = PLEXOSToSiennaConfig(
        system_base_power=200.0,
        default_voltage_kv=220.0,
    )

    result = dry_run(simple_system, config=config)

    assert result.is_ok()
    preview = result.unwrap()
    assert preview.metadata["system_base_power"] == 200.0
    assert preview.metadata["default_voltage_kv"] == 220.0


def test_dry_run_from_file_path(tmp_path, simple_system):
    file_path = tmp_path / "system.json"
    simple_system.to_json(file_path)

    result = dry_run(str(file_path))

    assert result.is_ok()
    preview = result.unwrap()
    assert len(preview.skipped_components) > 0


def test_dry_run_to_dict(simple_system):
    result = dry_run(simple_system)

    assert result.is_ok()
    preview = result.unwrap()
    preview_dict = preview.to_dict()

    assert "component_counts" in preview_dict
    assert "skipped_components" in preview_dict
    assert "mappings_used" in preview_dict
    assert "total_components" in preview_dict
    assert "total_skipped" in preview_dict


def test_dry_run_node_with_load():
    system = System(name="node_load_test")
    node = PLEXOSNode(name="LoadNode", object_id=1, load=100.0)
    system.add_component(node)

    result = dry_run(system)

    assert result.is_ok()
    preview = result.unwrap()

    counts = preview.component_counts
    assert ("PLEXOSNode", "ACBus") in counts
    assert ("PLEXOSNode", "PowerLoad") in counts


def test_dry_run_region_with_load():
    system = System(name="region_load_test")
    region = PLEXOSRegion(name="LoadRegion", object_id=1, load=50.0)
    system.add_component(region)

    result = dry_run(system)

    assert result.is_ok()
    preview = result.unwrap()

    counts = preview.component_counts
    assert ("PLEXOSRegion", "Area") in counts
    assert ("PLEXOSRegion", "ACBus") in counts
    assert ("PLEXOSRegion", "PowerLoad") in counts


def test_dry_run_lines_become_interchanges():
    system = System(name="line_test")
    line = PLEXOSLine(name="Line1")
    system.add_component(line)

    result = dry_run(system)

    assert result.is_ok()
    preview = result.unwrap()

    counts = preview.component_counts
    assert ("PLEXOSLine", "AreaInterchange") in counts
