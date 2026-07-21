"""Direct getter coverage tests for Sienna-to-PLEXOS."""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta

import pytest
from infrasys.value_curves import LinearCurve
from r2x_plexos.models import (
    PLEXOSGenerator,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSStorage,
)
from r2x_sienna.models import (
    ACBus,
    Arc,
    Area,
    EnergyReservoirStorage,
    HydroReservoir,
    Line,
    MinMax,
    PowerLoad,
    ThermalStandard,
    Transformer2W,
    TransmissionInterface,
    VariableReserve,
)
from r2x_sienna.models.costs import (
    HydroReservoirCost,
    ThermalGenerationCost,
)
from r2x_sienna.models.enums import (
    LoadConformity,
    PrimeMoversType,
    ReserveDirection,
    ReserveType,
    StorageTechs,
    ThermalFuels,
)
from r2x_sienna.models.named_tuples import Complex, FromTo_ToFrom, InputOutput
from r2x_sienna.units import ActivePower
from r2x_sienna_to_plexos import getters

from r2x_core import DataStore, PluginConfig, PluginContext, System


@pytest.fixture
def context(tmp_path):
    config = PluginConfig(models=("r2x_sienna.models", "r2x_plexos.models", "r2x_sienna_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ctx = PluginContext(config=config, store=store)
    ctx.source_system = System(name="source", auto_add_composed_components=True)
    ctx.target_system = System(name="target", auto_add_composed_components=True)
    return ctx


def make_context(tmp_path) -> PluginContext:
    config = PluginConfig(models=("r2x_sienna.models", "r2x_plexos.models", "r2x_sienna_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ctx = PluginContext(config=config, store=store)
    ctx.source_system = System(name="source", auto_add_composed_components=True)
    ctx.target_system = System(name="target", auto_add_composed_components=True)
    return ctx


def test__get_time_limit_ext(context):
    # ext-key fallback was intentionally removed; components with no time_limits return 0.0
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus2 = ACBus(name="N3", base_voltage=115.0, number=2)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)
    arc = Arc(from_to=bus1, to_from=bus2)
    context.source_system.add_component(arc)
    gen = Transformer2W(
        name="T1",
        arc=arc,
        primary_shunt=Complex(real=0.0, imag=0.0),
        rating=50.0,
        base_power=2.0,
        x=0.1,
        r=0.01,
    )
    gen.ext = {"NARIS_Min_Up_Time": 7.5}
    # No time_limits on Transformer2W and ext lookup is no longer supported.
    assert getters.get_min_up_time(gen, context).unwrap() == 0.0


def test__get_defaults(tmp_path):
    # Covers defaults.json fallback and error branch
    defaults_dir = tmp_path / "r2x_sienna_to_plexos" / "config"
    defaults_dir.mkdir(parents=True, exist_ok=True)
    defaults_path = defaults_dir / "defaults.json"
    defaults_path.write_text(json.dumps({"pcm_defaults": {"battery": {"forced_outage_rate": "bad"}}}))
    import importlib.resources

    importlib.resources.files = lambda pkg: defaults_dir
    assert getters._get_defaults("battery", "forced_outage_rate") == 0.02


def test__lookup_target_node_by_source_area_err(context):
    assert getters._lookup_target_node_by_source_area(context, "missing").is_err()


def test__lookup_source_generator_none(context):
    assert getters._lookup_source_generator(context, "missing") is None


def test__lookup_source_battery_none(context):
    assert getters._lookup_source_battery(context, "missing") is None


def test__lookup_target_node_by_name_err(context):
    assert getters._lookup_target_node_by_name(context, "missing").is_err()


def test__find_source_line_none(context):
    assert getters._find_source_line(context, "missing") is None


def test__find_source_transformer_none(context):
    assert getters._find_source_transformer(context, "missing") is None


def test__attach_generator_time_series_no_source(context):
    # Should log debug and return
    gen = PLEXOSGenerator(name="missing")
    getters._attach_generator_time_series(context, "missing", gen)


def test__attach_generator_time_series_weekly_hydro_budget_aggregation(context, monkeypatch):
    source_gen = types.SimpleNamespace(name="hydro_gen", active_power_limits=None, rating=None)
    metadata = types.SimpleNamespace(name="hydro_budget", features={})
    source_ts = types.SimpleNamespace(
        name="hydro_budget",
        data=[1.0] * 400,
        initial_timestamp=datetime(2025, 1, 1),
        resolution=timedelta(hours=1),
        features={},
    )

    monkeypatch.setattr(getters, "_lookup_source_generator", lambda *_args, **_kwargs: source_gen)
    monkeypatch.setattr(context.source_system.time_series, "has_time_series", lambda _component: True)
    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda _component: [metadata],
    )
    monkeypatch.setattr(
        context.source_system,
        "list_time_series",
        lambda _component, name=None, **_kwargs: [source_ts] if name == "hydro_budget" else [],
    )

    captured: list[object] = []
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    context.target_system.add_time_series = lambda ts, *_args, **_kwargs: captured.append(ts)

    getters._attach_generator_time_series(context, "hydro_gen", PLEXOSGenerator(name="hydro_gen"))

    assert len(captured) == 1
    attached = captured[0]
    assert attached.resolution == timedelta(days=7)
    assert list(attached.data) == [168.0, 168.0, 64.0]


def test__attach_generator_time_series_hydro_budget_keeps_hourly_when_single_bucket(context, monkeypatch):
    source_gen = types.SimpleNamespace(name="hydro_short", active_power_limits=None, rating=None)
    metadata = types.SimpleNamespace(name="hydro_budget", features={})
    source_ts = types.SimpleNamespace(
        name="hydro_budget",
        data=[2.0] * 100,
        initial_timestamp=datetime(2025, 1, 1),
        resolution=timedelta(hours=1),
        features={},
    )

    monkeypatch.setattr(getters, "_lookup_source_generator", lambda *_args, **_kwargs: source_gen)
    monkeypatch.setattr(context.source_system.time_series, "has_time_series", lambda _component: True)
    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda _component: [metadata],
    )
    monkeypatch.setattr(
        context.source_system,
        "list_time_series",
        lambda _component, name=None, **_kwargs: [source_ts] if name == "hydro_budget" else [],
    )

    captured: list[object] = []
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    context.target_system.add_time_series = lambda ts, *_args, **_kwargs: captured.append(ts)

    getters._attach_generator_time_series(context, "hydro_short", PLEXOSGenerator(name="hydro_short"))

    assert len(captured) == 1
    attached = captured[0]
    assert attached.resolution == timedelta(hours=1)
    assert len(attached.data) == 100
    assert float(attached.data[0]) == 2.0


def test__has_usable_generator_time_series_false_on_absent_series(context, monkeypatch):
    source_component = types.SimpleNamespace(name="g1")
    monkeypatch.setattr(context.source_system.time_series, "has_time_series", lambda _component: False)

    assert not getters._has_usable_generator_time_series(source_component, context)


def test__has_usable_generator_time_series_true_when_metadata_present(context, monkeypatch):
    """Metadata-only check: if metadata is registered the generator is considered usable
    (no data read is performed, so data-retrieval failures are irrelevant)."""
    source_component = types.SimpleNamespace(name="g2")
    metadata = types.SimpleNamespace(name="max_active_power", features={})

    monkeypatch.setattr(context.source_system.time_series, "has_time_series", lambda _component: True)
    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda _component: [metadata],
    )

    # list_time_series is never called by the optimised implementation.
    def raise_on_list(*_args, **_kwargs):
        raise RuntimeError("should not be reached")

    monkeypatch.setattr(context.source_system, "list_time_series", raise_on_list)

    assert getters._has_usable_generator_time_series(source_component, context)


