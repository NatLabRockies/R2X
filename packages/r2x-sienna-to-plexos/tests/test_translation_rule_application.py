"""Translation rule application tests for Sienna-to-PLEXOS."""

import json
import types
from importlib.resources import files

from r2x_sienna_to_plexos import translation as translation_module

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
    assert nodes[0].name == "A_TEST"


def test_sienna_generators_translate_to_plexos_types(tmp_path):
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSNode
    from r2x_sienna.models import ACBus, Area, HydroDispatch, RenewableDispatch, ThermalStandard
    from r2x_sienna.models.costs import HydroGenerationCost, RenewableGenerationCost, ThermalGenerationCost
    from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels
    from r2x_sienna.models.named_tuples import MinMax, UpDown

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(Area(name="A1"))

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)

    context.source_system.add_component(
        ThermalStandard(
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
    )

    context.source_system.add_component(
        RenewableDispatch(
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
    )

    context.source_system.add_component(
        HydroDispatch(
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
    )

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
    context.source_system.add_component(Area(name="A1"))

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    context.source_system.add_component(
        EnergyReservoirStorage(
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
    )
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
    context.source_system.add_component(Area(name="A1"))
    context.source_system.add_component(Area(name="A2"))
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
    assert interfaces[0].name == "A1_A2-IFACE_1_2"


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
    assert reserves[0].name == "REG_UP"
    assert reserves[0].duration == 3600.0


def test_sienna_transmission_line_translates_to_plexos_line(tmp_path):
    from r2x_plexos.models import PLEXOSLine
    from r2x_sienna.models import ACBus, Arc, Area, Line, TransmissionInterface
    from r2x_sienna.models.named_tuples import FromTo_ToFrom, MinMax

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(Area(name="A1"))
    context.source_system.add_component(Area(name="A2"))

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus3 = ACBus(name="N4", base_voltage=115.0, number=3)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus3)

    arc1 = Arc(from_to=bus1, to_from=bus3)
    context.source_system.add_component(arc1)
    context.source_system.add_component(
        TransmissionInterface(
            name="IFACE",
            active_power_flow_limits=MinMax(min=-150.0, max=150.0),
            direction_mapping={"line-01": 1, "line-02": -2},
        )
    )
    context.source_system.add_component(
        Line(
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
    )

    context.target_system = System(name="target", auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    lines = list(context.target_system.get_components(PLEXOSLine))
    assert len(lines) == 1
    assert lines[0].name == "LINE_1_2"
    assert hasattr(lines[0], "min_flow")
    assert hasattr(lines[0], "max_flow")


def test_sienna_to_plexos_executes_full_pipeline(monkeypatch, tmp_path):
    calls = []

    class FakeRulesPath:
        def read_text(self):
            return "[]"

    class FakeConfigDir:
        def __truediv__(self, _name):
            return FakeRulesPath()

    class FakeSystem:
        def __init__(self, name, auto_add_composed_components=True, time_series_manager=None):
            self.name = name
            self.auto_add_composed_components = auto_add_composed_components
            self.time_series_manager = time_series_manager

        def get_time_series_directory(self):
            return tmp_path

    def _mark(step_name):
        def _inner(_context):
            calls.append(step_name)

        return _inner

    monkeypatch.setattr(translation_module, "files", lambda _pkg: FakeConfigDir())
    monkeypatch.setattr(translation_module, "System", FakeSystem)
    monkeypatch.setattr(translation_module, "create_in_memory_db", lambda: object())
    monkeypatch.setattr(translation_module, "TimeSeriesManager", lambda *args, **kwargs: object())
    monkeypatch.setattr(translation_module.Rule, "from_records", lambda records: ["rule"])
    monkeypatch.setattr(translation_module, "apply_rules_to_context", lambda _ctx: calls.append("apply"))

    monkeypatch.setattr(translation_module, "ensure_generator_time_series", _mark("gen_ts"))
    monkeypatch.setattr(translation_module, "ensure_reserve_time_series", _mark("reserve_ts"))
    monkeypatch.setattr(translation_module, "ensure_region_node_memberships", _mark("region_node"))
    monkeypatch.setattr(translation_module, "ensure_generator_node_memberships", _mark("gen_node"))
    monkeypatch.setattr(translation_module, "ensure_battery_node_memberships", _mark("battery_node"))
    monkeypatch.setattr(translation_module, "ensure_reserve_battery_memberships", _mark("reserve_battery"))
    monkeypatch.setattr(translation_module, "ensure_reserve_generator_memberships", _mark("reserve_gen"))
    monkeypatch.setattr(translation_module, "ensure_transformer_node_memberships", _mark("trf_node"))
    monkeypatch.setattr(translation_module, "ensure_interface_line_memberships", _mark("iface_line"))
    monkeypatch.setattr(translation_module, "ensure_head_storage_generator_membership", _mark("head"))
    monkeypatch.setattr(translation_module, "ensure_tail_storage_generator_membership", _mark("tail"))

    source = FakeSystem(name="source")
    result = translation_module.sienna_to_plexos(source, config=types.SimpleNamespace())

    assert result.name == "PLEXOS"
    assert calls == [
        "apply",
        "gen_ts",
        "reserve_ts",
        "region_node",
        "gen_node",
        "battery_node",
        "reserve_battery",
        "reserve_gen",
        "trf_node",
        "iface_line",
        "head",
        "tail",
    ]


def test_fixture_coverage_context_rules_and_time_series(
    caplog,
    context_with_versioned_rules,
    context_with_bus_and_load,
    context_with_thermal_generators,
    rule_multifield,
    rule_with_all_features,
    rule_list_versioned,
    rules_from_config,
    vre_single_time_series,
    load_single_time_series,
    wind_single_time_series,
    hydro_single_time_series,
):
    assert caplog is not None
    assert context_with_versioned_rules.rules
    assert context_with_bus_and_load.source_system is not None
    assert context_with_thermal_generators.source_system is not None

    max_capacity_getter = rule_multifield.getters["Max Capacity"]
    comp = types.SimpleNamespace(rating=2.0, base_power=100.0)
    assert max_capacity_getter(None, comp).unwrap() == 200.0

    total_rating_getter = rule_with_all_features.getters["total_rating"]
    comp2 = types.SimpleNamespace(base_rating=80.0, premium_rating=20.0)
    assert total_rating_getter(None, comp2).unwrap() == 100.0

    assert {rule.version for rule in rule_list_versioned} == {1, 2}
    assert len(rules_from_config) > 0

    assert len(vre_single_time_series.data) == 24
    assert len(load_single_time_series.data) == 24
    assert len(wind_single_time_series.data) == 24
    assert len(hydro_single_time_series.data) == 24
