"""Direct getter coverage tests for Sienna-to-PLEXOS."""

from __future__ import annotations

import types
from datetime import datetime, timedelta
from typing import ClassVar

import pytest
from r2x_plexos.models import (
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSRegion,
)
from r2x_sienna.models import (
    ACBus,
    Area,
    EnergyReservoirStorage,
    HydroReservoir,
    HydroTurbine,
    Line,
    LoadZone,
    MinMax,
    PowerLoad,
    ThermalStandard,
    Transformer2W,
    TransmissionInterface,
    UpDown,
    VariableReserve,
)
from r2x_sienna.models.costs import (
    HydroGenerationCost,
    ThermalGenerationCost,
)
from r2x_sienna.models.enums import (
    HydroTurbineType,
    PrimeMoversType,
    ThermalFuels,
)
from r2x_sienna_to_plexos import getters

from r2x_core import DataStore, PluginConfig, PluginContext, System

from .fixtures.five_bus_systems import (
    system_complete,
    system_with_5_buses,
    system_with_hydro,
    system_with_loads,
    system_with_network,
    system_with_renewables,
    system_with_reserves,
    system_with_storage,
    system_with_thermal_generators,
    system_with_zones,
)


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


def _make_thermal_generator_for_category_tests(
    name: str,
    fuel: ThermalFuels | str,
    prime_mover_type: PrimeMoversType = PrimeMoversType.CC,
) -> ThermalStandard:
    return ThermalStandard(
        name=name,
        bus=None,
        active_power=0.0,
        reactive_power=0.0,
        rating=100.0,
        base_power=10.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        active_power_limits=MinMax(min=10.0, max=100.0),
        ramp_limits=UpDown(up=10.0, down=10.0),
        time_limits=UpDown(up=1.0, down=1.0),
        prime_mover_type=prime_mover_type,
        fuel=fuel,
        operation_cost=ThermalGenerationCost.example(),
    )


def _disable_time_series(sys):
    sys.add_time_series = lambda *args, **kwargs: None
    return sys


def _build_to_5_buses():
    sys = system_with_zones.__wrapped__()
    return system_with_5_buses.__wrapped__(sys)


def _build_to_loads():
    sys = _build_to_5_buses()
    _disable_time_series(sys)
    return system_with_loads.__wrapped__(sys, object())


def _build_to_thermal():
    sys = _build_to_loads()
    return system_with_thermal_generators.__wrapped__(sys)


def _build_to_renewables():
    sys = _build_to_thermal()
    _disable_time_series(sys)
    return system_with_renewables.__wrapped__(sys, object())


def _build_to_hydro():
    sys = _build_to_renewables()
    return system_with_hydro.__wrapped__(sys)


def _build_to_storage():
    sys = _build_to_hydro()
    return system_with_storage.__wrapped__(sys)


def _build_to_network():
    sys = _build_to_storage()
    return system_with_network.__wrapped__(sys)


def _build_to_reserves():
    sys = _build_to_network()
    return system_with_reserves.__wrapped__(sys)


def test_system_with_zones_builds_base_system():
    sys = system_with_zones.__wrapped__()

    assert sys.name == "c_sys_5bus"
    assert sys.base_power == 100.0

    zones = list(sys.get_components(LoadZone))
    areas = list(sys.get_components(Area))
    assert len(zones) == 1
    assert zones[0].name == "Zone-1"
    assert len(areas) == 1
    assert areas[0].name == "Area-1"


def test_system_with_5_buses_adds_expected_buses():
    sys = _build_to_5_buses()
    buses = list(sys.get_components(ACBus))

    assert len(buses) == 5
    assert {b.name for b in buses} == {f"Bus-{i}" for i in range(1, 6)}
    assert {b.number for b in buses} == {1, 2, 3, 4, 5}
    assert all(getattr(b.base_voltage, "magnitude", b.base_voltage) == 138.0 for b in buses)


def test_system_with_loads_adds_two_power_loads():
    sys = _build_to_loads()
    loads = list(sys.get_components(PowerLoad))

    assert len(loads) == 2
    by_name = {ld.name: ld for ld in loads}
    assert {"Load-1", "Load-2"} <= set(by_name)
    assert by_name["Load-1"].bus.name == "Bus-1"
    assert by_name["Load-2"].bus.name == "Bus-2"
    assert by_name["Load-1"].max_active_power.magnitude == 100.0
    assert by_name["Load-2"].max_active_power.magnitude == 200.0