def test__attach_reservoir_time_series_to_storage_no_source(context):
    # Should log warning and return
    storage = PLEXOSStorage(name="missing_head")
    getters._attach_reservoir_time_series_to_storage(context, "missing_head", storage)


def test__attach_region_node_load_time_series_no_buses(context):
    region = PLEXOSRegion(name="missing")
    node = PLEXOSNode(name="missing")
    getters._attach_region_node_load_time_series(context, "missing", node, region)


def test__attach_region_node_load_time_series_no_loads(context):
    area = Area(name="A1")
    context.source_system.add_component(area)
    bus = ACBus(name="A1", area=area, number=1)
    context.source_system.add_component(bus)
    region = PLEXOSRegion(name="A1")
    node = PLEXOSNode(name="A1")
    getters._attach_region_node_load_time_series(context, "A1", node, region)


def test_get_load_participation_factor_with_ext(context):
    acbus = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(acbus)
    sload = PowerLoad(
        name="ExampleLoad",
        bus=acbus,
        comformity=LoadConformity.CONFORMING,
        active_power=ActivePower(1000, "MW"),
    )
    sload.ext = {"MMWG_LPF": 5.0}
    context.source_system.add_component(sload)
    assert getters.get_load_participation_factor(acbus, context).unwrap() == 0.0


