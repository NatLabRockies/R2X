"""End-to-end tests for the plexos_to_sienna translation entry point."""

from __future__ import annotations

import pytest
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSReserve,
    PLEXOSZone,
)
from r2x_plexos_to_sienna.plugin_config import PlexosToSiennaConfig
from r2x_plexos_to_sienna.translation import plexos_to_sienna
from r2x_sienna.models import (
    ACBus,
    Area,
    EnergyReservoirStorage,
    LoadZone,
    PowerLoad,
    ThermalStandard,
    TransmissionInterface,
    VariableReserve,
)

from r2x_core import System


def _build_source_system():
    """Build a minimal PLEXOS source system with topology and components."""
    source = System(name="plexos-source", auto_add_composed_components=True)

    node = PLEXOSNode(name="NODE1", voltage=115.0, is_slack_bus=0)
    source.add_component(node)

    region = PLEXOSRegion(name="REGION1", load=200.0)
    source.add_component(region)

    zone = PLEXOSZone(name="ZONE1")
    source.add_component(zone)

    # Region membership on node
    mem_region = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node,
        child_object=region,
    )
    source.add_supplemental_attribute(region, mem_region)
    source.add_supplemental_attribute(node, mem_region)

    # Generator with node membership
    gen = PLEXOSGenerator(name="GEN1", category="gas-cc", max_capacity=100.0, units=1)
    source.add_component(gen)
    mem_gen = PLEXOSMembership(collection=CollectionEnum.Nodes, parent_object=gen, child_object=node)
    source.add_supplemental_attribute(gen, mem_gen)
    source.add_supplemental_attribute(node, mem_gen)

    # Battery with node membership
    battery = PLEXOSBattery(name="BAT1", category="battery", initial_soc=0.5)
    source.add_component(battery)
    mem_bat = PLEXOSMembership(collection=CollectionEnum.Nodes, parent_object=battery, child_object=node)
    source.add_supplemental_attribute(battery, mem_bat)
    source.add_supplemental_attribute(node, mem_bat)

    # Reserve
    reserve = PLEXOSReserve(name="SPIN1", timeframe=300.0, duration=3600.0)
    source.add_component(reserve)

    # Interface
    interface = PLEXOSInterface(name="IF1", min_flow=-200.0, max_flow=200.0)
    source.add_component(interface)

    return source


def test_plexos_to_sienna_returns_system():
    source = _build_source_system()
    config = PlexosToSiennaConfig()
    result = plexos_to_sienna(source, config=config)

    assert isinstance(result, System)
    assert result.name == "Sienna"


def test_plexos_to_sienna_translates_zone():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    zones = list(result.get_components(LoadZone))
    assert len(zones) == 1
    assert zones[0].name == "ZONE1"


def test_plexos_to_sienna_translates_node_to_bus():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    buses = list(result.get_components(ACBus))
    assert any(b.name == "NODE1" for b in buses)

    bus = next(b for b in buses if b.name == "NODE1")
    assert bus.base_voltage.magnitude == 115.0


def test_plexos_to_sienna_translates_region_to_area():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    areas = list(result.get_components(Area))
    assert len(areas) == 1
    assert areas[0].name == "REGION1"
    assert areas[0].peak_active_power == 200.0


def test_plexos_to_sienna_translates_region_to_load():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    loads = list(result.get_components(PowerLoad))
    assert len(loads) >= 1
    load = next(ld for ld in loads if ld.name == "REGION1")
    assert load.active_power.magnitude == 200.0
    assert load.bus is not None
    assert load.bus.name == "NODE1"


def test_plexos_to_sienna_translates_generator():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    thermals = list(result.get_components(ThermalStandard))
    assert any(t.name == "GEN1" for t in thermals)

    gen = next(t for t in thermals if t.name == "GEN1")
    assert gen.bus is not None
    assert gen.bus.name == "NODE1"


def test_plexos_to_sienna_translates_battery():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    storages = list(result.get_components(EnergyReservoirStorage))
    assert any(s.name == "BAT1" for s in storages)

    bat = next(s for s in storages if s.name == "BAT1")
    assert pytest.approx(0.5) == bat.initial_storage_capacity_level
    assert bat.bus is not None
    assert bat.bus.name == "NODE1"


def test_plexos_to_sienna_translates_reserve():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    reserves = list(result.get_components(VariableReserve))
    assert len(reserves) == 1
    assert reserves[0].name == "SPIN1"
    assert reserves[0].time_frame == 300.0


def test_plexos_to_sienna_translates_interface():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    interfaces = list(result.get_components(TransmissionInterface))
    assert len(interfaces) == 1
    assert interfaces[0].name == "IF1"
    assert interfaces[0].active_power_flow_limits.max == 200.0
