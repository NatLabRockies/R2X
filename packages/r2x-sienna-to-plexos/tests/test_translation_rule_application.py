"""Translation rule application tests for Sienna-to-PLEXOS."""

import json
from importlib.resources import files

from r2x_core import DataStore, PluginConfig, PluginContext, Rule, System, apply_rules_to_context


def make_context_and_rules(tmp_path):
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))
    config = PluginConfig(models=("r2x_sienna.models", "r2x_plexos.models", "r2x_sienna_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    context = PluginContext(config=config, store=store)
    return context, rules


def test_sienna_area_translates_to_node(tmp_path):
    from r2x_plexos.models import PLEXOSNode
    from r2x_sienna.models import ACBus

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(ACBus(name="A_TEST", base_voltage=115.0, number=1))
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    nodes = list(context.target_system.get_components(PLEXOSNode))
    assert len(nodes) == 1
    node = nodes[0]
    assert node.name == "A_TEST"


def test_sienna_area_translates_to_zone(tmp_path):
    from r2x_plexos.models import PLEXOSZone
    from r2x_sienna.models import LoadZone

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(LoadZone(name="Z42"))
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    zones = list(context.target_system.get_components(PLEXOSZone))
    assert len(zones) == 1
    zone = zones[0]
    assert zone.name == "Z42"


def test_sienna_generators_translate_to_plexos_types(tmp_path):
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSNode
    from r2x_sienna.models import (
        ACBus,
        Area,
        HydroDispatch,
        RenewableDispatch,
        ThermalStandard,
    )
    from r2x_sienna.models.costs import HydroGenerationCost, RenewableGenerationCost, ThermalGenerationCost
    from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels
    from r2x_sienna.models.named_tuples import MinMax, UpDown

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    area = Area(name="A1")
    context.source_system.add_component(area)

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)

    thermal_gen_1 = ThermalStandard(
        name="THERM1",
        must_run=False,
        bus=bus1,
        status=False,
        base_power=100.0,
        rating=200.0,
        active_power=0.0,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0, max=1),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost.example(),
        time_at_status=1_000,
    )
    context.source_system.add_component(thermal_gen_1)

    ren_dist_1 = RenewableDispatch(
        name="VRE1",
        bus=ACBus.example(),
        base_power=100,
        rating=1,
        active_power=0.8,
        reactive_power=0.0,
        prime_mover_type=PrimeMoversType.PVe,
        power_factor=1.0,
        operation_cost=RenewableGenerationCost(),
    )
    context.source_system.add_component(ren_dist_1)

    hyd_dispatch_1 = HydroDispatch(
        name="HYDRO1",
        available=True,
        bus=ACBus.example(),
        active_power=80.0,
        reactive_power=0.0,
        rating=100.0,
        prime_mover_type=PrimeMoversType.HY,
        active_power_limits=MinMax(min=10.0, max=100.0),
        reactive_power_limits=MinMax(min=-30.0, max=30.0),
        ramp_limits=UpDown(up=5.0, down=5.0),
        time_limits=UpDown(up=1.0, down=1.0),
        base_power=100.0,
        status=True,
        time_at_status=24.0,
        operation_cost=HydroGenerationCost.example(),
        category="hydro",
    )
    context.source_system.add_component(hyd_dispatch_1)

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    nodes = list(context.target_system.get_components(PLEXOSNode))
    assert len(nodes) == 3

    generators = list(context.target_system.get_components(PLEXOSGenerator))
    names = {g.name for g in generators}
    assert {"VRE1", "HYDRO1"} <= names