def test_get_susceptance_plain_float(context):
    bus1 = ACBus(name="N1", base_voltage=115.0, number=1)
    bus2 = ACBus(name="N2", base_voltage=115.0, number=2)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)

    arc = Arc(from_to=bus1, to_from=bus2)
    context.source_system.add_component(arc)
    t = Transformer2W(
        name="T1",
        arc=arc,
        primary_shunt=Complex(real=2.5, imag=0.0),
        rating=50.0,
        base_power=2.0,
        x=0.1,
        r=0.01,
    )
    assert getters.get_transformer_susceptance(t, context).unwrap() == 0.0


def test_get_line_min_max_flow_and_charging_susceptance_none(context):

    bus1 = ACBus(name="N1", base_voltage=115.0, number=1)
    bus2 = ACBus(name="N2", base_voltage=115.0, number=2)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)

    arc = Arc(from_to=bus1, to_from=bus2)
    context.source_system.add_component(arc)
    line = Line(
        name="L1",
        arc=arc,
        rating=100.0,
        r=0.01,
        x=0.1,
        b=FromTo_ToFrom(from_to=5.0, to_from=5.0),
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    assert getters.get_line_min_flow(line, context).unwrap() == -10000.0
    assert getters.get_line_max_flow(line, context).unwrap() == 10000.0


def test_get_power_or_standard_load_no_loads(context):
    acbus = ACBus(name="N1", base_voltage=115.0, number=1)
    assert getters.get_area_load(acbus, context).unwrap() == 0.0


def test_get_storage_max_volume_natural_inflow_none(context):

    hr = HydroReservoir(
        name="hydro1",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=0.8,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        operation_cost=HydroReservoirCost.example(),
        level_data_type="USABLE_VOLUME",
        category="hydro_reservoir",
    )

    hr.initial_level = 0.5
    hr.storage_level_limits = {"min": 0.0, "max": 1000.0}
    hr.inflow = 50.0
    assert getters.get_storage_max_volume(hr, context).unwrap() == 1.0

    # inflow None
    hr.initial_level = 0.5
    hr.storage_level_limits = {"min": 0.0, "max": 1000.0}
    hr.inflow = 0.0
    assert getters.get_storage_natural_inflow(hr, context).unwrap() == 0.0

    # All valid
    hr.initial_level = 500.0
    hr.storage_level_limits = {"min": 0.0, "max": 1000.0}
    hr.inflow = 123.0
    hr.operation_cost = HydroReservoirCost.example()
    assert getters.get_storage_max_volume(hr, context).unwrap() == 1.0
    assert getters.get_storage_natural_inflow(hr, context).unwrap() == 123.0


def test_get_min_stable_level_none(context):
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus)
    gen = ThermalStandard(
        name="thermal-standard-test",
        must_run=False,
        bus=bus,
        status=False,
        base_power=100.0,
        rating=1.0,
        active_power=0.0,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0, max=1),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost.example(),
        time_at_status=1_000,
    )
    assert getters.get_generator_min_stable_level(gen, context).unwrap() == 50.0


def test_reserve_getters(context):
    reserve = VariableReserve(
        name="SpinUp-pjm",
        reserve_type=ReserveType.SPINNING,
        vors=0.05,
        duration=36.0,
        load_risk=0.5,
        time_frame=3600,
        direction=ReserveDirection.UP,
        requirement=100.0,
    )

    assert getters.get_reserve_timeframe(reserve, context).unwrap() == 216000.0
    assert getters.get_reserve_duration(reserve, context).unwrap() == 3600.0
    assert getters.get_reserve_min_provision(reserve, context).unwrap() == 10000.0
    assert getters.get_reserve_type(reserve, context).unwrap() == 1
    assert getters.get_reserve_vors(reserve, context).unwrap() == 0.05

    reserve.reserve_type = ReserveType.FLEXIBILITY
    reserve.vors = 1000.0
    assert getters.get_reserve_type(reserve, context).unwrap() == 2
    assert getters.get_reserve_vors(reserve, context).unwrap() == 1000.0


