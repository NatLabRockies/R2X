"""Tests for PLEXOS to Sienna component converters."""

import pytest
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSRegion,
)
from r2x_sienna.models import ACBus, Area, EnergyReservoirStorage, PowerLoad

from r2x.common.config import PLEXOSToSiennaConfig
from r2x.translations.plexos_to_sienna.converters import convert_component, post_process_component
from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings
from r2x_core import System


@pytest.fixture(autouse=True)
def setup_mappings():
    initialize_all_mappings()


@pytest.fixture
def config():
    return PLEXOSToSiennaConfig()


@pytest.fixture
def plexos_system():
    return System(name="plexos", auto_add_composed_components=True)


@pytest.fixture
def sienna_system():
    return System(name="sienna", auto_add_composed_components=True)


def test_convert_region_to_area(plexos_system, sienna_system, config):
    region = PLEXOSRegion(name="TestRegion")
    plexos_system.add_component(region)

    result = convert_component(region, plexos_system, sienna_system, config)

    assert result.is_ok()
    areas = list(sienna_system.get_components(Area))
    assert len(areas) == 1
    assert areas[0].name == "TestRegion"


def test_convert_node_to_bus(plexos_system, sienna_system, config):
    node = PLEXOSNode(name="TestNode", object_id=1)
    plexos_system.add_component(node)

    result = convert_component(node, plexos_system, sienna_system, config)

    assert result.is_ok()
    buses = list(sienna_system.get_components(ACBus))
    assert len(buses) == 1
    assert buses[0].name == "TestNode"


def test_convert_node_with_load(plexos_system, sienna_system, config):
    node = PLEXOSNode(name="LoadNode", object_id=1, load=100.0)
    plexos_system.add_component(node)

    result = convert_component(node, plexos_system, sienna_system, config)

    assert result.is_ok()
    loads = list(sienna_system.get_components(PowerLoad))
    assert len(loads) == 1
    assert "LoadNode_load" in loads[0].name


def test_convert_node_with_zero_load(plexos_system, sienna_system, config):
    node = PLEXOSNode(name="NoLoadNode", object_id=1, load=0.0)
    plexos_system.add_component(node)

    result = convert_component(node, plexos_system, sienna_system, config)

    assert result.is_ok()
    loads = list(sienna_system.get_components(PowerLoad))
    assert len(loads) == 0


def test_convert_generator_to_thermal(plexos_system, sienna_system, config):
    from plexosdb import CollectionEnum
    from r2x_sienna.models import ThermalStandard

    gen = PLEXOSGenerator(name="CoalGen", category="Coal", max_capacity=500.0, units=1)
    node = PLEXOSNode(name="GenNode", object_id=1)

    plexos_system.add_component(node)
    plexos_system.add_component(gen)

    membership = PLEXOSMembership(
        parent_object=gen,
        child_object=node,
        collection=CollectionEnum.Nodes,
    )
    plexos_system.add_supplemental_attribute(gen, membership)
    plexos_system.add_supplemental_attribute(node, membership)

    convert_component(node, plexos_system, sienna_system, config)

    result = convert_component(gen, plexos_system, sienna_system, config)

    assert result.is_ok()
    generators = list(sienna_system.get_components(ThermalStandard))
    assert len(generators) >= 1


def test_convert_generator_zero_capacity(plexos_system, sienna_system, config):
    from plexosdb import CollectionEnum

    gen = PLEXOSGenerator(name="ZeroGen", category="Coal", max_capacity=0.0, units=1)
    node = PLEXOSNode(name="GenNode", object_id=1)

    plexos_system.add_component(node)
    plexos_system.add_component(gen)

    membership = PLEXOSMembership(
        parent_object=gen,
        child_object=node,
        collection=CollectionEnum.Nodes,
    )
    plexos_system.add_supplemental_attribute(gen, membership)
    plexos_system.add_supplemental_attribute(node, membership)

    convert_component(node, plexos_system, sienna_system, config)

    result = convert_component(gen, plexos_system, sienna_system, config)

    assert result.is_ok()


def test_convert_generator_missing_category(plexos_system, sienna_system, config):
    gen = PLEXOSGenerator(name="NoCategory", category=None)
    plexos_system.add_component(gen)

    result = convert_component(gen, plexos_system, sienna_system, config)

    assert result.is_err()
    assert "missing category" in result.err().lower()


