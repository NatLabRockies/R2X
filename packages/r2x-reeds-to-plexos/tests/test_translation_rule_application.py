"""Translation rule application tests for ReEDS-to-PLEXOS."""

from __future__ import annotations

import json
from importlib.resources import files

from r2x_core import DataStore, PluginConfig, PluginContext, Rule, System, apply_rules_to_context


def make_context_and_rules(tmp_path):
    rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))
    config = PluginConfig(models=("r2x_reeds.models", "r2x_plexos.models", "r2x_reeds_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    context = PluginContext(config=config, store=store)
    return context, rules


def test_reeds_region_translates_to_node(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSNode
    from r2x_reeds.models import ReEDSRegion

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(ReEDSRegion(name="R_TEST", transmission_region="Z1"))
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    nodes = list(context.target_system.get_components(PLEXOSNode))
    assert len(nodes) == 1
    node = nodes[0]
    assert node.name == "R_TEST"
    assert node.voltage in (0.0, 115.0, 230.0, 345.0, 500.0) or isinstance(node.voltage, float)
    assert hasattr(node, "load")


def test_reeds_region_translates_to_zone(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSZone
    from r2x_reeds.models import ReEDSRegion

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(ReEDSRegion(name="p42", transmission_region="Z42"))
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    zones = list(context.target_system.get_components(PLEXOSZone))
    assert len(zones) == 1
    zone = zones[0]
    assert zone.name == "Z42"


def test_reeds_generators_translate_to_plexos_types(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSNode
    from r2x_reeds.models import (
        ReEDSHydroGenerator,
        ReEDSRegion,
        ReEDSThermalGenerator,
        ReEDSVariableGenerator,
    )

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", transmission_region="Z1")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSThermalGenerator(
            name="THERM1",
            region=region,
            technology="gas-cc",
            capacity=100.0,
            heat_rate=7.5,
            fuel_type="gas",
        )
    )
    context.source_system.add_component(
        ReEDSVariableGenerator(
            name="VRE1",
            region=region,
            technology="wind-ons",
            capacity=50.0,
        )
    )
    context.source_system.add_component(
        ReEDSHydroGenerator(
            name="HYDRO1",
            region=region,
            technology="hydro",
            capacity=25.0,
            is_dispatchable=True,
            ramp_rate=10.0,
        )
    )
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    nodes = list(context.target_system.get_components(PLEXOSNode))
    assert len(nodes) == 1

    generators = list(context.target_system.get_components(PLEXOSGenerator))
    names = {g.name for g in generators}
    assert {"THERM1", "VRE1", "HYDRO1"} <= names


def test_reeds_storage_translates_to_plexos_storage(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator
    from r2x_reeds.models import ReEDSRegion, ReEDSStorage

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", transmission_region="Z1")
    context.source_system.add_component(region)
    storage = ReEDSStorage(
        name="BATT1",
        region=region,
        technology="battery",
        capacity=50.0,
        storage_duration=4.0,
        round_trip_efficiency=0.85,
    )
    context.source_system.add_component(storage)
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    storages = []
    for cls in (
        PLEXOSBattery,
        getattr(__import__("r2x_plexos.models", fromlist=["PLEXOSBattery"]), "PLEXOSBattery", None),
        PLEXOSGenerator,
    ):
        if cls is not None:
            storages.extend(list(context.target_system.get_components(cls)))
    storage = [s for s in storages if s.name in ("BATT1", "BATT1_head", "BATT1_tail")]
    assert storage


def test_reeds_interface_translates_to_plexos_interface(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSInterface
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region1 = ReEDSRegion(name="p1", transmission_region="Z1")
    region2 = ReEDSRegion(name="p2", transmission_region="Z2")
    context.source_system.add_component(region1)
    context.source_system.add_component(region2)
    context.source_system.add_component(
        ReEDSInterface(name="IFACE_1_2", from_region=region1, to_region=region2)
    )
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    interfaces = list(context.target_system.get_components(PLEXOSInterface))
    assert len(interfaces) == 1
    iface = interfaces[0]
    assert iface.name == "Z1_Z2-IFACE_1_2"
    assert iface.category == "reeds-interface"


def test_reeds_reserve_translates_to_plexos_reserve(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSReserve
    from r2x_reeds.models import ReEDSReserve

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(
        ReEDSReserve(
            name="REG_UP",
            reserve_type="REGULATION",
            direction="Up",
            duration=3600.0,
        )
    )

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    reserves = list(context.target_system.get_components(PLEXOSReserve))
    assert len(reserves) == 1
    reserve = reserves[0]
    assert reserve.name == "REG_UP"
    assert reserve.duration == 3600.0


def test_reeds_transmission_line_translates_to_plexos_line(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSLine
    from r2x_reeds.models import FromTo_ToFrom, ReEDSInterface, ReEDSRegion, ReEDSTransmissionLine

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region1 = ReEDSRegion(name="p1", transmission_region="Z1")
    region2 = ReEDSRegion(name="p2", transmission_region="Z2")
    context.source_system.add_component(region1)
    context.source_system.add_component(region2)
    interface = ReEDSInterface(name="IFACE", from_region=region1, to_region=region2)
    context.source_system.add_component(interface)
    line1 = ReEDSTransmissionLine(
        name="LINE_1_2", interface=interface, max_active_power=FromTo_ToFrom(from_to=150.0, to_from=150.0)
    )
    context.source_system.add_component(line1)

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    lines = list(context.target_system.get_components(PLEXOSLine))
    assert len(lines) == 1
    line = lines[0]
    assert line.name == "LINE_1_2"
    assert hasattr(line, "min_flow")
    assert hasattr(line, "max_flow")


def test_multiple_regions_create_multiple_nodes_and_zones(tmp_path) -> None:
    from r2x_plexos.models import PLEXOSNode, PLEXOSZone
    from r2x_reeds.models import ReEDSRegion

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(ReEDSRegion(name="p1", transmission_region="Z1"))
    context.source_system.add_component(ReEDSRegion(name="p2", transmission_region="Z2"))
    context.source_system.add_component(ReEDSRegion(name="p3", transmission_region="Z3"))
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    nodes = list(context.target_system.get_components(PLEXOSNode))
    zones = list(context.target_system.get_components(PLEXOSZone))

    assert len(nodes) == 3
    assert len(zones) == 3

    node_names = {node.name for node in nodes}
    zone_names = {zone.name for zone in zones}

    assert node_names == {"p1", "p2", "p3"}
    assert zone_names == {"Z1", "Z2", "Z3"}