def test_system_with_thermal_generators_adds_five_units():
    sys = _build_to_thermal()
    thermal = list(sys.get_components(ThermalStandard))
    names = {g.name for g in thermal}

    assert len(thermal) == 5
    assert {
        "thermal-coal",
        "thermal-gas-1",
        "thermal-gas-2",
        "thermal-quad",
        "thermal-markup",
    } <= names


def test_system_with_renewables_adds_three_units():
    from r2x_sienna.models import RenewableDispatch

    sys = _build_to_renewables()
    renewables = list(sys.get_components(RenewableDispatch))
    names = {r.name for r in renewables}

    assert len(renewables) == 3
    assert {"solar-1", "solar-2", "wind-1"} <= names


def test_system_with_hydro_adds_dispatch_turbine_and_reservoir():
    from r2x_sienna.models import HydroDispatch, HydroTurbine

    sys = _build_to_hydro()

    assert len(list(sys.get_components(HydroDispatch))) >= 1
    assert len(list(sys.get_components(HydroTurbine))) >= 1
    assert len(list(sys.get_components(HydroReservoir))) >= 1


def test_system_with_storage_adds_battery_on_bus_5():
    sys = _build_to_storage()
    storages = list(sys.get_components(EnergyReservoirStorage))

    assert len(storages) >= 1
    assert any(getattr(s, "bus", None) is not None and s.bus.name == "Bus-5" for s in storages)


def test_system_with_network_adds_lines_and_transformer():
    sys = _build_to_network()
    lines = list(sys.get_components(Line))
    transformers = list(sys.get_components(Transformer2W))

    assert len(lines) == 4
    assert {ln.name for ln in lines} == {"line-1-2", "line-2-3", "line-3-4", "line-4-5"}
    assert len(transformers) == 1
    assert transformers[0].name == "transformer-1-5"


def test_system_with_reserves_adds_two_variable_reserves():
    sys = _build_to_reserves()
    reserves = list(sys.get_components(VariableReserve))
    names = {r.name for r in reserves}

    assert len(reserves) == 2
    assert {"spin-reserve", "flex-reserve"} <= names


def test_system_complete_returns_same_system_instance():
    sys = _build_to_reserves()
    result = system_complete.__wrapped__(sys)
    assert result is sys


def test_attach_generator_time_series_scales_and_attaches(tmp_path, monkeypatch):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    source_gen = types.SimpleNamespace(name="GEN_TS", active_power_limits={"max": 10.0}, base_power=1.0)
    monkeypatch.setattr(getters, "_lookup_source_generator", lambda _ctx, _name: source_gen)
    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={}),
        types.SimpleNamespace(name="missing", features={}),
    ]
    context.source_system.list_time_series = lambda _component, **kwargs: (
        [
            types.SimpleNamespace(
                name="max_active_power",
                data=[0.1, 0.2],
                initial_timestamp=datetime(2020, 1, 1),
                resolution=timedelta(hours=1),
            )
        ]
        if kwargs.get("name") == "max_active_power"
        else []
    )
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    attached = []
    context.target_system.add_time_series = lambda ts, *_args, **_kwargs: attached.append(ts)

    getters._attach_generator_time_series(context, "GEN_TS", PLEXOSGenerator(name="GEN_TS"))

    assert len(attached) == 1
    assert attached[0].name == "max_active_power"
    assert list(attached[0].data) == [1.0, 2.0]