def test_convert_generator_unknown_category(plexos_system, sienna_system, config):
    from plexosdb import CollectionEnum

    gen = PLEXOSGenerator(name="UnknownGen", category="UnknownCategory")
    node = PLEXOSNode(name="GenNode", object_id=1)

    plexos_system.add_component(node)
    plexos_system.add_component(gen)

    membership = PLEXOSMembership(
        parent_object=gen,
        child_object=node,
        collection=CollectionEnum.Nodes,
    )
    plexos_system.add_supplemental_attribute(gen, membership)
    plexos_system.add_supplemental_attribute(node, membership)

    convert_component(node, plexos_system, sienna_system, config)

    result = convert_component(gen, plexos_system, sienna_system, config)

    assert result.is_err()
    assert "no mapping" in result.err().lower()


def test_convert_generator_not_connected(plexos_system, sienna_system, config):
    gen = PLEXOSGenerator(name="Orphan", category="Coal", max_capacity=100.0, units=1)
    plexos_system.add_component(gen)

    result = convert_component(gen, plexos_system, sienna_system, config)

    assert result.is_err()
    assert "not connected" in result.err().lower()


@pytest.mark.xfail(reason="Battery converter missing required EnergyReservoirStorage fields")
def test_convert_battery_to_storage(plexos_system, sienna_system, config):
    from plexosdb import CollectionEnum

    battery = PLEXOSBattery(
        name="Battery1",
        max_power=50.0,
        capacity=200.0,
        charge_efficiency=0.9,
        discharge_efficiency=0.95,
        units=1,
    )
    node = PLEXOSNode(name="BatteryNode", object_id=1)

    plexos_system.add_component(node)
    plexos_system.add_component(battery)

    membership = PLEXOSMembership(
        parent_object=battery,
        child_object=node,
        collection=CollectionEnum.Nodes,
    )
    plexos_system.add_supplemental_attribute(battery, membership)
    plexos_system.add_supplemental_attribute(node, membership)

    convert_component(node, plexos_system, sienna_system, config)

    result = convert_component(battery, plexos_system, sienna_system, config)

    assert result.is_ok()
    storages = list(sienna_system.get_components(EnergyReservoirStorage))
    assert len(storages) == 1
    assert storages[0].name == "Battery1"


def test_convert_battery_not_connected(plexos_system, sienna_system, config):
    battery = PLEXOSBattery(name="OrphanBattery")
    plexos_system.add_component(battery)

    result = convert_component(battery, plexos_system, sienna_system, config)

    assert result.is_err()
    assert "not connected" in result.err().lower()


def test_post_process_area_with_load(plexos_system, sienna_system, config):
    region = PLEXOSRegion(name="LoadRegion", object_id=1, load=150.0)
    plexos_system.add_component(region)

    area = Area(name="LoadRegion", ext={"object_id": 1})
    sienna_system.add_component(area)

    result = post_process_component(area, plexos_system, sienna_system, config)

    assert result.is_ok()
    buses = list(sienna_system.get_components(ACBus))
    loads = list(sienna_system.get_components(PowerLoad))

    assert len(buses) >= 1
    assert len(loads) >= 1


def test_post_process_area_without_load(plexos_system, sienna_system, config):
    region = PLEXOSRegion(name="NoLoadRegion", object_id=1, load=0.0)
    plexos_system.add_component(region)

    area = Area(name="NoLoadRegion", ext={"object_id": 1})
    sienna_system.add_component(area)

    result = post_process_component(area, plexos_system, sienna_system, config)

    assert result.is_ok()
    buses = list(sienna_system.get_components(ACBus))
    assert len(buses) == 0


def test_post_process_non_area_component(plexos_system, sienna_system, config):
    from r2x_sienna.units import ureg

    bus = ACBus(name="TestBus", number=1, base_voltage=110.0 * ureg.kV)
    sienna_system.add_component(bus)

    result = post_process_component(bus, plexos_system, sienna_system, config)

    assert result.is_ok()


def test_convert_node_already_exists(plexos_system, sienna_system, config):
    from r2x_sienna.units import ureg

    node = PLEXOSNode(name="DuplicateNode", object_id=1)
    plexos_system.add_component(node)

    bus = ACBus(name="DuplicateNode", number=1, base_voltage=110.0 * ureg.kV)
    sienna_system.add_component(bus)

    result = convert_component(node, plexos_system, sienna_system, config)

    assert result.is_ok()
    buses = list(sienna_system.get_components(ACBus))
    assert len(buses) == 1
