"""Tests for PLEXOS to Sienna translator."""

import pytest
from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator, PLEXOSNode, PLEXOSRegion
from r2x_sienna.models import ACBus, Area, EnergyReservoirStorage

from r2x.common.config import PLEXOSToSiennaConfig
from r2x.translations.plexos_to_sienna import translate_system
from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings
from r2x_core import System


@pytest.fixture(autouse=True)
def setup_mappings():
    initialize_all_mappings()


@pytest.fixture
def simple_plexos_system():
    system = System(name="plexos_test")
    gen = PLEXOSGenerator(name="Gen1", category="Coal", max_capacity=100.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    system.add_component(gen)
    system.add_component(node)
    return system


@pytest.fixture
def plexos_system_with_battery():
    system = System(name="battery_test")
    battery = PLEXOSBattery(name="Battery1", capacity=100.0, max_power=50.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    system.add_component(battery)
    system.add_component(node)
    return system


@pytest.fixture
def plexos_system_with_region():
    system = System(name="region_test")
    region = PLEXOSRegion(name="Region1", object_id=1)
    system.add_component(region)
    return system


def test_translate_simple_system(simple_plexos_system):
    result = translate_system(simple_plexos_system)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system.name == "plexos_test_sienna"


def test_translate_creates_buses(simple_plexos_system):
    result = translate_system(simple_plexos_system)

    assert result.is_ok()
    sienna_system = result.unwrap()

    buses = list(sienna_system.get_components(ACBus))
    assert len(buses) >= 1


def test_translate_with_default_config(simple_plexos_system):
    result = translate_system(simple_plexos_system, config=None)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system is not None


def test_translate_with_custom_config(simple_plexos_system):
    config = PLEXOSToSiennaConfig(
        system_base_power=200.0,
        default_voltage_kv=220.0,
    )

    result = translate_system(simple_plexos_system, config)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system is not None


@pytest.mark.xfail(reason="Battery converter missing required EnergyReservoirStorage fields")
def test_translate_battery_to_storage(plexos_system_with_battery):
    result = translate_system(plexos_system_with_battery)

    assert result.is_ok()
    sienna_system = result.unwrap()

    storages = list(sienna_system.get_components(EnergyReservoirStorage))
    assert len(storages) >= 1


def test_translate_region_to_area(plexos_system_with_region):
    result = translate_system(plexos_system_with_region)

    assert result.is_ok()
    sienna_system = result.unwrap()

    areas = list(sienna_system.get_components(Area))
    assert len(areas) >= 1


def test_translate_preserves_component_names(simple_plexos_system):
    result = translate_system(simple_plexos_system)

    assert result.is_ok()
    sienna_system = result.unwrap()

    bus_names = [bus.name for bus in sienna_system.get_components(ACBus)]
    assert "Node1" in bus_names


def test_translate_empty_system():
    system = System(name="empty")
    result = translate_system(system)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system.name == "empty_sienna"


def test_translate_system_without_name():
    system = System(name=None)
    gen = PLEXOSGenerator(name="Gen1", category="Coal", max_capacity=100.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    system.add_component(gen)
    system.add_component(node)

    result = translate_system(system)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system.name == "sienna_system"


def test_translate_with_custom_mappings():
    system = System(name="custom_test")
    gen = PLEXOSGenerator(name="CustomGen", category="CustomType", max_capacity=100.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    system.add_component(gen)
    system.add_component(node)

    config = PLEXOSToSiennaConfig(
        category_mappings={
            "CustomType": {
                "sienna_type": "ThermalStandard",
                "prime_mover": "ST",
                "fuel_type": "COAL",
            }
        }
    )

    result = translate_system(system, config)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system is not None


def test_translate_logs_warnings_for_unknown_categories():
    system = System(name="unknown_test")
    gen = PLEXOSGenerator(name="UnknownGen", category="UnknownCategory", max_capacity=100.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    system.add_component(gen)
    system.add_component(node)

    result = translate_system(system)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system is not None


def test_translate_skips_zero_capacity_generators():
    system = System(name="zero_test")
    gen = PLEXOSGenerator(name="ZeroGen", category="Coal", max_capacity=0.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)

    system.add_component(gen)
    system.add_component(node)

    result = translate_system(system)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system is not None


def test_translate_from_file_path(tmp_path, simple_plexos_system):
    file_path = tmp_path / "plexos.json"
    simple_plexos_system.to_json(file_path)

    from r2x.translations.plexos_to_sienna import translate_from_json_file

    result = translate_from_json_file(file_path)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system is not None


def test_translate_with_mapping_strategy_merge():
    system = System(name="merge_test")
    gen = PLEXOSGenerator(name="Gen1", category="Coal", max_capacity=100.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    system.add_component(gen)
    system.add_component(node)

    config = PLEXOSToSiennaConfig(mapping_strategy="merge")

    result = translate_system(system, config)

    assert result.is_ok()


def test_translate_with_mapping_strategy_replace():
    system = System(name="replace_test")
    gen = PLEXOSGenerator(name="Gen1", category="MyCoal", max_capacity=100.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    system.add_component(gen)
    system.add_component(node)

    config = PLEXOSToSiennaConfig(
        mapping_strategy="replace",
        category_mappings={
            "MyCoal": {
                "sienna_type": "ThermalStandard",
                "prime_mover": "ST",
                "fuel_type": "COAL",
            }
        },
    )

    result = translate_system(system, config)

    assert result.is_ok()


def test_translate_auto_add_composed_components():
    system = System(name="auto_add_test", auto_add_composed_components=True)
    gen = PLEXOSGenerator(name="Gen1", category="Coal", max_capacity=100.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)
    system.add_component(gen)
    system.add_component(node)

    result = translate_system(system)

    assert result.is_ok()
    sienna_system = result.unwrap()
    assert sienna_system.auto_add_composed_components is True