def test_attach_region_node_load_time_series_aggregates_loads(tmp_path, monkeypatch):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    bus1 = types.SimpleNamespace(uuid="bus-1")
    bus2 = types.SimpleNamespace(uuid="bus-2")
    load1 = types.SimpleNamespace(name="L1")
    load2 = types.SimpleNamespace(name="L2")

    monkeypatch.setattr(getters, "_build_area_buses_index", lambda _ctx: {"R1": [bus1, bus2]})
    monkeypatch.setattr(
        getters, "_build_bus_to_loads_index", lambda _ctx: {"bus-1": [load1], "bus-2": [load2]}
    )
    monkeypatch.setattr(getters, "_get_load_mw", lambda load: 10.0 if load is load1 else 20.0)

    context.source_system.time_series.has_time_series = lambda _load: True
    context.source_system.list_time_series = lambda load: [
        types.SimpleNamespace(
            name="max_active_power",
            data=[0.1, 0.2],
            initial_timestamp=datetime(2020, 1, 1),
            resolution=timedelta(hours=1),
        ),
    ]
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    attached = []
    context.target_system.add_time_series = lambda ts, *_args, **_kwargs: attached.append(ts)

    getters._attach_region_node_load_time_series(
        context=context,
        region_name="R1",
        node=PLEXOSNode(name="N1"),
        region_component=PLEXOSRegion(name="R1"),
    )

    assert len(attached) == 1
    assert attached[0].name == "load"
    assert list(attached[0].data) == [3.0, 6.0]


def test_attach_generator_time_series_uses_rating_when_limits_missing(tmp_path, monkeypatch):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    source_gen = types.SimpleNamespace(
        name="GEN_RATING", active_power_limits=None, rating=5.0, base_power=2.0
    )
    monkeypatch.setattr(getters, "_lookup_source_generator", lambda _ctx, _name: source_gen)
    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = lambda _component, **_kwargs: [
        types.SimpleNamespace(
            name="max_active_power",
            data=[0.1, 0.2],
            initial_timestamp=datetime(2020, 1, 1),
            resolution=timedelta(hours=1),
        )
    ]
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    attached = []
    context.target_system.add_time_series = lambda ts, *_args, **_kwargs: attached.append(ts)

    getters._attach_generator_time_series(context, "GEN_RATING", PLEXOSGenerator(name="GEN_RATING"))

    assert list(attached[0].data) == [1.0, 2.0]


def test_resolve_generator_category_zonal2nodal_uses_reeds_defaults(monkeypatch, context):
    comp = types.SimpleNamespace(name="zonal2nodal_natural-gas_cluster", ext={})
    monkeypatch.setattr(
        getters,
        "_get_defaults_data",
        lambda _ctx: {"reeds_defaults": {"gas": {}, "natural-gas": {}, "wind-ons": {}}},
    )

    assert getters._resolve_generator_category(comp, context) == "natural-gas"


def test_get_reeds_thermal_category_returns_none_for_non_list_mapping_values(monkeypatch, context):
    gen = _make_thermal_generator_for_category_tests(
        name="thermal-natgas",
        fuel=ThermalFuels.NATURAL_GAS,
    )
    monkeypatch.setattr(
        getters,
        "_get_defaults_data",
        lambda _ctx: {"reeds_thermal_mapping": {"natural-gas": "NATURAL_GAS", "coal": ["COAL"]}},
    )

    assert getters._get_reeds_thermal_category_from_fuel(gen, context) is None


def test_get_reservoir_location_helper_priority_order():
    by_name = types.SimpleNamespace(name="Plant_HEAD")
    by_attr = types.SimpleNamespace(name="Plant", reservoir_location="tail")
    by_ext = types.SimpleNamespace(name="Plant", ext={"RESERVOIR_LOCATION": "head"})
    unknown = types.SimpleNamespace(name="Plant")

    assert getters._get_reservoir_location(by_name) == "HEAD"
    assert getters._get_reservoir_location(by_attr) == "TAIL"
    assert getters._get_reservoir_location(by_ext) == "HEAD"
    assert getters._get_reservoir_location(unknown) is None


def test_has_explicit_side_reservoir_for_base_detects_matching_side(monkeypatch, context):
    current = types.SimpleNamespace(name="Plant", ext={"plant_name": "Plant"}, uuid="1")
    explicit_head = types.SimpleNamespace(name="Plant_head", ext={"plant_name": "Plant"}, uuid="2")

    other_plant = types.SimpleNamespace(name="Other_head", ext={"plant_name": "Other"}, uuid="3")

    fake_source = types.SimpleNamespace(get_components=lambda _cls: [current, explicit_head, other_plant])
    monkeypatch.setattr(getters, "_source_system", lambda _ctx: fake_source)

    assert getters._has_explicit_side_reservoir_for_base(current, context, side="HEAD") is True
    assert getters._has_explicit_side_reservoir_for_base(current, context, side="TAIL") is False


