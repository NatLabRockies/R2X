"""Translation tests."""

from __future__ import annotations

import json
from importlib.resources import files

import pytest

from r2x_core import DataStore, PluginConfig, PluginContext, Rule, System, apply_rules_to_context


def make_context_and_rules(tmp_path):
    rules_path = files("r2x_reeds_to_sienna.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    context = PluginContext(config=config, store=store)
    return context, rules


def test_reeds_region_translates_to_area(tmp_path) -> None:
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import Area

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(
        ReEDSRegion(name="R_TEST", category="region-cat", max_active_power=123.0, interconnect="west")
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    areas = list(context.target_system.get_components(Area))
    assert len(areas) == 1
    area = areas[0]
    assert area.name == "R_TEST"
    assert area.category == "region-cat"
    assert pytest.approx(1.23) == area.peak_active_power
    assert pytest.approx(0.0) == area.peak_reactive_power
    assert pytest.approx(0.0) == area.load_response


def test_reeds_region_translates_to_acbus(tmp_path) -> None:
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import ACBus, Area

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(ReEDSRegion(name="p42", category="region"))
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    buses = list(context.target_system.get_components(ACBus))
    assert len(buses) == 1
    bus = buses[0]
    assert bus.name == "p42_BUS"
    assert bus.number == 42
    assert bus.base_voltage.magnitude == 115.0
    assert bus.magnitude == 1.0
    assert bus.angle == 0.0
    assert bus.available is True

    areas = list(context.target_system.get_components(Area))
    assert len(areas) == 1
    assert bus.area == areas[0]


def test_reeds_region_with_non_numeric_name(tmp_path) -> None:
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import ACBus

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(ReEDSRegion(name="otx", category="region"))
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    buses = list(context.target_system.get_components(ACBus))
    assert len(buses) == 1
    bus = buses[0]
    assert bus.name == "otx_BUS"
    assert bus.number >= 10000


def test_reeds_generators_translate_to_sienna_types(tmp_path) -> None:
    from r2x_reeds.models import ReEDSRegion, ReEDSThermalGenerator, ReEDSVariableGenerator
    from r2x_sienna.models import (
        ACBus,
        Area,
        RenewableDispatch,
        RenewableNonDispatch,
        ThermalStandard,
    )

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
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
        ReEDSVariableGenerator(
            name="DISTPV",
            region=region,
            technology="distpv",
            capacity=25.0,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    areas = list(context.target_system.get_components(Area))
    assert len(areas) == 1

    buses = list(context.target_system.get_components(ACBus))
    assert len(buses) == 1

    thermal_gens = list(context.target_system.get_components(ThermalStandard))
    vre_dispatch = list(context.target_system.get_components(RenewableDispatch))
    vre_nondispatch = list(context.target_system.get_components(RenewableNonDispatch))

    assert len(thermal_gens) == 1
    assert len(vre_dispatch) == 1
    assert len(vre_nondispatch) == 1

    thermal = thermal_gens[0]
    assert thermal.name == "THERM1"
    assert thermal.category == "gas-cc"
    assert thermal.rating == 1.0
    assert thermal.base_power == 100.0
    assert thermal.bus == buses[0]

    wind = vre_dispatch[0]
    assert wind.name == "VRE1"
    assert wind.category == "wind-ons"
    assert wind.rating == 1.0
    assert wind.base_power == 50.0
    assert wind.bus == buses[0]

    pv = vre_nondispatch[0]
    assert pv.name == "DISTPV"
    assert pv.category == "distpv"
    assert pv.rating == 1.0
    assert pv.base_power == 25.0
    assert pv.bus == buses[0]


def test_reeds_hydro_translates_by_operating_mode(tmp_path) -> None:
    from r2x_reeds.models import ReEDSHydroGenerator, ReEDSRegion
    from r2x_sienna.models import HydroDispatch, PrimeMoversType, RenewableNonDispatch

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSHydroGenerator(
            name="HYDRO_DISPATCH",
            region=region,
            technology="hydro",
            capacity=100.0,
            is_dispatchable=True,
            ramp_rate=10.0,
            vom_cost=1.02,
        )
    )
    context.source_system.add_component(
        ReEDSHydroGenerator(
            name="HYDRO_NONDISPATCH",
            region=region,
            technology="hydro",
            capacity=50.0,
            is_dispatchable=False,
            vom_cost=1.02,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    hydros = list(context.target_system.get_components(HydroDispatch))
    assert len(hydros) == 1

    hydro = hydros[0]
    assert hydro.name == "HYDRO_DISPATCH"
    assert hydro.category == "hydro"
    assert hydro.rating == 1.0
    assert hydro.base_power == 100.0
    assert hydro.active_power_limits.max == 1.0
    assert hydro.ramp_limits.up == pytest.approx(10.0 / 60.0)
    assert hydro.time_limits.up == 0.0
    assert hydro.time_limits.down == 0.0
    assert hydro.operation_cost.fixed == 0.0
    assert hydro.operation_cost.variable is not None
    assert hydro.operation_cost.variable.vom_cost.function_data.proportional_term == pytest.approx(1.02)

    nondispatchable_hydros = list(context.target_system.get_components(RenewableNonDispatch))
    assert len(nondispatchable_hydros) == 1

    nondispatchable_hydro = nondispatchable_hydros[0]
    assert nondispatchable_hydro.name == "HYDRO_NONDISPATCH"
    assert nondispatchable_hydro.category == "hydro"
    assert nondispatchable_hydro.rating == 1.0
    assert nondispatchable_hydro.base_power == 50.0
    assert nondispatchable_hydro.prime_mover_type == PrimeMoversType.HY
    assert nondispatchable_hydro.ext["reeds_vom_cost"] == pytest.approx(1.02)


def test_reeds_storage_translates_to_energy_reservoir(tmp_path) -> None:
    from r2x_reeds.models import ReEDSRegion, ReEDSStorage
    from r2x_sienna.models import EnergyReservoirStorage

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSStorage(
            name="BATT1",
            region=region,
            technology="battery_4",
            capacity=50.0,
            storage_duration=4.0,
            round_trip_efficiency=0.85,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    storages = list(context.target_system.get_components(EnergyReservoirStorage))
    assert len(storages) == 1

    storage = storages[0]
    assert storage.name == "BATT1"
    assert storage.category == "battery_4"
    assert storage.base_power == 50.0
    assert storage.rating == 1.0
    assert storage.storage_capacity == 4.0
    assert storage.input_active_power_limits.max == 1.0
    assert storage.output_active_power_limits.max == 1.0
    assert storage.efficiency.input == pytest.approx(0.85)
    assert storage.efficiency.output == pytest.approx(1.0)


def test_reeds_pumped_hydro_translates_to_turbine_and_reservoirs(tmp_path) -> None:
    from r2x_reeds.models import ReEDSRegion, ReEDSStorage
    from r2x_sienna.models import (
        EnergyReservoirStorage,
        HydroPumpTurbine,
        HydroReservoir,
        ReservoirDataType,
        ReservoirLocation,
    )

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSStorage(
            name="PSH1",
            region=region,
            technology="pumped-hydro",
            capacity=50.0,
            storage_duration=4.0,
            round_trip_efficiency=0.8,
            vom_cost=0.38,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    assert list(context.target_system.get_components(EnergyReservoirStorage)) == []

    turbines = list(context.target_system.get_components(HydroPumpTurbine))
    reservoirs = list(context.target_system.get_components(HydroReservoir))

    assert len(turbines) == 1
    assert len(reservoirs) == 2

    turbine = turbines[0]
    reservoirs_by_name = {reservoir.name: reservoir for reservoir in reservoirs}
    head = reservoirs_by_name["PSH1_head"]
    tail = reservoirs_by_name["PSH1_tail"]

    assert turbine.name == "PSH1"
    assert turbine.rating == 1.0
    assert turbine.base_power == 50.0
    assert turbine.active_power_limits.max == 1.0
    assert turbine.active_power_limits_pump.max == 1.0
    assert turbine.time_at_status == 0.0
    assert turbine.efficiency.turbine == 1.0
    assert turbine.efficiency.pump == 0.8
    assert turbine.operation_cost.fixed == 0.0
    assert turbine.operation_cost.variable is not None
    assert turbine.operation_cost.variable.vom_cost.function_data.proportional_term == 0.0
    assert turbine.ext["reeds_vom_cost"] == pytest.approx(0.38)

    assert head.storage_level_limits.max == 200.0
    assert tail.storage_level_limits.max == 200.0
    assert head.initial_level == 0.5
    assert tail.initial_level == 0.5
    assert head.level_data_type == ReservoirDataType.ENERGY
    assert tail.level_data_type == ReservoirDataType.ENERGY
    assert head.reservoir_location == ReservoirLocation.HEAD
    assert tail.reservoir_location == ReservoirLocation.TAIL
    assert head.downstream_turbines == [turbine]
    assert tail.upstream_turbines == [turbine]


def test_reeds_demand_translates_to_power_load(tmp_path) -> None:
    from r2x_reeds.models import ReEDSDemand, ReEDSRegion
    from r2x_sienna.models import PowerLoad

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSDemand(
            name="LOAD1",
            region=region,
            max_active_power=500.0,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    loads = list(context.target_system.get_components(PowerLoad))
    assert len(loads) == 1

    load = loads[0]
    assert load.name == "LOAD1"
    assert load.max_active_power.magnitude == 1.0
    assert load.base_power.magnitude == 500.0


def test_reeds_interface_translates_to_area_interchange(tmp_path) -> None:
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion
    from r2x_sienna.models import AreaInterchange

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region1 = ReEDSRegion(name="p1", category="region")
    region2 = ReEDSRegion(name="p2", category="region")
    context.source_system.add_component(region1)
    context.source_system.add_component(region2)
    context.source_system.add_component(
        ReEDSInterface(name="IFACE_1_2", from_region=region1, to_region=region2)
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    interchanges = list(context.target_system.get_components(AreaInterchange))
    assert len(interchanges) == 1

    interchange = interchanges[0]
    assert interchange.name == "IFACE_1_2"
    assert interchange.from_area.name == "p1"
    assert interchange.to_area.name == "p2"
    assert interchange.active_power_flow == 0.0


def test_reeds_reserve_translates_to_variable_reserve(tmp_path) -> None:
    from r2x_reeds.models import ReEDSReserve
    from r2x_sienna.models import VariableReserve

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(
        ReEDSReserve(
            name="REG_UP",
            reserve_type="REGULATION",
            direction="Up",
            time_frame=300.0,
            duration=3600.0,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    reserves = list(context.target_system.get_components(VariableReserve))
    assert len(reserves) == 1

    reserve = reserves[0]
    assert reserve.name == "REG_UP"
    assert reserve.requirement == 0.0
    assert reserve.time_frame == 300.0
    assert reserve.sustained_time == 3600.0
    assert reserve.max_output_fraction == 1.0
    assert reserve.deployed_fraction == 1.0


def test_reeds_ac_transmission_line_translates_to_monitored_line(tmp_path) -> None:
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion, ReEDSTransmissionLine
    from r2x_sienna.models import MonitoredLine

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region1 = ReEDSRegion(name="p1", category="region")
    region2 = ReEDSRegion(name="p2", category="region")
    context.source_system.add_component(region1)
    context.source_system.add_component(region2)
    interface = ReEDSInterface(name="IFACE", from_region=region1, to_region=region2)
    context.source_system.add_component(interface)
    context.source_system.add_component(
        ReEDSTransmissionLine(
            name="LINE_1_2",
            interface=interface,
            line_type="ac",
            max_active_power={"from_to": 125.0, "to_from": 150.0},
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    lines = list(context.target_system.get_components(MonitoredLine))
    assert len(lines) == 1

    line = lines[0]
    assert line.name == "LINE_1_2"
    assert line.rating == 1.5
    assert line.flow_limits.from_to == 1.5
    assert line.flow_limits.to_from == 1.25
    assert line.active_power_flow == 0.0
    assert line.rating_b is None
    assert line.rating_c is None
    assert line.r == 0.0
    assert line.x == 0.0
    assert line.angle_limits.min == -90.0
    assert line.angle_limits.max == 90.0
    assert line.arc is not None
    assert line.ext == {"reeds_line_type": "ac"}


def test_reeds_vsc_lcc_b2b_transmission_types_translate_to_generic_hvdc_lines(tmp_path) -> None:
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion, ReEDSTransmissionLine
    from r2x_sienna.models import Line, TwoTerminalGenericHVDCLine

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region1 = ReEDSRegion(name="p1", category="region")
    region2 = ReEDSRegion(name="p2", category="region")
    context.source_system.add_component(region1)
    context.source_system.add_component(region2)
    interface = ReEDSInterface(name="IFACE", from_region=region1, to_region=region2)
    context.source_system.add_component(interface)
    source_lines = {
        "VSC_1_2": {"line_type": "vsc", "losses": 0.025},
        "LCC_1_2": {"line_type": "lcc", "losses": 0.015},
        "B2B_1_2": {"line_type": "b2b", "losses": 0.010},
    }
    for name, attributes in source_lines.items():
        context.source_system.add_component(
            ReEDSTransmissionLine(
                name=name,
                interface=interface,
                max_active_power={"from_to": 125.0, "to_from": 150.0},
                **attributes,
            )
        )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    lines = list(context.target_system.get_components(TwoTerminalGenericHVDCLine))
    assert len(lines) == 3
    assert list(context.target_system.get_components(Line)) == []

    lines_by_name = {line.name: line for line in lines}
    assert lines_by_name.keys() == source_lines.keys()
    for name, attributes in source_lines.items():
        line = lines_by_name[name]
        assert line.active_power_flow == 0.0
        assert line.active_power_limits_from.min == -1.25
        assert line.active_power_limits_from.max == 1.5
        assert line.active_power_limits_to.min == -1.5
        assert line.active_power_limits_to.max == 1.25
        assert line.reactive_power_limits_from.min == 0.0
        assert line.reactive_power_limits_from.max == 0.0
        assert line.reactive_power_limits_to.min == 0.0
        assert line.reactive_power_limits_to.max == 0.0
        assert line.loss.function_data.proportional_term == attributes["losses"]
        assert line.loss.function_data.constant_term == 0.0
        assert line.arc is not None
        assert line.ext == {"reeds_line_type": attributes["line_type"]}


def test_multiple_regions_create_multiple_buses_and_areas(tmp_path) -> None:
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import ACBus, Area

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(ReEDSRegion(name="p1", category="region"))
    context.source_system.add_component(ReEDSRegion(name="p2", category="region"))
    context.source_system.add_component(ReEDSRegion(name="p3", category="region"))
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    areas = list(context.target_system.get_components(Area))
    buses = list(context.target_system.get_components(ACBus))

    assert len(areas) == 3
    assert len(buses) == 3

    area_names = {area.name for area in areas}
    bus_names = {bus.name for bus in buses}

    assert area_names == {"p1", "p2", "p3"}
    assert bus_names == {"p1_BUS", "p2_BUS", "p3_BUS"}


def test_reeds_hydro_has_hy_prime_mover(tmp_path) -> None:
    """Hydro generators must translate with PrimeMoversType.HY, not OT."""
    from r2x_reeds.models import ReEDSHydroGenerator, ReEDSRegion
    from r2x_sienna.models import HydroDispatch
    from r2x_sienna.models.enums import PrimeMoversType

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSHydroGenerator(
            name="HYDRO_PM",
            region=region,
            technology="hydro",
            capacity=80.0,
            is_dispatchable=True,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    apply_rules_to_context(context)

    hydros = list(context.target_system.get_components(HydroDispatch))
    assert len(hydros) == 1
    assert hydros[0].prime_mover_type == PrimeMoversType.HY


def test_reeds_hydro_has_reactive_power_limits(tmp_path) -> None:
    """Hydro generators must translate with zeroed reactive_power_limits (no reactive data from ReEDS)."""
    from r2x_reeds.models import ReEDSHydroGenerator, ReEDSRegion
    from r2x_sienna.models import HydroDispatch

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSHydroGenerator(
            name="HYDRO_RPL",
            region=region,
            technology="hydro",
            capacity=60.0,
            is_dispatchable=True,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    apply_rules_to_context(context)

    hydros = list(context.target_system.get_components(HydroDispatch))
    assert len(hydros) == 1
    hydro = hydros[0]
    assert hydro.reactive_power_limits is not None
    assert hydro.reactive_power_limits.min == pytest.approx(0.0)
    assert hydro.reactive_power_limits.max == pytest.approx(0.0)


def test_reeds_non_spinning_reserve_translates_to_variable_reserve_non_spinning(tmp_path) -> None:
    """NON_SPINNING reserves must translate to VariableReserveNonSpinning, not VariableReserve."""
    from r2x_reeds.models import ReEDSReserve
    from r2x_sienna.models import VariableReserve, VariableReserveNonSpinning

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(
        ReEDSReserve(
            name="NON_SPIN_UP",
            reserve_type="NON_SPINNING",
            direction="Up",
            time_frame=600.0,
            duration=1800.0,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    apply_rules_to_context(context)

    non_spin = list(context.target_system.get_components(VariableReserveNonSpinning))
    spinning = list(context.target_system.get_components(VariableReserve))

    assert len(non_spin) == 1, "NON_SPINNING reserve must produce VariableReserveNonSpinning"
    assert len(spinning) == 0, "NON_SPINNING reserve must NOT produce VariableReserve"

    ns = non_spin[0]
    assert ns.name == "NON_SPIN_UP"
    assert ns.time_frame == pytest.approx(600.0)
    assert ns.sustained_time == pytest.approx(1800.0)


def test_gen_services_attaches_non_spinning_reserve_to_generator(tmp_path) -> None:
    """Translated generators must include VariableReserveNonSpinning in their services list.

    Regression: get_gen_services previously only searched VariableReserve, so a
    generator with ext['reserves'] referencing a NON_SPINNING reserve would get
    an empty services list even after the reserve was translated.
    """
    from r2x_reeds.models import ReEDSRegion, ReEDSReserve, ReEDSStorage, ReEDSThermalGenerator
    from r2x_sienna.models import (
        EnergyReservoirStorage,
        HydroPumpTurbine,
        ThermalStandard,
        VariableReserveNonSpinning,
    )

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)

    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)

    context.source_system.add_component(
        ReEDSReserve(
            name="NON_SPIN_UP",
            reserve_type="NON_SPINNING",
            direction="Up",
            time_frame=600.0,
            duration=1800.0,
        )
    )
    context.source_system.add_component(
        ReEDSThermalGenerator(
            name="THERM1",
            region=region,
            technology="gas-cc",
            capacity=100.0,
            heat_rate=7.5,
            fuel_type="gas",
            ext={"reserves": ["NON_SPIN_UP"]},
        )
    )
    context.source_system.add_component(
        ReEDSStorage(
            name="BATT1",
            region=region,
            technology="battery_4",
            capacity=50.0,
            storage_duration=4.0,
            round_trip_efficiency=0.9,
            ext={"reserves": ["NON_SPIN_UP"]},
        )
    )
    context.source_system.add_component(
        ReEDSStorage(
            name="PSH1",
            region=region,
            technology="pumped-hydro",
            capacity=50.0,
            storage_duration=12.0,
            round_trip_efficiency=0.8,
            ext={"reserves": ["NON_SPIN_UP"]},
        )
    )

    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    apply_rules_to_context(context)

    non_spin_reserves = list(context.target_system.get_components(VariableReserveNonSpinning))
    assert len(non_spin_reserves) == 1
    non_spin = non_spin_reserves[0]

    thermals = list(context.target_system.get_components(ThermalStandard))
    assert len(thermals) == 1
    assert (
        non_spin in thermals[0].services
    ), "ThermalStandard must have the VariableReserveNonSpinning in its services"

    storages = list(context.target_system.get_components(EnergyReservoirStorage))
    assert len(storages) == 1
    assert (
        non_spin in storages[0].services
    ), "EnergyReservoirStorage must have the VariableReserveNonSpinning in its services"

    pumped_hydro = list(context.target_system.get_components(HydroPumpTurbine))
    assert len(pumped_hydro) == 1
    assert (
        non_spin in pumped_hydro[0].services
    ), "HydroPumpTurbine must have the VariableReserveNonSpinning in its services"


def test_reeds_spinning_reserve_does_not_produce_non_spinning(tmp_path) -> None:
    """SPINNING reserves must go to VariableReserve, not VariableReserveNonSpinning."""
    from r2x_reeds.models import ReEDSReserve
    from r2x_sienna.models import VariableReserve, VariableReserveNonSpinning

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    context.source_system.add_component(
        ReEDSReserve(
            name="SPIN",
            reserve_type="SPINNING",
            direction="Up",
            time_frame=300.0,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    apply_rules_to_context(context)

    spinning = list(context.target_system.get_components(VariableReserve))
    non_spin = list(context.target_system.get_components(VariableReserveNonSpinning))

    assert len(spinning) == 1
    assert len(non_spin) == 0


def test_reeds_electrolyzer_demand_translates_to_standard_load(tmp_path) -> None:
    """ReEDSElectrolyzerDemand must translate to StandardLoad."""
    from r2x_reeds.models import ReEDSElectrolyzerDemand, ReEDSRegion
    from r2x_sienna.models import StandardLoad

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSElectrolyzerDemand(
            name="ELEC1",
            region=region,
            technology="electrolyzer",
            capacity=50.0,
            electricity_efficiency=55.0,
            max_active_power=40.0,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    apply_rules_to_context(context)

    loads = list(context.target_system.get_components(StandardLoad))
    assert len(loads) == 1

    load = loads[0]
    assert load.name == "ELEC1"
    assert load.category == "electrolyzer"
    assert load.constant_active_power == pytest.approx(0.8)
    assert load.max_constant_active_power == pytest.approx(0.8)
    assert load.base_power == pytest.approx(50.0)


def test_reeds_datacenter_demand_translates_to_standard_load(tmp_path) -> None:
    """ReEDSDataCenterDemand must translate to StandardLoad."""
    from r2x_reeds.models import ReEDSDataCenterDemand, ReEDSRegion
    from r2x_sienna.models import StandardLoad

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSDataCenterDemand(
            name="DC1",
            region=region,
            technology="data-center",
            capacity=200.0,
            electricity_efficiency=1.0,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    apply_rules_to_context(context)

    loads = list(context.target_system.get_components(StandardLoad))
    assert len(loads) == 1

    load = loads[0]
    assert load.name == "DC1"
    assert load.category == "data-center"
    # No explicit max_active_power — falls back to capacity
    assert load.constant_active_power == pytest.approx(1.0)
    assert load.max_constant_active_power == pytest.approx(1.0)
    assert load.base_power == pytest.approx(200.0)


def test_reeds_smr_demand_translates_to_standard_load(tmp_path) -> None:
    """SMR electricity demand must translate to StandardLoad."""
    from r2x_reeds.models import ReEDSRegion, ReEDSSteamMethaneReformingDemand
    from r2x_sienna.models import StandardLoad

    context, rules = make_context_and_rules(tmp_path)
    context.source_system = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    context.source_system.add_component(region)
    context.source_system.add_component(
        ReEDSSteamMethaneReformingDemand(
            name="SMR1",
            region=region,
            technology="smr",
            capacity=50.0,
            electricity_efficiency=1.0,
            max_active_power=40.0,
        )
    )
    context.source_system.add_component(
        ReEDSSteamMethaneReformingDemand(
            name="SMR_CCS1",
            region=region,
            technology="smr_ccs",
            capacity=30.0,
            electricity_efficiency=1.0,
        )
    )
    context.target_system = System(name="target", system_base=100.0, auto_add_composed_components=True)
    context.rules = rules

    apply_rules_to_context(context)

    loads = {load.name: load for load in context.target_system.get_components(StandardLoad)}
    assert set(loads) == {"SMR1", "SMR_CCS1"}
    assert loads["SMR1"].category == "smr"
    assert loads["SMR1"].constant_active_power == pytest.approx(0.8)
    assert loads["SMR1"].max_constant_active_power == pytest.approx(0.8)
    assert loads["SMR1"].base_power == pytest.approx(50.0)
    assert loads["SMR_CCS1"].category == "smr_ccs"
    assert loads["SMR_CCS1"].constant_active_power == pytest.approx(1.0)
    assert loads["SMR_CCS1"].max_constant_active_power == pytest.approx(1.0)
    assert loads["SMR_CCS1"].base_power == pytest.approx(30.0)
