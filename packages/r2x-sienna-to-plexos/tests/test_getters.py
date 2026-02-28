"""Direct getter coverage tests for Sienna-to-PLEXOS."""

from __future__ import annotations

import json

import pytest
from infrasys.cost_curves import FuelCurve, UnitSystem
from infrasys.function_data import QuadraticFunctionData
from infrasys.value_curves import InputOutputCurve, LinearCurve
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_sienna.models import (
    ACBus,
    Arc,
    Area,
    EnergyReservoirStorage,
    HydroReservoir,
    HydroTurbine,
    Line,
    LoadZone,
    MinMax,
    PhaseShiftingTransformer,
    PowerLoad,
    TapTransformer,
    ThermalStandard,
    Transformer2W,
    TransmissionInterface,
    UpDown,
    VariableReserve,
)
from r2x_sienna.models.costs import (
    HydroGenerationCost,
    HydroReservoirCost,
    ThermalGenerationCost,
)
from r2x_sienna.models.enums import (
    ACBusTypes,
    HydroTurbineType,
    LoadConformity,
    PrimeMoversType,
    ReserveDirection,
    ReserveType,
    ReservoirDataType,
    ReservoirLocation,
    StorageTechs,
    ThermalFuels,
)
from r2x_sienna.models.named_tuples import Complex, FromTo_ToFrom, InputOutput
from r2x_sienna.units import ActivePower
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