def test_membership_component_child_node_err_when_source_generator_has_no_bus(context):
    source_gen = _make_thermal_generator_for_category_tests(
        name="gen-without-bus",
        fuel=ThermalFuels.NATURAL_GAS,
    )
    context.source_system.add_component(source_gen)

    result = getters.membership_component_child_node(PLEXOSGenerator(name="gen-without-bus"), context)
    assert result.is_err()
    assert "missing bus data" in str(result.err())


def test_membership_interface_child_line_success_via_monkeypatched_index(monkeypatch, context):
    target_line = PLEXOSLine(name="line-01")
    context.target_system.add_component(target_line)

    source_interface = types.SimpleNamespace(name="IFACE-1", lines=[types.SimpleNamespace(name="line-01")])
    monkeypatch.setattr(
        getters, "_build_source_interface_name_index", lambda _ctx: {"IFACE-1": source_interface}
    )

    result = getters.membership_interface_child_line(types.SimpleNamespace(name="IFACE-1"), context)
    assert result.is_ok()
    assert result.unwrap() == target_line


def test_membership_line_parent_interface_success_and_missing_target(context):
    from r2x_plexos.models import PLEXOSInterface

    source_interface = TransmissionInterface(
        name="Interface-1",
        active_power_flow_limits=MinMax(min=-100.0, max=100.0),
        direction_mapping={"line-01": 1},
    )
    context.source_system.add_component(source_interface)

    line = PLEXOSLine(name="line-01")

    missing_target = getters.membership_line_parent_interface(line, context)
    assert missing_target.is_err()

    target_interface = PLEXOSInterface(name="Interface-1")
    context.target_system.add_component(target_interface)
    context._cache.pop("target_interface_name_index", None)

    result = getters.membership_line_parent_interface(line, context)
    assert result.is_ok()
    assert result.unwrap().name == "Interface-1"