def test_sienna_storage_translates_to_plexos_storage(tmp_path):
    from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator
    from r2x_sienna.models import ACBus, Area, EnergyReservoirStorage
    from r2x_sienna.models.enums import PrimeMoversType, StorageTechs
    from r2x_sienna.models.named_tuples import InputOutput, MinMax

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    area = Area(name="A1")
    context.source_system.add_component(area)

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)

    battery = EnergyReservoirStorage(
        name="battery",
        available=True,
        bus=bus1,
        prime_mover_type=PrimeMoversType.BA,
        storage_technology_type=StorageTechs.OTHER_CHEM,
        storage_capacity=1000.0,
        storage_level_limits=MinMax(min=0.1, max=0.9),
        initial_storage_capacity_level=0.5,
        rating=250.0,
        active_power=0.0,
        input_active_power_limits=MinMax(min=0.0, max=200.0),
        output_active_power_limits=MinMax(min=0.0, max=200.0),
        efficiency=InputOutput(input=0.95, output=0.95),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    context.source_system.add_component(battery)
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    storages = []
    for cls in (PLEXOSBattery, PLEXOSGenerator):
        storages.extend(list(context.target_system.get_components(cls)))
    storage = [s for s in storages if s.name in ("battery", "battery_head", "battery_tail")]
    assert storage


def test_sienna_interface_translates_to_plexos_interface(tmp_path):
    from r2x_plexos.models import PLEXOSInterface
    from r2x_sienna.models import Area, TransmissionInterface
    from r2x_sienna.models.named_tuples import MinMax

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    area1 = Area(name="A1")
    area2 = Area(name="A2")
    context.source_system.add_component(area1)
    context.source_system.add_component(area2)
    context.source_system.add_component(
        TransmissionInterface(
            name="A1_A2-IFACE_1_2",
            active_power_flow_limits=MinMax(min=-150.0, max=150.0),
            direction_mapping={"line-01": 1, "line-02": -2},
        )
    )
    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    interfaces = list(context.target_system.get_components(PLEXOSInterface))
    assert len(interfaces) == 1
    iface = interfaces[0]
    assert iface.name == "A1_A2-IFACE_1_2"


def test_sienna_reserve_translates_to_plexos_reserve(tmp_path):
    from r2x_plexos.models import PLEXOSReserve
    from r2x_sienna.models import VariableReserve

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(
        VariableReserve(
            name="REG_UP",
            reserve_type="REGULATION",
            direction="UP",
            duration=3600.0,
            requirement=100.0,
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


def test_sienna_transmission_line_translates_to_plexos_line(tmp_path):
    from r2x_plexos.models import PLEXOSLine
    from r2x_sienna.models import ACBus, Arc, Area, Line, TransmissionInterface
    from r2x_sienna.models.named_tuples import FromTo_ToFrom, MinMax

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    area1 = Area(name="A1")
    area2 = Area(name="A2")
    context.source_system.add_component(area1)
    context.source_system.add_component(area2)

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus3 = ACBus(name="N4", base_voltage=115.0, number=3)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus3)

    arc1 = Arc(from_to=bus1, to_from=bus3)
    context.source_system.add_component(arc1)

    interface = TransmissionInterface(
        name="IFACE",
        active_power_flow_limits=MinMax(min=-150.0, max=150.0),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    context.source_system.add_component(interface)
    line1 = Line(
        name="LINE_1_2",
        rating=100.0,
        r=0.01,
        x=0.1,
        arc=arc1,
        b=FromTo_ToFrom(from_to=0.0, to_from=0.0),
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
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


def test_multiple_areas_create_multiple_nodes_and_zones(tmp_path):
    from r2x_plexos.models import PLEXOSNode, PLEXOSZone
    from r2x_sienna.models import ACBus, LoadZone

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(LoadZone(name="A1"))
    context.source_system.add_component(LoadZone(name="A2"))
    context.source_system.add_component(LoadZone(name="A3"))

    context.source_system.add_component(ACBus(name="A1", base_voltage=115.0, number=1))
    context.source_system.add_component(ACBus(name="A2", base_voltage=115.0, number=2))
    context.source_system.add_component(ACBus(name="A3", base_voltage=115.0, number=3))
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

    assert node_names == {"A1", "A2", "A3"}
    assert zone_names == {"A1", "A2", "A3"}