def test_basic_getters_return_values(tmp_path):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus3 = ACBus(name="N4", base_voltage=115.0, number=3)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus3)

    arc1 = Arc(from_to=bus1, to_from=bus3)
    context.source_system.add_component(arc1)

    area = Area(name="A1", category="region")
    context.source_system.add_component(area)
    acbus = ACBus(name="N1", base_voltage=230.0, bustype=ACBusTypes.SLACK, number=100)
    context.source_system.add_component(acbus)

    line = Line(
        name="L1",
        rating=100.0,
        r=0.01,
        x=0.1,
        arc=arc1,
        b=FromTo_ToFrom(from_to=0.0, to_from=0.0),
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    context.source_system.add_component(line)

    gen = ThermalStandard(
        name="thermal-quad",
        bus=bus3,
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=220.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        active_power_limits=MinMax(min=22.0, max=220.0),
        ramp_limits=UpDown(up=88.0, down=66.0),
        time_limits=UpDown(up=3.0, down=1.5),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=QuadraticFunctionData(
                        quadratic_term=0.015,
                        proportional_term=9.8,
                        constant_term=120.0,
                    )
                ),
                fuel_cost=2.1,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    context.source_system.add_component(gen)

    # Add a hydro reservoir
    hydro = HydroReservoir.example()
    context.source_system.add_component(hydro)

    # Add a reserve
    reserve = VariableReserve(
        name="RES1",
        reserve_type=ReserveType.SPINNING,
        vors=10.0,
        max_participation_factor=0.5,
        direction="UP",
        requirement=100.0,
    )
    context.source_system.add_component(reserve)

    # Add a battery
    battery = EnergyReservoirStorage(
        name="energy-reservoir-storage-test",
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

    # Test node getters
    assert getters.get_voltage(acbus, context).unwrap() == 230.0
    assert getters.get_availability(acbus, context).unwrap() == 1
    assert getters.is_slack_bus(acbus, context).unwrap() == 1

    # Test line getters
    assert getters.get_line_min_flow(line, context).unwrap() == -10000.0
    assert getters.get_line_max_flow(line, context).unwrap() == 10000.0
    assert getters.get_line_charging_susceptance(line, context).unwrap() == 0.0

    # Test generator getters
    assert getters.get_max_capacity(gen, context).unwrap() == 48400.0

    # Test hydro reservoir getters
    assert getters.get_storage_initial_level(hydro, context).unwrap() == 0.5
    assert getters.get_storage_max_volume(hydro, context).unwrap() == 1000.0
    assert getters.get_storage_natural_inflow(hydro, context).unwrap() == 50.0

    # Test reserve getters
    assert getters.get_reserve_type(reserve, context).unwrap() == 1
    assert getters.get_reserve_vors(reserve, context).unwrap() == 10.0
    assert getters.get_reserve_max_sharing(reserve, context).unwrap() == 50.0

    # Test battery getters
    assert getters.get_storage_charge_efficiency(battery, context).unwrap() == 95.0
    assert getters.get_storage_discharge_efficiency(battery, context).unwrap() == 95.0
    assert getters.get_storage_cycles(battery, context).unwrap() == 5000.0
    assert getters.get_storage_max_power(battery, context).unwrap() == 200.0
    assert getters.get_storage_capacity(battery, context).unwrap() == 1000.0


def test_get_power_or_standard_load(tmp_path):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")
    acbus = ACBus(name="N2", base_voltage=115.0, number=2)
    context.source_system.add_component(acbus)
    # Add loads
    pload = PowerLoad(
        name="Load-1",
        bus=acbus,
        max_active_power=200.0,
    )
    sload = PowerLoad(
        name="Load-2",
        bus=acbus,
        max_active_power=200.0,
    )
    context.source_system.add_component(pload)
    context.source_system.add_component(sload)
    # Patch get_components to filter by bus
    _ = context.source_system.get_components

    def get_components(cls, filter_func=None):
        all_comps = [pload, sload]
        if filter_func:
            return [c for c in all_comps if filter_func(c)]
        return all_comps

    context.source_system.get_components = get_components
    assert getters.get_power_or_standard_load(acbus, context).unwrap() == 800.0


def test_get_head_tail_storage_names(tmp_path):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")
    hydro = HydroReservoir(
        name="hydro-reservoir-test",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        travel_time=2.0,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )
    context.source_system.add_component(hydro)
    assert getters.get_head_storage_name(hydro, context).unwrap() == "hydro-reservoir-test_head"
    assert getters.get_tail_storage_name(hydro, context).unwrap() == "hydro-reservoir-test_tail"
    assert isinstance(getters.get_head_storage_uuid(hydro, context).unwrap(), str)
    assert isinstance(getters.get_tail_storage_uuid(hydro, context).unwrap(), str)


def test_getters_with_missing_data(tmp_path):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)

    gen = ThermalStandard(
        name="thermal-standard-test",
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
    context.source_system.add_component(gen)
    assert getters.get_max_capacity(gen, context).unwrap() == 100.0

    plexos_gen = PLEXOSGenerator(name="G2")
    context.target_system.add_component(plexos_gen)
    result = getters.membership_component_child_node(plexos_gen, context)
    assert result.is_err()


def test_get_susceptance_transformers(tmp_path):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus2 = ACBus(name="N3", base_voltage=115.0, number=2)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)

    arc1 = Arc(from_to=bus1, to_from=bus2)
    context.source_system.add_component(arc1)

    t1 = Transformer2W(name="T1", arc=arc1, primary_shunt=Complex(real=1.0, imag=2.0))
    context.source_system.add_component(t1)
    assert getters.get_susceptance(t1, context).unwrap() == 2.0
    t2 = TapTransformer(name="T2", arc=arc1, primary_shunt=Complex(real=4.0, imag=2.0), tap=1.0)
    context.source_system.add_component(t2)
    assert getters.get_susceptance(t2, context).unwrap() == 2.0
    t3 = PhaseShiftingTransformer(
        name="T3",
        arc=arc1,
        tap=0.89,
        α=1.5,
        phase_angle_limits=MinMax(min=-0.03, max=0.03),
        primary_shunt=None,
    )
    context.source_system.add_component(t3)
    assert getters.get_susceptance(t3, context).is_err()


def test_get_line_charging_susceptance_types(tmp_path):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus2 = ACBus(name="N3", base_voltage=115.0, number=2)
    bus3 = ACBus(name="N4", base_voltage=115.0, number=3)
    bus4 = ACBus(name="N5", base_voltage=115.0, number=4)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)
    context.source_system.add_component(bus3)
    context.source_system.add_component(bus4)

    arc1 = Arc(from_to=bus1, to_from=bus2)
    arc2 = Arc(from_to=bus3, to_from=bus4)
    context.source_system.add_component(arc1)
    context.source_system.add_component(arc2)

    l1_2 = Line(
        name="line-1-2",
        arc=arc1,
        b=FromTo_ToFrom(from_to=3.0, to_from=3.0),
        rating=100.0,
        active_power_flow=100,
        reactive_power_flow=100,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    context.source_system.add_component(l1_2)
    assert getters.get_line_charging_susceptance(l1_2, context).unwrap() == 3.0

    l3_4 = Line(
        name="line-3-4",
        arc=arc2,
        b=FromTo_ToFrom(from_to=7.0, to_from=7.0),
        rating=100.0,
        active_power_flow=100,
        reactive_power_flow=100,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    context.source_system.add_component(l3_4)
    assert getters.get_line_charging_susceptance(l3_4, context).unwrap() == 7.0


def test_get_load_participation_factor(tmp_path):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")
    acbus = ACBus(name="N3", base_voltage=115.0, number=3)
    context.source_system.add_component(acbus)
    # StandardLoad with ext
    sload = PowerLoad(
        name="Load-2",
        bus=acbus,
        max_active_power=200.0,
    )
    context.source_system.add_component(sload)
    assert getters.get_load_participation_factor(acbus, context).unwrap() == 0.0


def test_membership_collection_enums(tmp_path):
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")
    dummy = object()
    assert getters.membership_collection_nodes(dummy, context).unwrap().name == "Nodes"
    assert getters.membership_collection_lines(dummy, context).unwrap().name == "Lines"
    assert getters.membership_collection_generators(dummy, context).unwrap().name == "Generators"
    assert getters.membership_collection_batteries(dummy, context).unwrap().name == "Batteries"
    assert getters.membership_collection_region(dummy, context).unwrap().name == "Region"
    assert getters.membership_collection_node_from(dummy, context).unwrap().name == "NodeFrom"
    assert getters.membership_collection_node_to(dummy, context).unwrap().name == "NodeTo"
    assert getters.membership_collection_zone(dummy, context).unwrap().name == "Zone"
    assert getters.membership_collection_head_storage(dummy, context).unwrap().name == "HeadStorage"
    assert getters.membership_collection_tail_storage(dummy, context).unwrap().name == "TailStorage"


def test_get_voltage_valid(context):
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    assert getters.get_voltage(bus, context).unwrap() == 115.0


def test_get_availability_true(context):
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    bus.available = True
    assert getters.get_availability(bus, context).unwrap() == 1


def test_is_slack_bus_true(context):
    bus = ACBus(name="N1", base_voltage=115.0, bustype=ACBusTypes.SLACK, number=1)
    assert getters.is_slack_bus(bus, context).unwrap() == 1


def test_get_line_min_flow_max_flow_with_rating(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus3 = ACBus(name="N4", base_voltage=115.0, number=3)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus3)

    arc = Arc(from_to=bus1, to_from=bus3)
    context.source_system.add_component(arc)
    line = Line(
        name="L1",
        rating=100.0,
        r=0.01,
        x=0.1,
        arc=arc,
        b=FromTo_ToFrom(from_to=0.0, to_from=0.0),
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    assert getters.get_line_min_flow(line, context).unwrap() == -10000.0
    assert getters.get_line_max_flow(line, context).unwrap() == 10000.0


def test_get_line_charging_susceptance_with_b(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus3 = ACBus(name="N4", base_voltage=115.0, number=3)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus3)

    arc = Arc(from_to=bus1, to_from=bus3)
    context.source_system.add_component(arc)
    line = Line(
        name="L1",
        rating=100.0,
        r=0.01,
        x=0.1,
        arc=arc,
        b=FromTo_ToFrom(from_to=2.5, to_from=2.5),
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    assert getters.get_line_charging_susceptance(line, context).unwrap() == 2.5


def test_get_max_capacity_with_limits(context):
    gen = ThermalStandard(
        name="GEN1",
        bus=ACBus(name="N1", base_voltage=115.0, number=1),
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
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=QuadraticFunctionData(
                        quadratic_term=0.01,
                        proportional_term=9.0,
                        constant_term=100.0,
                    )
                ),
                fuel_cost=2.0,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    assert getters.get_max_capacity(gen, context).unwrap() == 1000.0


def test_get_storage_charge_discharge_efficiency_valid(context):
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
        efficiency=InputOutput(input=0.95, output=0.92),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    assert getters.get_storage_charge_efficiency(battery, context).unwrap() == 95.0
    assert getters.get_storage_discharge_efficiency(battery, context).unwrap() == 92.0


def test_get_storage_cycles_valid(context):
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
        efficiency=InputOutput(input=0.95, output=0.92),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    assert getters.get_storage_cycles(battery, context).unwrap() == 5000.0


def test_get_storage_max_power_valid(context):
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
        efficiency=InputOutput(input=0.95, output=0.92),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    assert getters.get_storage_max_power(battery, context).unwrap() == 200.0


def test_get_storage_capacity_valid(context):
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
        efficiency=InputOutput(input=0.95, output=0.92),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    assert getters.get_storage_capacity(battery, context).unwrap() == 1000.0


def test_get_reserve_type_valid(context):
    reserve = VariableReserve(
        name="RES1",
        reserve_type=ReserveType.SPINNING,
        vors=2000.0,
        direction="UP",
        requirement=100.0,
    )
    assert getters.get_reserve_type(reserve, context).unwrap() == 1


def test_get_reserve_vors_valid(context):
    reserve = VariableReserve(
        name="RES1",
        reserve_type=ReserveType.SPINNING,
        vors=1000.0,
        direction="UP",
        requirement=100.0,
    )
    assert getters.get_reserve_vors(reserve, context).unwrap() == 1000.0


def test_get_reserve_max_sharing_valid(context):
    reserve = VariableReserve(
        name="RES1",
        reserve_type=ReserveType.SPINNING,
        vors=3000.0,
        direction="DOWN",
        requirement=100.0,
    )
    reserve.max_participation_factor = 0.5
    assert getters.get_reserve_max_sharing(reserve, context).unwrap() == 50.0


def test_get_power_or_standard_load_valid(context):
    acbus = ACBus(name="N2", base_voltage=115.0, number=2)
    context.source_system.add_component(acbus)
    pload = PowerLoad(
        name="Load-1",
        bus=acbus,
        max_active_power=200.0,
    )
    sload = PowerLoad(
        name="Load-2",
        bus=acbus,
        max_active_power=200.0,
    )
    context.source_system.add_component(pload)
    context.source_system.add_component(sload)

    def get_components(cls, filter_func=None):
        all_comps = [pload, sload]
        if filter_func:
            return [c for c in all_comps if filter_func(c)]
        return all_comps

    context.source_system.get_components = get_components
    assert getters.get_power_or_standard_load(acbus, context).unwrap() == 800.0


def test_get_head_tail_storage_names_valid(context):
    hydro = HydroReservoir(
        name="hydro-reservoir-test",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        travel_time=2.0,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )
    context.source_system.add_component(hydro)
    assert getters.get_head_storage_name(hydro, context).unwrap() == "hydro-reservoir-test_head"
    assert getters.get_tail_storage_name(hydro, context).unwrap() == "hydro-reservoir-test_tail"
    assert isinstance(getters.get_head_storage_uuid(hydro, context).unwrap(), str)
    assert isinstance(getters.get_tail_storage_uuid(hydro, context).unwrap(), str)


def test_membership_collection_enums_valid(context):
    dummy = object()
    assert getters.membership_collection_nodes(dummy, context).unwrap().name == "Nodes"
    assert getters.membership_collection_lines(dummy, context).unwrap().name == "Lines"
    assert getters.membership_collection_generators(dummy, context).unwrap().name == "Generators"
    assert getters.membership_collection_batteries(dummy, context).unwrap().name == "Batteries"
    assert getters.membership_collection_region(dummy, context).unwrap().name == "Region"
    assert getters.membership_collection_node_from(dummy, context).unwrap().name == "NodeFrom"
    assert getters.membership_collection_node_to(dummy, context).unwrap().name == "NodeTo"
    assert getters.membership_collection_zone(dummy, context).unwrap().name == "Zone"
    assert getters.membership_collection_head_storage(dummy, context).unwrap().name == "HeadStorage"
    assert getters.membership_collection_tail_storage(dummy, context).unwrap().name == "TailStorage"


def test_get_hydro_dispatch_properties(context):
    from r2x_sienna.models import HydroDispatch
    from r2x_sienna.models.costs import HydroGenerationCost

    bus1 = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)

    hydro = HydroDispatch(
        name="HD1",
        bus=bus1,
        rating=100.0,
        active_power=50.0,
        reactive_power=10.0,
        base_power=100.0,
        prime_mover_type=PrimeMoversType.HY,
        ramp_limits=UpDown(up=5.0, down=5.0),
        active_power_limits=MinMax(min=0.0, max=100.0),
        operation_cost=HydroGenerationCost.example(),
    )
    context.source_system.add_component(hydro)
    assert getters.get_component_rating(hydro, context).unwrap() == 10000.0
    assert getters.get_max_ramp_down(hydro, context).unwrap() == 500.0
    assert getters.get_max_ramp_up(hydro, context).unwrap() == 500.0


def test_get_component_rating_transformer(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    bus3 = ACBus(name="N4", base_voltage=115.0, number=3)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus3)

    arc1 = Arc(from_to=bus1, to_from=bus3)
    context.source_system.add_component(arc1)

    t = Transformer2W(
        name="T1",
        arc=arc1,
        primary_shunt=Complex(real=1.0, imag=2.0),
        rating=50.0,
        base_power=2.0,
        x=0.1,
        r=0.01,
    )
    assert getters.get_component_rating(t, context).unwrap() == 100.0


def test_get_component_rating_hydro_turbine(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht = HydroTurbine(
        name="hydro-turbine-test",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=150.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    assert getters.get_component_rating(ht, context).unwrap() == 22500.0


def test_get_vom_cost(context):
    from infrasys.cost_curves import CostCurve
    from infrasys.function_data import LinearFunctionData
    from infrasys.value_curves import InputOutputCurve
    from r2x_sienna.models.costs import ThermalGenerationCost

    gen = ThermalStandard(
        name="GEN1",
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
        prime_mover_type=PrimeMoversType.CC,
        fuel="GEOTHERMAL",
        operation_cost=ThermalGenerationCost(
            variable=CostCurve(
                vom_cost=InputOutputCurve(
                    function_data=LinearFunctionData(proportional_term=5.0, constant_term=2.0)
                ),
                value_curve=LinearCurve(1.0),
                power_units=UnitSystem.NATURAL_UNITS,
            )
        ),
    )
    assert getters.get_vom_cost(gen, context).unwrap() == 2.0


def test_get_turbine_pump_load_and_efficiency(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht = HydroTurbine(
        name="hydro-turbine-test",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=150.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    assert getters.get_turbine_pump_load(ht, context).unwrap() == 22500.0
    assert getters.get_turbine_pump_efficiency(ht, context).unwrap() == 92.0


def test_get_thermal_forced_outage_rate_defaults(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht = HydroTurbine(
        name="hydro-turbine-test",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=150.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    assert getters.get_thermal_forced_outage_rate(ht, context).unwrap() >= 0.0


def test_thermal_standard_all_getters(context):
    from infrasys.cost_curves import CostCurve, FuelCurve
    from infrasys.function_data import PiecewiseLinearData, XYCoords
    from infrasys.value_curves import InputOutputCurve, LinearCurve
    from r2x_sienna.models.costs import ThermalGenerationCost

    gen = ThermalStandard(
        name="GEN1",
        bus=None,
        active_power=10.0,
        reactive_power=0.0,
        rating=100.0,
        base_power=2.0,
        must_run=False,
        status=True,
        time_at_status=5.0,
        active_power_limits=MinMax(min=10.0, max=100.0),
        ramp_limits=UpDown(up=10.0, down=10.0),
        time_limits=UpDown(up=2.0, down=3.0),
        prime_mover_type=PrimeMoversType.CC,
        fuel="NUCLEAR",
        operation_cost=ThermalGenerationCost(
            fixed=5.0,
            shut_down=1.0,
            start_up=2.0,
            variable=FuelCurve(value_curve=LinearCurve(10), power_units=UnitSystem.NATURAL_UNITS),
        ),
    )

    # min up/down time
    assert getters.get_min_up_time(gen, context).unwrap() == 2.0
    assert getters.get_min_down_time(gen, context).unwrap() == 3.0

    # initial generation/hours
    assert getters.get_initial_generation(gen, context).unwrap() == 20.0
    assert getters.get_initial_hours_up(gen, context).unwrap() == 5.0
    gen.status = False
    assert getters.get_initial_hours_down(gen, context).unwrap() == 5.0

    # running/start/shutdown cost
    assert getters.get_running_cost(gen, context).unwrap() == 5.0
    assert getters.get_start_cost(gen, context).unwrap() == 2.0
    assert getters.get_shutdown_cost(gen, context).unwrap() == 1.0

    # fuel price
    assert getters.get_fuel_price(gen, context).unwrap() == 0.0

    # mark up and mark up point
    gen.operation_cost = ThermalGenerationCost(
        variable=CostCurve(
            vom_cost=InputOutputCurve(
                function_data=PiecewiseLinearData(points=[XYCoords(0, 0), XYCoords(10, 10)])
            ),
            value_curve=LinearCurve(1.0),
            power_units=UnitSystem.NATURAL_UNITS,
        )
    )
    assert getters.get_mark_up(gen, context).unwrap() is not None
    assert getters.get_mark_up_point(gen, context).unwrap() is not None


def test_get_storage_charge_discharge_efficiency_100(context):
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
    assert getters.get_storage_charge_efficiency(battery, context).unwrap() == 100.0
    assert getters.get_storage_discharge_efficiency(battery, context).unwrap() == 100.0


def test_get_interface_min_max_flow(context):
    ti = TransmissionInterface(
        name="TI1",
        active_power_flow_limits=MinMax(min=10.0, max=20.0),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    assert getters.get_interface_min_flow(ti, context).unwrap() == 10.0
    assert getters.get_interface_max_flow(ti, context).unwrap() == 20.0


def test_membership_parent_component(context):
    dummy = object()
    assert getters.membership_parent_component(dummy, context).unwrap() is dummy


def test_membership_collection_enums_all(context):
    dummy = object()
    assert getters.membership_collection_nodes(dummy, context).unwrap().name == "Nodes"
    assert getters.membership_collection_lines(dummy, context).unwrap().name == "Lines"
    assert getters.membership_collection_generators(dummy, context).unwrap().name == "Generators"
    assert getters.membership_collection_batteries(dummy, context).unwrap().name == "Batteries"
    assert getters.membership_collection_region(dummy, context).unwrap().name == "Region"
    assert getters.membership_collection_node_from(dummy, context).unwrap().name == "NodeFrom"
    assert getters.membership_collection_node_to(dummy, context).unwrap().name == "NodeTo"
    assert getters.membership_collection_zone(dummy, context).unwrap().name == "Zone"
    assert getters.membership_collection_head_storage(dummy, context).unwrap().name == "HeadStorage"
    assert getters.membership_collection_tail_storage(dummy, context).unwrap().name == "TailStorage"


def test_get_head_tail_storage_uuid(context):
    hydro = HydroReservoir(
        name="hydro-reservoir-test",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        travel_time=2.0,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )
    assert isinstance(getters.get_head_storage_uuid(hydro, context).unwrap(), str)
    assert isinstance(getters.get_tail_storage_uuid(hydro, context).unwrap(), str)


def test_get_area_units_and_load(context):
    area = Area(name="A1", category="region")
    assert getters.get_area_units(area, context).unwrap() == 1.0
    assert getters.get_area_load(area, context).unwrap() == 0.0


def test_get_head_tail_storage_name(context):
    hydro = HydroReservoir(
        name="hydro1",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        travel_time=2.0,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )
    assert getters.get_head_storage_name(hydro, context).unwrap() == "hydro1_head"
    assert getters.get_tail_storage_name(hydro, context).unwrap() == "hydro1_tail"


def test_membership_node_child_zone(context):
    node = PLEXOSNode(name="N1")
    zone = LoadZone(name="Z1")
    context.source_system.add_component(zone)
    bus = ACBus(name="N1", load_zone=zone, number=1)
    context.source_system.add_component(bus)
    context.target_system.add_component(PLEXOSZone(name="Z1"))
    assert getters.membership_node_child_zone(node, context).unwrap().name == "Z1"


def test_membership_component_child_node_generator(context):
    gen = PLEXOSGenerator(name="GEN1")
    node = PLEXOSNode(name="N1")
    bus = ACBus(name="N1", number=1)
    context.source_system.add_component(bus)
    source_gen = ThermalStandard(
        name="GEN1",
        must_run=False,
        bus=bus,
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
    context.source_system.add_component(source_gen)
    context.target_system.add_component(node)
    context.target_system.add_component(gen)
    assert getters.membership_component_child_node(gen, context).unwrap().name == "N1"


def test_membership_component_child_node_battery(context):
    bat = PLEXOSBattery(name="BAT1")
    node = PLEXOSNode(name="N2")
    bus = ACBus(name="N2", number=2)
    context.source_system.add_component(bus)

    source_bat = EnergyReservoirStorage(
        name="BAT1",
        available=True,
        bus=bus,
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
    context.source_system.add_component(source_bat)
    context.target_system.add_component(node)
    context.target_system.add_component(bat)
    assert getters.membership_component_child_node(bat, context).unwrap().name == "N2"


def test_membership_region_parent_node(context):
    region = PLEXOSRegion(name="A1")
    node = PLEXOSNode(name="A1")
    area = Area(name="A1")
    bus = ACBus(name="A1", area=area, number=1)
    context.target_system.add_component(region)
    context.target_system.add_component(node)
    context.source_system.add_component(area)
    context.source_system.add_component(bus)
    assert getters.membership_region_parent_node(region, context).unwrap().name == "A1"


def test_membership_line_from_to_parent_node(context):
    line = PLEXOSLine(name="L1")
    node_from = PLEXOSNode(name="N1")
    node_to = PLEXOSNode(name="N2")
    bus_from = ACBus(name="N1", number=1)
    bus_to = ACBus(name="N2", number=2)
    context.source_system.add_component(bus_from)
    context.source_system.add_component(bus_to)
    arc = Arc(from_to=bus_from, to_from=bus_to)
    context.source_system.add_component(arc)

    source_line = Line(
        name="L1",
        arc=arc,
        rating=100.0,
        r=0.01,
        x=0.1,
        b=FromTo_ToFrom(from_to=3.0, to_from=3.0),
        active_power_flow=100,
        reactive_power_flow=100,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )

    context.source_system.add_component(source_line)
    context.target_system.add_component(line)
    context.target_system.add_component(node_from)
    context.target_system.add_component(node_to)
    assert getters.membership_line_from_parent_node(line, context).unwrap().name == "N1"
    assert getters.membership_line_to_parent_node(line, context).unwrap().name == "N2"


def test_membership_transformer_from_to_parent_node(context):
    transformer = PLEXOSTransformer(name="T1")
    node_from = PLEXOSNode(name="N1")
    node_to = PLEXOSNode(name="N2")
    bus_from = ACBus(name="N1", number=1)
    bus_to = ACBus(name="N2", number=2)
    context.source_system.add_component(bus_from)
    context.source_system.add_component(bus_to)

    arc = Arc(from_to=bus_from, to_from=bus_to)
    context.source_system.add_component(arc)

    source_transformer = Transformer2W(
        name="T1",
        arc=arc,
        primary_shunt=Complex(real=0.0, imag=0.0),
        rating=50.0,
        base_power=2.0,
        x=0.1,
        r=0.01,
    )

    context.source_system.add_component(source_transformer)
    context.target_system.add_component(transformer)
    context.target_system.add_component(node_from)
    context.target_system.add_component(node_to)
    assert getters.membership_transformer_from_parent_node(transformer, context).unwrap().name == "N1"
    assert getters.membership_transformer_to_parent_node(transformer, context).unwrap().name == "N2"


def test_membership_head_tail_storage_generator(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht = HydroTurbine(
        name="hydro1_Turbine",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=150.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    storage_head = PLEXOSStorage(name="hydro1_Reservoir_head")
    storage_tail = PLEXOSStorage(name="hydro1_Reservoir_tail")
    context.target_system.add_component(storage_head)
    context.target_system.add_component(storage_tail)
    assert getters.membership_head_storage_generator(ht, context).unwrap().name == "hydro1_Reservoir_head"
    assert getters.membership_tail_storage_generator(ht, context).unwrap().name == "hydro1_Reservoir_tail"


def test__get_time_limit_ext(context):
    # Covers ext dict fallback
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
    assert getters.get_min_up_time(gen, context).unwrap() == 7.5


def test__get_defaults(tmp_path):
    # Covers defaults.json fallback and error branch
    defaults_dir = tmp_path / "r2x_sienna_to_plexos" / "config"
    defaults_dir.mkdir(parents=True, exist_ok=True)
    defaults_path = defaults_dir / "defaults.json"
    defaults_path.write_text(json.dumps({"pcm_defaults": {"battery": {"forced_outage_rate": "bad"}}}))
    import importlib.resources

    importlib.resources.files = lambda pkg: defaults_dir
    assert getters._get_defaults("battery", "forced_outage_rate") == 0.01


def test__lookup_target_zone_by_name_err(context):
    assert getters._lookup_target_zone_by_name(context, "missing").is_err()


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
    assert getters.get_susceptance(t, context).unwrap() == 0.0


def test_get_line_min_max_flow_and_charging_susceptance_none(context):
    from r2x_sienna.models.named_tuples import FromTo_ToFrom

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
    assert getters.get_line_charging_susceptance(line, context).unwrap() == 5.0


def test_get_power_or_standard_load_no_loads(context):
    acbus = ACBus(name="N1", base_voltage=115.0, number=1)
    assert getters.get_power_or_standard_load(acbus, context).unwrap() == 0.0


def test_get_storage_initial_level_max_volume_natural_inflow_none(context):
    from infrasys.value_curves import LinearCurve
    from r2x_sienna.models import HydroReservoir
    from r2x_sienna.models.costs import HydroReservoirCost

    hr = HydroReservoir(
        name="hydro1",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=0.8,
        travel_time=2.0,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        operation_cost=HydroReservoirCost.example(),
        level_data_type="USABLE_VOLUME",
        category="hydro_reservoir",
    )

    hr.initial_level = 100.0
    hr.storage_level_limits = {"min": 0.0, "max": 1000.0}
    hr.inflow = 50.0
    assert getters.get_storage_initial_level(hr, context).unwrap() == 100.0

    hr.initial_level = 0.5
    hr.storage_level_limits = {"min": 0.0, "max": 1000.0}
    hr.inflow = 50.0
    assert getters.get_storage_max_volume(hr, context).unwrap() == 1000.0

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
    assert getters.get_storage_initial_level(hr, context).unwrap() == 500.0
    assert getters.get_storage_max_volume(hr, context).unwrap() == 1000.0
    assert getters.get_storage_natural_inflow(hr, context).unwrap() == 123.0


def test_get_heat_rate_none(context):
    class Dummy:
        pass

    assert getters.get_heat_rate_base(Dummy(), context).unwrap() == 0.0
    assert getters.get_heat_rate_incr(Dummy(), context).unwrap() == 0.0
    assert getters.get_heat_rate_incr2(Dummy(), context).unwrap() == 0.0
    assert getters.get_heat_rate_incr3(Dummy(), context).unwrap() == 0.0
    result = getters.get_heat_rate_load_point(Dummy(), context)
    assert result.is_err()


def test_get_min_stable_level_none(context):
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus)
    gen = ThermalStandard(
        name="thermal-standard-test",
        must_run=False,
        bus=bus,
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
    assert getters.get_min_stable_level(gen, context).unwrap() == 0.0


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
    assert getters.get_reserve_min_provision(reserve, context).unwrap() == 100.0
    assert getters.get_reserve_type(reserve, context).unwrap() == 1
    assert getters.get_reserve_vors(reserve, context).unwrap() == 0.05
    assert getters.get_reserve_max_sharing(reserve, context).unwrap() == 100.0

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
    assert getters.get_load_subtracter(Dummy(), context).unwrap() == 0.0
    assert getters.get_component_rating(d, context).unwrap() == 0.0
    assert getters.get_vom_cost(Dummy(), context).unwrap() == 0.0
    assert getters.get_turbine_pump_load(d, context).unwrap() == 0.0
    assert getters.get_turbine_pump_efficiency(d, context).unwrap() == 100.0
    assert getters.get_thermal_forced_outage_rate(d, context).unwrap() >= 0.0
    assert getters.get_thermal_maintenance_rate(d, context).unwrap() >= 0.0
    assert getters.get_thermal_mean_time_to_repair(d, context).unwrap() >= 0.0
    assert getters.get_turbine_forced_outage_rate(d, context).unwrap() >= 0.0
    assert getters.get_turbine_maintenance_rate(d, context).unwrap() >= 0.0
    assert getters.get_hydro_mean_time_to_repair(d, context).unwrap() >= 0.0
    assert getters.get_turbine_mean_time_to_repair(d, context).unwrap() >= 0.0
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
    assert getters.get_min_up_time(gen, context).unwrap() == 0.0
    assert getters.get_min_down_time(gen, context).unwrap() == 0.0
    assert getters.get_initial_generation(gen, context).unwrap() == 0.0
    assert getters.get_initial_hours_up(gen, context).unwrap() == 0.0
    assert getters.get_initial_hours_down(gen, context).unwrap() == 1000.0


def test_getters_none_costs_and_battery(context):
    class Dummy:
        operation_cost = None
        forced_outage_rate = None
        maintenance_rate = None
        mean_time_to_repair = None

    d = Dummy()
    assert getters.get_running_cost(d, context).unwrap() == 0.0
    assert getters.get_start_cost(d, context).unwrap() == 0.0
    assert getters.get_shutdown_cost(d, context).unwrap() == 0.0
    assert getters.get_fuel_price(d, context).unwrap() == 0.0
    assert getters.get_mark_up(Dummy(), context).unwrap() == 0.0
    result = getters.get_mark_up_point(Dummy(), context)
    assert result.is_err()
    assert getters.get_vom_charge(Dummy(), context).unwrap() == 0.0
    assert getters.get_battery_forced_outage_rate(d, context).unwrap() >= 0.0
    assert getters.get_battery_maintenance_rate(d, context).unwrap() >= 0.0
    assert getters.get_battery_mean_time_to_repair(d, context).unwrap() >= 0.0


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
    assert getters.get_storage_charge_efficiency(battery, context).unwrap() == 100.0
    assert getters.get_storage_discharge_efficiency(battery, context).unwrap() == 100.0


def test_get_storage_cycles_none(context):
    class Dummy:
        cycle_limits = None

    assert getters.get_storage_cycles(Dummy(), context).unwrap() == 0.0


def test_get_storage_max_power_none(context):
    class Dummy:
        output_active_power_limits = type("Limits", (), {"max": None})()
        base_power = 1.0

    assert getters.get_storage_max_power(Dummy(), context).unwrap() == 0.0


def test_get_storage_capacity_none(context):
    class Dummy:
        storage_capacity = None
        base_power = 1.0

    assert getters.get_storage_capacity(Dummy(), context).unwrap() == 0.0


def test_get_interface_min_flow_not_none(context):
    ti = TransmissionInterface(
        name="ExampleTransmissionInterface",
        active_power_flow_limits=MinMax(min=-100, max=100),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    assert getters.get_interface_min_flow(ti, context).unwrap() == -100.0


def test_get_interface_max_flow_not_none(context):
    ti = TransmissionInterface(
        name="ExampleTransmissionInterface",
        active_power_flow_limits=MinMax(min=-100, max=100),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    assert getters.get_interface_max_flow(ti, context).unwrap() == 100.0


def test_membership_collection_nodes(context):
    dummy = object()
    assert getters.membership_collection_nodes(dummy, context).unwrap().name == "Nodes"


def test_membership_collection_lines(context):
    dummy = object()
    assert getters.membership_collection_lines(dummy, context).unwrap().name == "Lines"


def test_membership_collection_generators(context):
    dummy = object()
    assert getters.membership_collection_generators(dummy, context).unwrap().name == "Generators"


def test_membership_collection_batteries(context):
    dummy = object()
    assert getters.membership_collection_batteries(dummy, context).unwrap().name == "Batteries"


def test_membership_collection_region(context):
    dummy = object()
    assert getters.membership_collection_region(dummy, context).unwrap().name == "Region"


def test_membership_collection_node_from(context):
    dummy = object()
    assert getters.membership_collection_node_from(dummy, context).unwrap().name == "NodeFrom"


def test_membership_collection_node_to(context):
    dummy = object()
    assert getters.membership_collection_node_to(dummy, context).unwrap().name == "NodeTo"


def test_membership_collection_zone(context):
    dummy = object()
    assert getters.membership_collection_zone(dummy, context).unwrap().name == "Zone"


def test_membership_collection_head_storage(context):
    dummy = object()
    assert getters.membership_collection_head_storage(dummy, context).unwrap().name == "HeadStorage"


def test_membership_collection_tail_storage(context):
    dummy = object()
    assert getters.membership_collection_tail_storage(dummy, context).unwrap().name == "TailStorage"


def test_get_head_storage_uuid(context):
    hydro = HydroReservoir(
        name="HeadReservoir",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        travel_time=0.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert isinstance(getters.get_head_storage_uuid(hydro, context).unwrap(), str)


def test_get_tail_storage_uuid(context):
    hydro = HydroReservoir(
        name="TailReservoir",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        travel_time=0.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert isinstance(getters.get_tail_storage_uuid(hydro, context).unwrap(), str)


def test_get_area_units(context):
    area = Area(name="A1", category="region")
    assert getters.get_area_units(area, context).unwrap() == 1.0


def test_get_area_load(context):
    area = Area(name="A1", category="region")
    assert getters.get_area_load(area, context).unwrap() == 0.0


def test_get_head_storage_name(context):
    hydro = HydroReservoir(
        name="hydro1_head",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        travel_time=0.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert getters.get_head_storage_name(hydro, context).unwrap() == "hydro1_head"


def test_get_tail_storage_name(context):
    hydro = HydroReservoir(
        name="hydro1_tail",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        travel_time=0.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert getters.get_tail_storage_name(hydro, context).unwrap() == "hydro1_tail"


def test_membership_node_child_zone_err(context):
    node = PLEXOSNode(name="missing")
    result = getters.membership_node_child_zone(node, context)
    assert result.is_err()


def test_membership_reserve_child_generator_err(context):
    reserve = VariableReserve(
        name="missing", reserve_type=ReserveType.SPINNING, vors=10.0, direction="UP", requirement=100.0
    )
    result = getters.membership_reserve_child_generator(reserve, context)
    assert result.is_err()


def test_membership_reserve_child_battery_err(context):
    reserve = VariableReserve(
        name="missing", reserve_type=ReserveType.SPINNING, vors=10.0, direction="UP", requirement=100.0
    )
    result = getters.membership_reserve_child_battery(reserve, context)
    assert result.is_err()


def test_membership_component_child_node_err(context):
    gen = PLEXOSGenerator(name="missing")
    result = getters.membership_component_child_node(gen, context)
    assert result.is_err()


def test_membership_interface_child_line_err(context):
    interface = TransmissionInterface(
        name="ExampleTransmissionInterface",
        active_power_flow_limits=MinMax(min=-100, max=100),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    result = getters.membership_interface_child_line(interface, context)
    assert result.is_err()


def test_membership_region_parent_node_err(context):
    region = PLEXOSRegion(name="missing")
    result = getters.membership_region_parent_node(region, context)
    assert result.is_err()


def test_membership_region_child_node_err(context):
    region = PLEXOSRegion(name="missing")
    result = getters.membership_region_child_node(region, context)
    assert result.is_err()


def test_membership_line_from_parent_node_err(context):
    line = PLEXOSLine(name="missing")
    result = getters.membership_line_from_parent_node(line, context)
    assert result.is_err()


def test_membership_line_to_parent_node_err(context):
    line = PLEXOSLine(name="missing")
    result = getters.membership_line_to_parent_node(line, context)
    assert result.is_err()


def test_membership_transformer_from_parent_node_err(context):
    transformer = PLEXOSTransformer(name="missing")
    result = getters.membership_transformer_from_parent_node(transformer, context)
    assert result.is_err()


def test_membership_transformer_to_parent_node_err(context):
    transformer = PLEXOSTransformer(name="missing")
    result = getters.membership_transformer_to_parent_node(transformer, context)
    assert result.is_err()


def test_membership_head_storage_generator_err(context):
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus)
    ht = HydroTurbine(
        name="TestTurbine",
        available=True,
        bus=bus,
        active_power=0.0,
        reactive_power=0.0,
        rating=1.0,
        base_power=100.0,
        active_power_limits=MinMax(min=0.0, max=1.0),
        outflow_limits=None,
        powerhouse_elevation=0.0,
        ramp_limits=None,
        time_limits=None,
        operation_cost=HydroGenerationCost.example(),
        prime_mover_type=PrimeMoversType.OT,
    )
    result = getters.membership_head_storage_generator(ht, context)
    assert result.is_err()


def test_membership_tail_storage_generator_err(context):
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus)
    ht = HydroTurbine(
        name="TestTurbine",
        available=True,
        bus=bus,
        active_power=0.0,
        reactive_power=0.0,
        rating=1.0,
        base_power=100.0,
        active_power_limits=MinMax(min=0.0, max=1.0),
        outflow_limits=None,
        powerhouse_elevation=0.0,
        ramp_limits=None,
        time_limits=None,
        operation_cost=HydroGenerationCost.example(),
        prime_mover_type=PrimeMoversType.OT,
    )
    result = getters.membership_tail_storage_generator(ht, context)
    assert result.is_err()


# ...existing code...


def test_get_voltage_zero(context):
    """Covers get_voltage returning 0.0 when base_voltage has no magnitude."""
    bus = ACBus(name="N1", number=1)
    bus.base_voltage = None
    assert getters.get_voltage(bus, context).unwrap() == 0.0


def test_get_susceptance_complex_primary_shunt(context):
    """Covers complex number branch in get_susceptance."""
    bus1 = ACBus(name="N1", base_voltage=115.0, number=1)
    bus2 = ACBus(name="N2", base_voltage=115.0, number=2)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)
    arc = Arc(from_to=bus1, to_from=bus2)
    context.source_system.add_component(arc)
    t = Transformer2W(name="T1", arc=arc, primary_shunt=Complex(real=1.0, imag=3.0))
    assert getters.get_susceptance(t, context).unwrap() == 3.0


def test_get_line_min_max_flow_none_rating(context):
    """Covers None rating branch in get_line_min_flow and get_line_max_flow."""
    bus1 = ACBus(name="N1", base_voltage=115.0, number=1)
    bus2 = ACBus(name="N2", base_voltage=115.0, number=2)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)
    arc = Arc(from_to=bus1, to_from=bus2)
    context.source_system.add_component(arc)
    line = Line(
        name="L1",
        arc=arc,
        rating=None,
        r=0.01,
        x=0.1,
        b=FromTo_ToFrom(from_to=0.0, to_from=0.0),
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    assert getters.get_line_min_flow(line, context).unwrap() == 0.0
    assert getters.get_line_max_flow(line, context).unwrap() == 0.0


def test_get_line_charging_susceptance_complex_b(context):
    """Covers complex b branch in get_line_charging_susceptance."""
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
        b=FromTo_ToFrom(from_to=4.5, to_from=4.5),
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    assert getters.get_line_charging_susceptance(line, context).unwrap() == 4.5


def test_get_line_charging_susceptance_dict_b(context):
    """Covers dict b branch in get_line_charging_susceptance."""
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
        b={"from_to": 6.0, "to_from": 6.0},
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    assert getters.get_line_charging_susceptance(line, context).unwrap() == 6.0


def test_get_max_capacity_zero_from_sienna(context):
    """Covers branch where sienna_get_max_active_power returns 0.0 and falls through to active_power_limits dict."""

    class DummyWithLimits:
        active_power_limits = {"max": 55.0}  # noqa: RUF012
        rating = None

    d = DummyWithLimits()
    assert getters.get_max_capacity(d, context).unwrap() == 55.0


def test_get_component_rating_no_base_power(context):
    """Covers get_component_rating when rating is not None but base_power missing."""

    class Dummy:
        rating = 10.0
        base_power = 5.0

    assert getters.get_component_rating(Dummy(), context).unwrap() == 50.0


def test_get_turbine_pump_efficiency_gt_one(context):
    """Covers get_turbine_pump_efficiency when efficiency > 1.0 (already percent)."""

    class Dummy:
        efficiency = 95.0

    assert getters.get_turbine_pump_efficiency(Dummy(), context).unwrap() == 100.0


def test_get_max_ramp_up_down_dict(context):
    """Covers dict ramp_limits branch in get_max_ramp_up and get_max_ramp_down."""

    class DummyRamp:
        ramp_limits = {"up": 10.0, "down": 8.0}  # noqa: RUF012
        base_power = 100.0

    d = DummyRamp()
    assert getters.get_max_ramp_up(d, context).unwrap() == 1000.0
    assert getters.get_max_ramp_down(d, context).unwrap() == 800.0


def test_get_max_ramp_up_down_object(context):
    """Covers object ramp_limits branch in get_max_ramp_up and get_max_ramp_down."""

    class DummyRamp:
        ramp_limits = UpDown(up=5.0, down=3.0)
        base_power = 10.0

    d = DummyRamp()
    assert getters.get_max_ramp_up(d, context).unwrap() == 50.0
    assert getters.get_max_ramp_down(d, context).unwrap() == 30.0


def test_get_initial_hours_up_status_true(context):
    """Covers get_initial_hours_up when status is True."""
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus)
    gen = ThermalStandard(
        name="gen-up",
        must_run=False,
        bus=bus,
        status=True,
        base_power=100.0,
        rating=100.0,
        active_power=0.0,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.0, max=100.0),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost.example(),
        time_at_status=500.0,
    )
    assert getters.get_initial_hours_up(gen, context).unwrap() == 500.0
    assert getters.get_initial_hours_down(gen, context).unwrap() == 0.0


def test_get_fuel_price_fuel_curve(context):
    """Covers get_fuel_price with a FuelCurve that has fuel_cost."""
    from infrasys.cost_curves import FuelCurve
    from infrasys.value_curves import LinearCurve
    from r2x_sienna.models.costs import ThermalGenerationCost

    gen = ThermalStandard(
        name="GEN-FUEL",
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
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=LinearCurve(10.0),
                fuel_cost=3.5,
                power_units=UnitSystem.NATURAL_UNITS,
            )
        ),
    )
    assert getters.get_fuel_price(gen, context).unwrap() == 3.5


def test_get_storage_max_power_dict_limits(context):
    """Covers dict output_active_power_limits branch in get_storage_max_power."""

    class Dummy:
        output_active_power_limits = {"max": 150.0}  # noqa: RUF012
        base_power = 1.0

    assert getters.get_storage_max_power(Dummy(), context).unwrap() == 150.0


def test_get_storage_max_power_dict_limits_none_max(context):
    """Covers dict output_active_power_limits with non-numeric max."""

    class Dummy:
        output_active_power_limits = {"max": "bad"}  # noqa: RUF012
        base_power = 1.0

    assert getters.get_storage_max_power(Dummy(), context).unwrap() == 0.0


def test_get_interface_min_max_flow_none_limits(context):
    """Covers None active_power_flow_limits in get_interface_min/max_flow."""

    class Dummy:
        active_power_flow_limits = None

    assert getters.get_interface_min_flow(Dummy(), context).unwrap() == 1e30
    assert getters.get_interface_max_flow(Dummy(), context).unwrap() == 1e30


def test_get_interface_min_max_flow_dict_limits(context):
    """Covers dict active_power_flow_limits branch."""

    class Dummy:
        active_power_flow_limits = {"min": -50.0, "max": 75.0}  # noqa: RUF012

    assert getters.get_interface_min_flow(Dummy(), context).unwrap() == -50.0
    assert getters.get_interface_max_flow(Dummy(), context).unwrap() == 75.0


def test_membership_node_child_zone_no_load_zone(context):
    """Covers branch where source bus has no load_zone."""
    node = PLEXOSNode(name="N1")
    bus = ACBus(name="N1", number=1)
    context.source_system.add_component(bus)
    result = getters.membership_node_child_zone(node, context)
    assert result.is_err()


def test_get_storage_charge_efficiency_dict(context):
    """Covers dict efficiency branch in get_storage_charge/discharge_efficiency."""

    class Dummy:
        efficiency = {"input": 0.88, "output": 0.77}  # noqa: RUF012

    assert getters.get_storage_charge_efficiency(Dummy(), context).unwrap() == 88.0
    assert getters.get_storage_discharge_efficiency(Dummy(), context).unwrap() == 77.0


def test_get_load_subtracter_with_value(context):
    """Covers get_load_subtracter when load_subtracter is set."""
    from infrasys.cost_curves import CostCurve, LinearCurve
    from r2x_sienna.models import RenewableDispatch
    from r2x_sienna.models.costs import RenewableGenerationCost

    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    context.source_system.add_component(bus)

    gen = RenewableDispatch(
        name="RD1",
        bus=bus,
        rating=100.0,
        active_power=50.0,
        reactive_power=0.0,
        base_power=100.0,
        prime_mover_type=PrimeMoversType.WT,
        operation_cost=RenewableGenerationCost(
            variable=CostCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS)
        ),
    )
    assert getters.get_load_subtracter(gen, context).unwrap() == 0.0


def test_get_thermal_mean_time_to_repair_with_value(context):
    """Covers get_thermal_mean_time_to_repair when value is set."""

    class Dummy:
        forced_outage_rate = None
        maintenance_rate = None
        mean_time_to_repair = 24.0

    assert getters.get_thermal_mean_time_to_repair(Dummy(), context).unwrap() == 24.0


def test_get_turbine_forced_outage_rate_with_value(context):
    """Covers get_turbine_forced_outage_rate when value is set."""

    class Dummy:
        forced_outage_rate = 0.05

    assert getters.get_turbine_forced_outage_rate(Dummy(), context).unwrap() == 0.05


def test_get_turbine_maintenance_rate_with_value(context):
    """Covers get_turbine_maintenance_rate when value is set."""

    class Dummy:
        maintenance_rate = 0.03

    assert getters.get_turbine_maintenance_rate(Dummy(), context).unwrap() == 0.03


def test_get_hydro_mean_time_to_repair_with_value(context):
    """Covers get_hydro_mean_time_to_repair when value is set."""

    class Dummy:
        mean_time_to_repair = 48.0

    assert getters.get_hydro_mean_time_to_repair(Dummy(), context).unwrap() == 48.0


def test_get_turbine_mean_time_to_repair_with_value(context):
    """Covers get_turbine_mean_time_to_repair when value is set."""

    class Dummy:
        mean_time_to_repair = 12.0

    assert getters.get_turbine_mean_time_to_repair(Dummy(), context).unwrap() == 12.0


def test_get_battery_outage_rates_with_values(context):
    """Covers battery outage getters when values are directly set."""

    class Dummy:
        forced_outage_rate = 0.02
        maintenance_rate = 0.01
        mean_time_to_repair = 8.0

    d = Dummy()
    assert getters.get_battery_forced_outage_rate(d, context).unwrap() == 0.02
    assert getters.get_battery_maintenance_rate(d, context).unwrap() == 0.01
    assert getters.get_battery_mean_time_to_repair(d, context).unwrap() == 8.0


def test_get_min_stable_level_dict_limits(context):
    """Covers dict active_power_limits branch in get_min_stable_level."""

    class Dummy:
        active_power_limits = {"min": 10.0, "max": 100.0}  # noqa: RUF012

    assert getters.get_min_stable_level(Dummy(), context).unwrap() == 10.0


def test_get_min_stable_level_negative_min(context):
    """Covers negative min clamped to 0.0 in get_min_stable_level."""

    class Dummy:
        active_power_limits = {"min": -5.0, "max": 100.0}  # noqa: RUF012

    assert getters.get_min_stable_level(Dummy(), context).unwrap() == 0.0


def test_get_reserve_duration_zero(context):
    """Covers get_reserve_duration with 0 sustained_time."""
    reserve = VariableReserve(
        name="R1",
        reserve_type=ReserveType.REGULATION,
        vors=1.0,
        direction="UP",
        requirement=50.0,
    )
    assert getters.get_reserve_duration(reserve, context).unwrap() == 3600.0
    assert getters.get_reserve_type(reserve, context).unwrap() == 3


def test_is_slack_bus_returns_result_int_type():
    from r2x_sienna.models.enums import ACBusTypes
    from r2x_sienna_to_plexos.getters import is_slack_bus

    class MockBus:
        bustype = ACBusTypes.SLACK

    class MockContext:
        pass

    result = is_slack_bus(MockBus(), MockContext())
    assert result.is_ok()
    assert result.unwrap() == 1


def test_is_slack_bus_returns_zero_for_non_slack():
    from r2x_sienna.models.enums import ACBusTypes
    from r2x_sienna_to_plexos.getters import is_slack_bus

    class MockBus:
        bustype = ACBusTypes.PV

    class MockContext:
        pass

    result = is_slack_bus(MockBus(), MockContext())
    assert result.is_ok()
    assert result.unwrap() == 0


def test_get_availability_returns_result_int_type():
    from r2x_sienna_to_plexos.getters import get_availability

    class MockComponent:
        units = 5

    result = get_availability(MockComponent(), None)
    assert result.is_ok()
    assert result.unwrap() == 5


def test_get_availability_defaults_to_one():
    from r2x_sienna_to_plexos.getters import get_availability

    class MockComponent:
        pass

    result = get_availability(MockComponent(), None)
    assert result.is_ok()
    assert result.unwrap() == 1


def test_getter_error_variant():
    from r2x_core import Err

    def failing_getter(component, ctx):
        return Err(ValueError("Test error"))

    result = failing_getter(None, None)
    assert result.is_err()
    assert isinstance(result.err(), ValueError)


def test_is_slack_bus_has_decorator():
    from r2x_core.getters import GETTER_REGISTRY

    assert "is_slack_bus" in GETTER_REGISTRY
    assert callable(GETTER_REGISTRY["is_slack_bus"])


def test_get_availability_has_decorator():
    from r2x_core.getters import GETTER_REGISTRY

    assert "get_availability" in GETTER_REGISTRY
    assert callable(GETTER_REGISTRY["get_availability"])


def test_get_max_capacity_scales_limits(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_max_capacity

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_max_capacity(source, context_with_thermal_generators)
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(90.0)


def test_get_min_stable_level_scales_limits(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_min_stable_level

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_min_stable_level(source, context_with_thermal_generators)
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(40.0)


def test_get_initial_generation_uses_base_power(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_initial_generation

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-vom")
    result = get_initial_generation(source, context_with_thermal_generators)
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(36.0)


def test_get_heat_rate_from_fuel_curve(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate, get_heat_rate_base

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    assert get_heat_rate(source, context_with_thermal_generators).unwrap() == pytest.approx(9.2)
    assert get_heat_rate_base(source, context_with_thermal_generators).unwrap() == pytest.approx(0.0)


def test_get_fuel_price_from_fuel_curve(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_fuel_price

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_fuel_price(source, context_with_thermal_generators)
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(2.4)


def test_get_mark_up_from_cost_curve(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_mark_up

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-vom")
    result = get_mark_up(source, context_with_thermal_generators)
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(14.0)


def test_get_heat_rate_quadratic_curve_returns_coefficients(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate, get_heat_rate_base, get_heat_rate_incr

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-quadratic")
    assert get_heat_rate(source, context_with_thermal_generators).unwrap() == pytest.approx(9.8)
    assert get_heat_rate_base(source, context_with_thermal_generators).unwrap() == pytest.approx(120.0)
    assert get_heat_rate_incr(source, context_with_thermal_generators).unwrap() == pytest.approx(0.015)


def test_get_heat_rate_multiband_returns_property(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate_incr, get_heat_rate_load_point

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-piecewise")
    load_prop = get_heat_rate_load_point(source, context_with_thermal_generators).unwrap()
    incr_prop = get_heat_rate_incr(source, context_with_thermal_generators).unwrap()
    assert hasattr(load_prop, "get_bands")
    assert load_prop.get_bands() == [1, 2]
    assert hasattr(incr_prop, "get_bands")
    assert incr_prop.get_bands() == [1, 2]


def test_get_mark_up_multiband_property(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_mark_up, get_mark_up_point

    source = context_with_thermal_generators.source_system.get_component(
        ThermalStandard, "thermal-markup-piecewise"
    )
    point_prop = get_mark_up_point(source, context_with_thermal_generators).unwrap()
    mark_prop = get_mark_up(source, context_with_thermal_generators).unwrap()
    assert point_prop.get_bands() == [1, 2]
    assert mark_prop.get_bands() == [1, 2]


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
    from r2x_sienna.models import HydroDispatch, HydroReservoir, HydroTurbine

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