def test_get_hydro_generator_units_always_online(context):
    from r2x_sienna.models import HydroDispatch

    bus = ACBus(name="BUS1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus)
    hydro = HydroDispatch(
        name="HD1",
        bus=bus,
        rating=100.0,
        active_power=50.0,
        reactive_power=10.0,
        base_power=100.0,
        prime_mover_type=PrimeMoversType.HY,
        ramp_limits=UpDown(up=5.0, down=5.0),
        active_power_limits=MinMax(min=0.0, max=100.0),
        operation_cost=HydroGenerationCost.example(),
    )
    assert getters.get_hydro_generator_units(hydro, context).unwrap() == 1


def _make_hydro_turbine_for_units_tests(bus: ACBus, name: str, rating: float) -> HydroTurbine:
    return HydroTurbine(
        name=name,
        available=True,
        bus=bus,
        active_power=0.0,
        reactive_power=0.0,
        rating=rating,
        active_power_limits=MinMax(min=0.0, max=100.0),
        reactive_power_limits=MinMax(min=-10.0, max=10.0),
        base_power=100.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=0.0,
        ramp_limits=UpDown(up=5.0, down=5.0),
        time_limits=UpDown(up=1.0, down=1.0),
        outflow_limits=MinMax(min=0.0, max=50.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )


def test_get_pumped_hydro_generator_units_zero_rating_is_online(context):
    """Turbine with zero rating has zero pump load → always online."""
    bus = ACBus(name="BUS_PH1", base_voltage=115.0, number=10)
    context.source_system.add_component(bus)
    ht = _make_hydro_turbine_for_units_tests(bus, "ht-zero-pump", rating=0.0)
    assert getters.get_pumped_hydro_generator_units(ht, context).unwrap() == 1


def test_get_pumped_hydro_generator_units_hydro_category_is_online(context):
    """Non-zero rating that resolves to 'hydro' category stays online."""
    bus = ACBus(name="BUS_PH2", base_voltage=115.0, number=11)
    context.source_system.add_component(bus)
    ht = _make_hydro_turbine_for_units_tests(bus, "ht-hydro-cat", rating=1.0)
    # Force category to "hydro" via gen_type_string
    ht.ext = {"gen_type_string": "hydro"}
    assert getters.get_pumped_hydro_generator_units(ht, context).unwrap() == 1


def test_get_pumped_hydro_generator_units_pumped_no_reservoir_is_offline(context, monkeypatch):
    """Pumped turbine not referenced by any reservoir → offline."""
    bus = ACBus(name="BUS_PH3", base_voltage=115.0, number=12)
    context.source_system.add_component(bus)
    ht = _make_hydro_turbine_for_units_tests(bus, "ht-no-reservoir", rating=1.0)
    # No gen_type_string → category is None → treated as pumped-hydro default
    # No HydroReservoir in source system → turbine_names is empty → Ok(0)
    monkeypatch.setattr(getters, "_resolve_generator_category", lambda _comp, _ctx: None)
    result = getters.get_pumped_hydro_generator_units(ht, context)
    assert result.unwrap() == 0


def test_get_pumped_hydro_generator_units_pumped_with_reservoir_is_online(context, monkeypatch):
    """Pumped turbine referenced by a storage-creating reservoir → online."""
    bus = ACBus(name="BUS_PH4", base_voltage=115.0, number=13)
    context.source_system.add_component(bus)
    ht = _make_hydro_turbine_for_units_tests(bus, "ht-with-reservoir", rating=1.0)
    monkeypatch.setattr(getters, "_resolve_generator_category", lambda _comp, _ctx: None)
    # Inject a non-empty turbine name set so the turbine is found
    context._cache["reservoir_pump_turbine_name_set"] = {"ht-with-reservoir"}
    result = getters.get_pumped_hydro_generator_units(ht, context)
    assert result.unwrap() == 1


def test_build_reservoir_pump_turbine_name_set_collects_ext_plants(context, monkeypatch):
    """_build_reservoir_pump_turbine_name_set returns turbine names from reservoir ext plants."""
    # Create a proxy reservoir whose ext["plants"] lists a turbine name, and whose
    # _reservoir_has_hydro_pumped_storage_association returns True.
    reservoir = types.SimpleNamespace(
        uuid="res-1",
        name="reservoir-1",
        upstream_turbines=[],
        downstream_turbines=[],
        ext={"plants": ["pump-turbine-A", "pump-turbine-B"]},
    )
    monkeypatch.setattr(
        getters,
        "_source_system",
        lambda _ctx: types.SimpleNamespace(get_components=lambda _cls: [reservoir]),
    )
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _res, _ctx: True,
    )
    # Clear cache so it is rebuilt
    context._cache.pop("reservoir_pump_turbine_name_set", None)
    names = getters._build_reservoir_pump_turbine_name_set(context)
    assert "pump-turbine-A" in names
    assert "pump-turbine-B" in names


def test_build_reservoir_pump_turbine_name_set_skips_non_storage_reservoirs(context, monkeypatch):
    """Reservoirs that fail the pump-storage association check are skipped."""
    reservoir = types.SimpleNamespace(
        uuid="res-2",
        name="reservoir-2",
        upstream_turbines=[],
        downstream_turbines=[],
        ext={"plants": ["should-not-appear"]},
    )
    monkeypatch.setattr(
        getters,
        "_source_system",
        lambda _ctx: types.SimpleNamespace(get_components=lambda _cls: [reservoir]),
    )
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _res, _ctx: False,
    )
    context._cache.pop("reservoir_pump_turbine_name_set", None)
    names = getters._build_reservoir_pump_turbine_name_set(context)
    assert "should-not-appear" not in names