def test_getters_none_and_defaults(context):
    class Dummy:
        rating = None
        base_power = 1.0
        efficiency = None
        forced_outage_rate = None
        maintenance_rate = None
        mean_time_to_repair = None

    d = Dummy()
    result = getters.get_max_capacity(d, context)
    assert result.is_err()
    assert getters.get_generator_load_subtracter(Dummy(), context).unwrap() == 0.0
    assert getters.get_generator_rating(d, context).unwrap() == 0.0
    assert getters.get_generator_vom_cost(Dummy(), context).unwrap() == 0.0
    assert getters.get_turbine_pump_load(d, context).unwrap() == 0.0
    assert getters.get_turbine_pump_efficiency(d, context).unwrap() == 89.0
    assert getters.get_generator_forced_outage_rate(d, context).unwrap() >= 0.0
    assert getters.get_generator_maintenance_rate(d, context).unwrap() >= 0.0
    assert getters.get_generator_mean_time_to_repair(d, context).unwrap() >= 0.0
    assert getters.get_generator_mean_time_to_repair(d, context).unwrap() >= 0.0
    result_up = getters.get_max_ramp_up(Dummy(), context).unwrap()
    assert result_up == 0.0
    result_down = getters.get_max_ramp_down(Dummy(), context).unwrap()
    assert result_down == 0.0


def test_thermal_standard_initial_none(context):
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus)
    gen = ThermalStandard(
        name="thermal-standard-1",
        must_run=False,
        bus=bus,
        status=False,
        base_power=100.0,
        rating=100.0,
        active_power=0.0,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.0, max=100.0),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost.example(),
        time_at_status=1000.0,
    )
    # CC + NATURAL_GAS resolves to "natural-gas" category; defaults apply when time_limits is None
    assert getters.get_min_up_time(gen, context).unwrap() == 6.0
    assert getters.get_min_down_time(gen, context).unwrap() == 8.0


def test_getters_none_costs_and_battery(context):
    class Dummy:
        operation_cost = None
        forced_outage_rate = None
        maintenance_rate = None
        mean_time_to_repair = None

    d = Dummy()
    assert getters.get_generator_start_cost(d, context).unwrap() == 0.0
    assert getters.get_generator_shutdown_cost(d, context).unwrap() == 0.0
    assert getters.get_fuel_price(d, context).unwrap() == 0.0
    assert getters.get_generator_vom_cost(Dummy(), context).unwrap() == 0.0
    assert getters.get_generator_forced_outage_rate(d, context).unwrap() >= 0.0
    assert getters.get_generator_maintenance_rate(d, context).unwrap() >= 0.0
    assert getters.get_generator_mean_time_to_repair(d, context).unwrap() >= 0.0


def test_get_storage_charge_and_discharge_efficiency_one(context):
    battery = EnergyReservoirStorage(
        name="BAT1",
        available=True,
        bus=ACBus(name="N1", base_voltage=115.0, number=1),
        prime_mover_type=PrimeMoversType.BA,
        storage_technology_type=StorageTechs.OTHER_CHEM,
        storage_capacity=1000.0,
        storage_level_limits=MinMax(min=0.1, max=0.9),
        initial_storage_capacity_level=0.5,
        rating=250.0,
        active_power=0.0,
        input_active_power_limits=MinMax(min=0.0, max=200.0),
        output_active_power_limits=MinMax(min=0.0, max=200.0),
        efficiency=InputOutput(input=1.0, output=1.0),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    assert getters.get_battery_charge_efficiency(battery, context).unwrap() == 100.0
    assert getters.get_battery_discharge_efficiency(battery, context).unwrap() == 100.0


def test_get_battery_cycles_none(context):
    class Dummy:
        cycle_limits = None

    assert getters.get_battery_cycles(Dummy(), context).unwrap() == 10000.0


def test_get_battery_max_power_none(context):
    class Dummy:
        output_active_power_limits = type("Limits", (), {"max": None})()
        base_power = 1.0

    assert getters.get_battery_max_power(Dummy(), context).unwrap() == 0.0


def test_get_battery_capacity_none(context):
    class Dummy:
        storage_capacity = None
        base_power = 1.0

    assert getters.get_battery_capacity(Dummy(), context).unwrap() == 200.0


def test_get_interface_min_flow_not_none(context):
    ti = TransmissionInterface(
        name="ExampleTransmissionInterface",
        active_power_flow_limits=MinMax(min=-100, max=100),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    assert getters.get_interface_min_flow(ti, context).unwrap() == -99999.0


def test_get_interface_max_flow_not_none(context):
    ti = TransmissionInterface(
        name="ExampleTransmissionInterface",
        active_power_flow_limits=MinMax(min=-100, max=100),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    assert getters.get_interface_max_flow(ti, context).unwrap() == 99999.0

