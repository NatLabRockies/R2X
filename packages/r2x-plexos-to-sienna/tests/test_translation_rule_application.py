"""Translation rule application tests for PLEXOS-to-Sienna."""

from __future__ import annotations

import json
from importlib.resources import files

import pytest

from r2x_core import DataStore, PluginConfig, PluginContext, Rule, System, apply_rules_to_context


def make_context_and_rules(tmp_path):
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))
    config = PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models", "r2x_plexos_to_sienna.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    context = PluginContext(config=config, store=store)
    return context, rules


def test_plexos_zone_translates_to_load_zone(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSZone
    from r2x_sienna.models import LoadZone

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(PLEXOSZone(name="ZONE1"))
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    zones = list(context.target_system.get_components(LoadZone))
    assert len(zones) == 1
    zone = zones[0]
    assert zone.name == "ZONE1"
    assert zone.peak_active_power == 0.0
    assert zone.peak_reactive_power == 0.0


def test_plexos_node_translates_to_acbus(tmp_path) -> None:
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSRegion
    from r2x_sienna.models import ACBus
    from r2x_sienna.models.enums import ACBusTypes

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)

    node = PLEXOSNode(name="NODE_123", voltage=115.0, is_slack_bus=0)
    context.source_system.add_component(node)
    region = PLEXOSRegion(name="REGION1", load=100.0)
    context.source_system.add_component(region)
    membership = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node,
        child_object=region,
    )
    context.source_system.add_supplemental_attribute(region, membership)
    context.source_system.add_supplemental_attribute(node, membership)

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    buses = list(context.target_system.get_components(ACBus))
    assert len(buses) >= 1

    bus = next((b for b in buses if b.name == "NODE_123"), None)
    assert bus is not None
    assert bus.number == 123
    assert bus.base_voltage.magnitude == 115.0
    assert bus.bustype == ACBusTypes.PQ


def test_plexos_region_translates_to_area(tmp_path) -> None:
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSRegion
    from r2x_sienna.models import Area

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)

    node = PLEXOSNode(name="NODE1", voltage=115.0)
    context.source_system.add_component(node)
    region = PLEXOSRegion(name="REGION1", load=300.0)
    context.source_system.add_component(region)
    membership = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node,
        child_object=region,
    )
    context.source_system.add_supplemental_attribute(region, membership)
    context.source_system.add_supplemental_attribute(node, membership)

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    areas = list(context.target_system.get_components(Area))
    assert len(areas) == 1
    area = areas[0]
    assert area.name == "REGION1"
    assert area.peak_active_power == 300.0
    assert area.load_response == 0.0


def test_plexos_region_translates_to_power_load(tmp_path) -> None:
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSRegion
    from r2x_sienna.models import PowerLoad

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)

    node = PLEXOSNode(name="NODE1", voltage=115.0)
    context.source_system.add_component(node)
    region = PLEXOSRegion(name="REGION1", load=250.0)
    context.source_system.add_component(region)
    membership = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node,
        child_object=region,
    )
    context.source_system.add_supplemental_attribute(region, membership)
    context.source_system.add_supplemental_attribute(node, membership)

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    loads = list(context.target_system.get_components(PowerLoad))
    assert len(loads) >= 1

    load = loads[0]
    assert load.name == "REGION1"
    assert load.active_power.magnitude == 250.0
    assert load.bus is not None
    assert load.bus.name == "NODE1"


def test_plexos_generators_translate_to_sienna_types(tmp_path) -> None:
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSMembership, PLEXOSNode, PLEXOSRegion
    from r2x_sienna.models import (
        HydroDispatch,
        RenewableDispatch,
        RenewableNonDispatch,
        ThermalStandard,
    )

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)

    node = PLEXOSNode(name="NODE1", voltage=115.0)
    context.source_system.add_component(node)
    region = PLEXOSRegion(name="REGION1", load=100.0)
    context.source_system.add_component(region)
    membership = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node,
        child_object=region,
    )
    context.source_system.add_supplemental_attribute(region, membership)
    context.source_system.add_supplemental_attribute(node, membership)

    therm = PLEXOSGenerator(
        name="THERM1",
        category="gas-cc",
        max_capacity=100.0,
        units=1,
    )
    context.source_system.add_component(therm)
    hydro = PLEXOSGenerator(
        name="HYDRO1",
        category="hydro-dispatch",
        max_capacity=50.0,
        units=1,
    )
    context.source_system.add_component(hydro)
    wind = PLEXOSGenerator(
        name="WIND1",
        category="wind-ons",
        max_capacity=75.0,
        units=1,
    )
    context.source_system.add_component(wind)
    pv = PLEXOSGenerator(
        name="PV1",
        category="distpv",
        max_capacity=25.0,
        units=1,
    )
    context.source_system.add_component(pv)

    for gen in [therm, hydro, wind, pv]:
        gen_membership = PLEXOSMembership(
            collection=CollectionEnum.Nodes,
            parent_object=gen,
            child_object=node,
        )
        context.source_system.add_supplemental_attribute(gen, gen_membership)
        context.source_system.add_supplemental_attribute(node, gen_membership)

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    thermals = list(context.target_system.get_components(ThermalStandard))
    assert len(thermals) >= 1
    thermal = next((t for t in thermals if t.name == "THERM1"), None)
    assert thermal is not None
    assert thermal.rating == 0.0
    assert thermal.bus is not None
    assert thermal.bus.name == "NODE1"

    hydros = list(context.target_system.get_components(HydroDispatch))
    assert len(hydros) >= 1
    hydro_gen = next((h for h in hydros if h.name == "HYDRO1"), None)
    assert hydro_gen is not None
    assert hydro_gen.rating == 0.0
    assert hydro_gen.bus is not None
    assert hydro_gen.bus.name == "NODE1"

    renewables = list(context.target_system.get_components(RenewableDispatch))
    assert len(renewables) >= 1
    wind_gen = next((r for r in renewables if r.name == "WIND1"), None)
    assert wind_gen is not None
    assert wind_gen.rating == 0.0
    assert wind_gen.bus is not None
    assert wind_gen.bus.name == "NODE1"

    non_dispatch = list(context.target_system.get_components(RenewableNonDispatch))
    assert len(non_dispatch) >= 1
    pv_gen = next((r for r in non_dispatch if r.name == "PV1"), None)
    assert pv_gen is not None
    assert pv_gen.rating == 0.0
    assert pv_gen.bus is not None
    assert pv_gen.bus.name == "NODE1"