def test_attach_generator_time_series_scales_hydro_budget(tmp_path, monkeypatch):
    """hydro_budget raw per-unit values must be multiplied by max_active_power."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    source_gen = types.SimpleNamespace(
        name="HYDRO_TS",
        active_power_limits={"max": 0.5},
        base_power=2.0,
    )
    monkeypatch.setattr(getters, "_lookup_source_generator", lambda _ctx, _name: source_gen)

    raw_values = [10.0, 20.0]  # raw per-unit; after *1.0 MW still 10, 20 MWh
    context.source_system.time_series.has_time_series = lambda _c: True
    context.source_system.time_series.list_time_series_metadata = lambda _c: [
        types.SimpleNamespace(name="hydro_budget", features={})
    ]
    context.source_system.list_time_series = lambda _c, **_kw: [
        types.SimpleNamespace(
            name="hydro_budget",
            data=raw_values,
            initial_timestamp=datetime(2020, 1, 1),
            # Use weekly resolution so the aggregation block is skipped (>=7 days)
            resolution=timedelta(weeks=1),
        )
    ]
    context.target_system.has_time_series = lambda *_a, **_kw: False
    attached = []
    context.target_system.add_time_series = lambda ts, *_a, **_kw: attached.append(ts)

    getters._attach_generator_time_series(context, "HYDRO_TS", PLEXOSGenerator(name="HYDRO_TS"))

    assert len(attached) == 1
    assert attached[0].name == "max_energy_week"
    # raw 10.0 * 1.0 MW = 10.0, raw 20.0 * 1.0 MW = 20.0
    assert list(attached[0].data) == [10.0, 20.0]


def test_attach_generator_time_series_scales_hydro_budget_hourly(tmp_path, monkeypatch):
    """hydro_budget with hourly resolution is scaled then aggregated into weekly sums."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # max_active_power = 0.1 pu * 10.0 MVA = 1.0 MW
    source_gen = types.SimpleNamespace(
        name="HYDRO_HOURLY",
        active_power_limits={"max": 0.1},
        base_power=10.0,
    )
    monkeypatch.setattr(getters, "_lookup_source_generator", lambda _ctx, _name: source_gen)

    # Two weeks of hourly data: all ones → raw weekly sum = 168; scaled = 168 * 1.0
    two_weeks_ones = [1.0] * 336
    context.source_system.time_series.has_time_series = lambda _c: True
    context.source_system.time_series.list_time_series_metadata = lambda _c: [
        types.SimpleNamespace(name="hydro_budget", features={})
    ]
    context.source_system.list_time_series = lambda _c, **_kw: [
        types.SimpleNamespace(
            name="hydro_budget",
            data=two_weeks_ones,
            initial_timestamp=datetime(2020, 1, 1),
            resolution=timedelta(hours=1),
        )
    ]
    context.target_system.has_time_series = lambda *_a, **_kw: False
    attached = []
    context.target_system.add_time_series = lambda ts, *_a, **_kw: attached.append(ts)

    getters._attach_generator_time_series(context, "HYDRO_HOURLY", PLEXOSGenerator(name="HYDRO_HOURLY"))

    assert len(attached) == 1
    ts = attached[0]
    assert ts.name == "max_energy_week"
    assert ts.resolution == timedelta(days=7)
    # Each weekly value = 168 * 1.0 (scaled) * 1.0 MW = 168.0 MWh
    assert all(abs(v - 168.0) < 1e-6 for v in ts.data)


def test__ramp_value_to_float_small_value():
    """Value <= 10 with no unit magnitude is scaled by base_power (lines 511-519)."""

    class Dummy:
        base_power = 100.0

    assert getters._ramp_value_to_float(Dummy(), 0.5) == pytest.approx(50.0)


def test__ramp_value_to_float_large_value():
    """Value > 10 is returned as-is (line 520)."""

    class Dummy:
        base_power = 100.0

    assert getters._ramp_value_to_float(Dummy(), 50.0) == pytest.approx(50.0)


def test__ramp_value_to_float_none_raw_value():
    """Non-numeric raw_value with no magnitude yields 0.0 (lines 514-515)."""

    class Dummy:
        base_power = 100.0

    assert getters._ramp_value_to_float(Dummy(), None) == 0.0


def test__get_minmax_value_key_missing():
    """val is None branch returns None (line 584)."""
    obj = types.SimpleNamespace(min=0.0)
    assert getters._get_minmax_value(obj, "max") is None


def test__get_minmax_value_plain_float_no_magnitude():
    """Plain float with no unit wrapper returns the float directly (line 588)."""
    obj = types.SimpleNamespace(max=150.0)
    assert getters._get_minmax_value(obj, "max") == pytest.approx(150.0)


def test__get_defaults_non_numeric_string(monkeypatch):
    """Non-convertible value in defaults.json falls back to 0.0 (lines 597-598)."""
    monkeypatch.setattr(
        getters,
        "_load_defaults_json",
        lambda: {"reeds_defaults": {"test-cat": {"test-key": "not_a_number"}}},
    )
    assert getters._get_defaults("test-cat", "test-key") == 0.0


def test__get_time_limit_dict_branch():
    """time_limits passed as dict uses .get() path (line 489)."""

    class Comp:
        time_limits: ClassVar[dict] = {"up": 4.0}
        ext = None

    assert getters._get_time_limit(Comp(), "up", None) == pytest.approx(4.0)


def test__has_usable_generator_time_series_exception_returns_true(context):
    """Exception during has_time_series introspection returns True (lines 742-744)."""

    class Dummy:
        pass

    def _raise(_c):
        raise RuntimeError("fail")

    context.source_system.time_series.has_time_series = _raise
    assert getters._has_usable_generator_time_series(Dummy(), context) is True


def test__coerce_scalar_uncoercible_object():
    """Object that cannot be coerced to float returns None (line 879)."""

    class Weird:
        def __float__(self):
            raise ValueError("nope")

    assert getters._coerce_scalar(Weird()) is None


def test__coerce_scalar_int_value():
    """Plain int input returns float (line 871)."""
    assert getters._coerce_scalar(7) == 7.0


def test__coerce_scalar_magnitude_attribute():
    """Object with numeric .magnitude attribute returns that value (lines 874-875)."""

    class WithMag:
        magnitude = 3.5

    assert getters._coerce_scalar(WithMag()) == pytest.approx(3.5)


def test__get_load_base_power_none():
    """base_power=None falls back to 100.0 (line 910)."""

    class Dummy:
        base_power = None

    assert getters._get_load_base_power(Dummy()) == pytest.approx(100.0)


def test__get_load_base_power_plain_float():
    """Plain float base_power is coerced via _coerce_scalar path."""

    class Dummy:
        base_power = 50.0

    assert getters._get_load_base_power(Dummy()) == pytest.approx(50.0)


def test__get_load_mw_plain_float_max_active_power():
    """Plain float max_active_power * base_power via magnitude_value path (line 950)."""

    class Dummy:
        base_power = 100.0
        max_active_power = 0.5

    assert getters._get_load_mw(Dummy()) == pytest.approx(50.0)


def test__get_load_mw_constant_active_power_fallback():
    """Falls through to constant_active_power attribute when max_active_power is None (lines 960-965)."""

    class Dummy:
        base_power = 100.0
        max_active_power = None
        max_constant_active_power = None
        constant_active_power = 0.8

    assert getters._get_load_mw(Dummy()) == pytest.approx(80.0)


def test__get_load_mw_all_none_returns_zero():
    """No usable power attribute returns 0.0 (line 969)."""

    class Dummy:
        base_power = 100.0
        max_active_power = None
        max_constant_active_power = None
        constant_active_power = None

    assert getters._get_load_mw(Dummy()) == 0.0


def test__compute_total_system_load_accumulates(context):
    """Iterates StandardLoad components and sums their MW contributions (lines 992-993)."""
    from r2x_sienna.models import StandardLoad

    # Mock out get_components so we avoid constructing a full StandardLoad
    dummy_load = types.SimpleNamespace(
        base_power=100.0,
        max_active_power=0.5,
        max_constant_active_power=None,
        constant_active_power=None,
    )
    original_get = context.source_system.get_components

    def mock_get(cls):
        if cls is StandardLoad:
            return [dummy_load]
        return original_get(cls)

    context.source_system.get_components = mock_get
    total = getters._compute_total_system_load(context)
    assert total == pytest.approx(50.0)


def test__find_3w_source_transformer_no_match(context):
    """Name with no recognized arm suffix returns None (line 869)."""
    assert getters._find_3w_source_transformer(context, "foo_unknown_suffix") is None


def test__build_source_interface_name_index_cache_hit(context):
    """Second call returns the same cached dict (line 216)."""
    first = getters._build_source_interface_name_index(context)
    second = getters._build_source_interface_name_index(context)
    assert first is second


def test__build_target_line_name_index_cache_hit(context):
    """Second call returns the same cached dict (line 228)."""
    first = getters._build_target_line_name_index(context)
    second = getters._build_target_line_name_index(context)
    assert first is second


def test__resolve_ramp_rates_huge_max_mw_uses_defaults(context, monkeypatch):
    """active_power_limits > 1e10 treated as sentinel; capacity defaults used (line 556)."""

    class Dummy:
        active_power_limits = types.SimpleNamespace(max=1e15)
        base_power = 1.0
        name = "dummy"
        ext = None
        prime_mover_type = None

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "natural-gas")
    result = getters._resolve_ramp_rates(
        Dummy(), context, initial_ramp_mw=0.0, defaults_key="max_ramp_up_percentage"
    )
    assert result >= 0.0