def test_plexos_battery_translates_to_energy_reservoir(tmp_path) -> None:
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSBattery, PLEXOSMembership, PLEXOSNode, PLEXOSRegion
    from r2x_sienna.models import EnergyReservoirStorage

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)

    node = PLEXOSNode(name="NODE1", voltage=115.0)
    context.source_system.add_component(node)
    region = PLEXOSRegion(name="REGION1", load=100.0)
    context.source_system.add_component(region)
    region_membership = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node,
        child_object=region,
    )
    context.source_system.add_supplemental_attribute(region, region_membership)
    context.source_system.add_supplemental_attribute(node, region_membership)

    battery = PLEXOSBattery(
        name="BATT1",
        category="battery",
        initial_soc=0.5,
    )
    context.source_system.add_component(battery)
    battery_membership = PLEXOSMembership(
        collection=CollectionEnum.Nodes,
        parent_object=battery,
        child_object=node,
    )
    context.source_system.add_supplemental_attribute(battery, battery_membership)
    context.source_system.add_supplemental_attribute(node, battery_membership)

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    storages = list(context.target_system.get_components(EnergyReservoirStorage))
    assert len(storages) >= 1
    storage = storages[0]
    assert storage.name == "BATT1"
    assert storage.storage_capacity == 0.0
    assert pytest.approx(0.5) == storage.initial_storage_capacity_level
    assert storage.bus is not None
    assert storage.bus.name == "NODE1"


def test_plexos_reserve_translates_to_variable_reserve(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSReserve
    from r2x_sienna.models import VariableReserve

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(
        PLEXOSReserve(
            name="SPIN_RES",
            timeframe=300.0,
            duration=3600.0,
        )
    )
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    reserves = list(context.target_system.get_components(VariableReserve))
    assert len(reserves) == 1
    reserve = reserves[0]
    assert reserve.name == "SPIN_RES"
    assert reserve.requirement == 0.0
    assert reserve.time_frame == 300.0


def test_plexos_interface_translates_to_transmission_interface(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSInterface
    from r2x_sienna.models import TransmissionInterface

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(PLEXOSInterface(name="IFACE1", min_flow=-200.0, max_flow=200.0))
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    interfaces = list(context.target_system.get_components(TransmissionInterface))
    assert len(interfaces) == 1
    interface = interfaces[0]
    assert interface.name == "IFACE1"
    assert interface.active_power_flow_limits.max == 200.0


def test_multiple_nodes_create_multiple_buses(tmp_path) -> None:
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSRegion
    from r2x_sienna.models import ACBus

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)

    node1 = PLEXOSNode(name="NODE_1", voltage=115.0)
    context.source_system.add_component(node1)
    node2 = PLEXOSNode(name="NODE_2", voltage=115.0)
    context.source_system.add_component(node2)
    node3 = PLEXOSNode(name="NODE_3", voltage=230.0)
    context.source_system.add_component(node3)
    region = PLEXOSRegion(name="REGION1", load=100.0)
    context.source_system.add_component(region)
    membership = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node1,
        child_object=region,
    )
    context.source_system.add_supplemental_attribute(region, membership)
    context.source_system.add_supplemental_attribute(node1, membership)

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    buses = list(context.target_system.get_components(ACBus))
    assert len(buses) >= 3

    bus_names = {bus.name for bus in buses}
    assert "NODE_1" in bus_names
    assert "NODE_2" in bus_names
    assert "NODE_3" in bus_names

    bus1 = next((b for b in buses if b.name == "NODE_1"), None)
    assert bus1 is not None
    assert bus1.base_voltage.magnitude == 115.0

    bus2 = next((b for b in buses if b.name == "NODE_2"), None)
    assert bus2 is not None
    assert bus2.base_voltage.magnitude == 115.0

    bus3 = next((b for b in buses if b.name == "NODE_3"), None)
    assert bus3 is not None
    assert bus3.base_voltage.magnitude == 230.0