def test__resolve_ramp_rates_ramp_capped_by_defaults_when_exceeds_capacity(context, monkeypatch):
    """Ramp from defaults that exceeds capacity_MW is replaced by gen_ramp_pct * max_mw."""

    class Dummy:
        active_power_limits = None
        base_power = 1.0
        name = "dummy"
        ext = None
        prime_mover_type = None

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "natural-gas")

    def mock_get_defaults(cat, key):
        if key == "max_ramp_up_percentage":
            return 2.0  # 200% of capacity → 200 MW > 100 MW cap → default 2.0 * 100 = 200, capped to 100
        if key == "ramp_rate":
            return 0.0
        if key == "capacity_MW":
            return 100.0
        return 0.0

    monkeypatch.setattr(getters, "_get_defaults", mock_get_defaults)
    result = getters._resolve_ramp_rates(
        Dummy(), context, initial_ramp_mw=0.0, defaults_key="max_ramp_up_percentage"
    )
    # gen_ramp_pct=2.0, max_mw=100 → default_ramp=200 > 100 → capped to min(200, 100) = 100
    assert result == pytest.approx(100.0)


def test__resolve_ramp_rates_source_ramp_exceeds_max_capacity_uses_defaults(context, monkeypatch):
    """Source ramp > max_mw is physically impossible; replace with gen_ramp_pct * max_mw."""

    class Dummy:
        active_power_limits = MinMax(min=0.0, max=100.0)
        base_power = 1.0
        name = "dummy"
        ext = None
        prime_mover_type = None

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "coal")

    # source ramp = 500 MW/min, max_mw = 100 MW → physically impossible
    # coal ramp_rate = 0.2 → default_ramp = 0.2 * 100 = 20 MW/min
    result = getters._resolve_ramp_rates(
        Dummy(), context, initial_ramp_mw=500.0, defaults_key="max_ramp_up_percentage"
    )
    assert result == pytest.approx(20.0)


def test_get_reeds_thermal_category_not_thermal_returns_none(context):
    """Non-thermal component always returns None (covers line 119)."""
    result = getters._get_reeds_thermal_category_from_fuel(
        types.SimpleNamespace(name="gen", fuel=None), context
    )
    assert result is None


def test_get_zone_category_no_buses_returns_zones(context):
    """LoadZone with no buses has no ISO/RTO → category is 'zones'."""
    lz = LoadZone(name="ZoneNoData")
    context.source_system.add_component(lz)
    result = getters.get_zone_category(lz, context)
    assert result.is_ok()
    assert result.unwrap() == "zones"


def test_get_zone_category_with_buses_no_geo_returns_zones(context):
    """Buses with no geographic info still return 'zones' fallback."""
    lz = LoadZone(name="ZoneWithBus")
    bus = ACBus(name="B1", base_voltage=115.0, number=1, load_zone=lz)
    context.source_system.add_component(bus)  # auto_add_composed_components adds lz too

    result = getters.get_zone_category(lz, context)
    assert result.is_ok()
    # No geo coords → _resolve_iso_rto_for_buses returns None → category="zones"
    assert result.unwrap() == "zones"


def test_get_region_ext_basic_no_buses(context):
    """Basic call with no buses covers most of get_region_ext (lines 1071-1089)."""
    area = Area(name="TestArea")
    context.source_system.add_component(area)
    result = getters.get_region_ext(area, context)
    assert result.is_ok()
    val = result.unwrap()
    assert val["sienna_type"] == "StandardLoad"
    assert "description" not in val


def test_get_region_ext_arname_ext_and_iso_description(context, monkeypatch):
    """Covers ARNAME branch (line 1074) and iso_rto description path (line 1090)."""
    monkeypatch.setattr(
        getters,
        "_resolve_iso_rto_description_for_buses",
        lambda buses, ctx: "ercot",
    )
    area = Area(name="TestArea", ext={"ARNAME": "AR_TEST"})
    context.source_system.add_component(area)
    result = getters.get_region_ext(area, context)
    assert result.is_ok()
    val = result.unwrap()
    assert val.get("description") == "ISO/RTOs where region belongs to: ercot"
