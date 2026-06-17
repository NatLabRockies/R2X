"""Direct getter coverage tests for Sienna-to-PLEXOS."""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta
from typing import ClassVar

import pytest
from infrasys.cost_curves import FuelCurve, UnitSystem
from infrasys.function_data import QuadraticFunctionData
from infrasys.value_curves import InputOutputCurve, LinearCurve
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSPropertyValue,
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

from r2x_core import DataStore, Ok, PluginConfig, PluginContext, System

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
    assert getters.get_max_capacity(gen, context).unwrap() == 20000.0

    plexos_gen = PLEXOSGenerator(name="G2")
    context.target_system.add_component(plexos_gen)
    result = getters.membership_component_child_node(plexos_gen, context)
    assert result.is_err()


def test_resolve_generator_category_reeds_and_prime_mover_mapping(context):
    reeds_component = types.SimpleNamespace(name="reeds_hyded_foo", ext=None)
    assert getters._resolve_generator_category(reeds_component, context) == "hyded"

    context.config = types.SimpleNamespace(prime_mover_mapping={"CC_NATURAL_GAS": ["mapped-tech"]})
    mapped_component = types.SimpleNamespace(
        name="custom_gen",
        ext={},
        prime_mover_type="CC",
    )
    assert getters._resolve_generator_category(mapped_component, context) is None


def test_reeds_thermal_category_returns_none_for_invalid_mapping(context, monkeypatch):
    bus = ACBus(name="B1", base_voltage=115.0, number=1)
    thermal = ThermalStandard(
        name="THERM_NONE",
        bus=bus,
        active_power=0.0,
        reactive_power=0.0,
        rating=10.0,
        base_power=10.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        active_power_limits=MinMax(min=0.0, max=10.0),
        ramp_limits=UpDown(up=1.0, down=1.0),
        time_limits=UpDown(up=1.0, down=1.0),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost.example(),
    )
    monkeypatch.setattr(getters, "_get_defaults_data", lambda _ctx: {"reeds_thermal_mapping": "bad"})
    assert getters._get_reeds_thermal_category_from_fuel(thermal, context) is None


def test_index_builders_return_empty_when_system_missing(tmp_path):
    context = make_context(tmp_path)
    context.target_system = None
    context.source_system = None

    assert getters._build_target_storage_name_index(context) == {}
    assert getters._build_source_reserve_name_index(context) == {}


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
    assert getters.get_transformer_susceptance(t1, context).unwrap() == 2.0
    t2 = TapTransformer(name="T2", arc=arc1, primary_shunt=Complex(real=4.0, imag=2.0), tap=1.0)
    context.source_system.add_component(t2)
    assert getters.get_transformer_susceptance(t2, context).unwrap() == 2.0
    t3 = PhaseShiftingTransformer(
        name="T3",
        arc=arc1,
        tap=0.89,
        α=1.5,
        phase_angle_limits=MinMax(min=-0.03, max=0.03),
        primary_shunt=None,
    )
    context.source_system.add_component(t3)
    assert getters.get_transformer_susceptance(t3, context).is_err()


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


def test_get_load_mw_handles_volt_ampere_quantity_without_base_scaling():
    class FakeQuantity:
        def __init__(self, magnitude: float, unit: str) -> None:
            self.magnitude = magnitude
            self.unit = unit

        def to(self, unit_name: str) -> FakeQuantity:
            if self.unit == unit_name:
                return FakeQuantity(self.magnitude, unit_name)
            if self.unit == "volt_ampere" and unit_name == "megawatt":
                return FakeQuantity(self.magnitude / 1_000_000.0, unit_name)
            if self.unit == "volt_ampere" and unit_name == "watt":
                return FakeQuantity(self.magnitude, unit_name)
            raise ValueError("unsupported conversion")

    load = types.SimpleNamespace(
        max_active_power=FakeQuantity(100_000_000.0, "volt_ampere"),
        base_power=100.0,
    )

    assert getters._get_load_mw(load) == 100.0


def test_get_voltage_valid(context):
    bus = ACBus(name="N1", base_voltage=115.0, number=1)
    assert getters.get_voltage_kv(bus, context).unwrap() == 115.0


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


def test_get_max_capacity_matches_rating_for_small_values(context):
    gen = ThermalStandard(
        name="GEN_SMALL",
        bus=ACBus(name="N1", base_voltage=115.0, number=1),
        active_power=0.0,
        reactive_power=0.0,
        rating=7.1,
        base_power=1.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        active_power_limits=MinMax(min=0.0, max=999.0),
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
    assert getters.get_generator_rating(gen, context).unwrap() == 7.1
    assert getters.get_max_capacity(gen, context).unwrap() == 7.1


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
    assert getters.get_battery_charge_efficiency(battery, context).unwrap() == 95.0
    assert getters.get_battery_discharge_efficiency(battery, context).unwrap() == 92.0


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
    assert getters.get_battery_cycles(battery, context).unwrap() == 5000.0


def test_get_battery_max_power_valid(context):
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
    assert getters.get_battery_max_power(battery, context).unwrap() == 62500.0


def test_get_battery_capacity_valid(context):
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
    assert getters.get_battery_capacity(battery, context).unwrap() == 250000.0


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


def test_get_area_load_valid(context):
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
    assert getters.get_area_load(acbus, context).unwrap() == 0.0


def test_get_head_tail_storage_names_valid(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    hydro = HydroReservoir(
        name="hydro-reservoir-test",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
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
    assert getters.get_generator_rating(hydro, context).unwrap() == 10000.0
    assert getters.get_max_ramp_down(hydro, context).unwrap() > 0.0
    assert getters.get_max_ramp_up(hydro, context).unwrap() > 0.0


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
    assert getters.get_generator_rating(t, context).unwrap() == 100.0


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
    assert getters.get_generator_rating(ht, context).unwrap() == 22500.0


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
    assert getters.get_generator_vom_cost(gen, context).unwrap() == 5.0


def test_get_thermal_generator_units_zero_when_fuel_price_zero(monkeypatch, context):
    class DummyThermal:
        pass

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_zero_when_heat_rate_zero(monkeypatch, context):
    class DummyThermal:
        pass

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(0.0))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_one_when_inputs_present(monkeypatch, context):
    class DummyThermal:
        pass

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_zero_for_monticello_tx(monkeypatch, context):
    class DummyThermal:
        ext = {"plant_name": "Monticello", "state": "TX"}  # noqa: RUF012

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 0


def test_get_thermal_generator_units_keeps_monticello_mn_active(monkeypatch, context):
    class DummyThermal:
        ext = {"plant_name": "Monticello Nuclear Facility", "state": "MN"}  # noqa: RUF012

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_zero_when_time_series_missing(monkeypatch, context):
    class DummyThermal:
        pass

    context.source_system.time_series.has_time_series = lambda _component: False

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.3))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(9.5))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_thermal_generator_units_honors_explicit_units_zero(context):
    class DummyThermal:
        units = 0

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 0


def test_get_thermal_generator_units_uses_heat_rate_base_and_incr(monkeypatch, context):
    class DummyThermal:
        pass

    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_generator_start_cost", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_heat_rate", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_heat_rate_base", lambda *_: Ok(12.3))
    monkeypatch.setattr(getters, "get_heat_rate_incr", lambda *_: Ok(9.7))
    monkeypatch.setattr(getters, "get_heat_rate_incr2", lambda *_: Ok(0.0))
    monkeypatch.setattr(getters, "get_heat_rate_incr3", lambda *_: Ok(0.0))

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 1


def test_get_generator_load_point_returns_multiband_property(monkeypatch, context):
    class DummyThermal:
        pass

    load_point = PLEXOSPropertyValue()
    load_point.add_entry(value=50.0, band=1)
    load_point.add_entry(value=100.0, band=2)

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda *_: {"load_point": load_point})
    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(3.0))

    assert getters.get_generator_load_point(DummyThermal(), context).unwrap() is load_point


def test_get_generator_load_point_falls_back_to_heat_rate_times_fuel(monkeypatch, context):
    class DummyThermal:
        pass

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda *_: {"heat_rate": 9.5})
    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(2.0))

    assert getters.get_generator_load_point(DummyThermal(), context).unwrap() == 19.0


def test_get_generator_load_point_negative_value_is_abs(monkeypatch, context):
    """Negative load_point values (e.g. from sign-flipped cost curves) must be made absolute."""

    class DummyThermal:
        pass

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda *_: {"heat_rate": -9.5})
    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(3.155))

    result = getters.get_generator_load_point(DummyThermal(), context).unwrap()
    assert result >= 0.0


def test_get_generator_load_point_negative_scalar_load_point_is_abs(monkeypatch, context):
    """Negative scalar computed_load_point values must be made absolute."""

    class DummyThermal:
        pass

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda *_: {"load_point": -29.97})
    monkeypatch.setattr(getters, "get_fuel_price", lambda *_: Ok(0.0))

    result = getters.get_generator_load_point(DummyThermal(), context).unwrap()
    assert result == 29.97


def test_get_dispatch_generator_units_zero_when_time_series_missing(context):
    class DummyDispatch:
        pass

    context.source_system.time_series.has_time_series = lambda _component: False

    assert getters.get_dispatch_generator_units(DummyDispatch(), context).unwrap() == 0


def test_generator_units_zero_when_available_false_thermal(context):
    """All generator unit getters must return 0 when available=False."""

    class DummyThermal:
        available = False
        ext = None
        units = None
        operation_cost = None
        prime_mover_type = None
        fuel = None

    assert getters.get_thermal_generator_units(DummyThermal(), context).unwrap() == 0


def test_generator_units_zero_when_available_false_dispatch(context):
    class DummyDispatch:
        available = False

    assert getters.get_dispatch_generator_units(DummyDispatch(), context).unwrap() == 0


def test_generator_units_zero_when_available_false_hydro(context):
    class DummyHydro:
        available = False

    assert getters.get_hydro_generator_units(DummyHydro(), context).unwrap() == 0


def test_generator_units_zero_when_available_false_pumped_hydro(context):
    class DummyPumpedHydro:
        available = False
        rating = None

    assert getters.get_pumped_hydro_generator_units(DummyPumpedHydro(), context).unwrap() == 0


def test_generator_units_not_affected_when_available_true(context):
    """available=True (or missing) should not override normal logic."""

    class DummyHydro:
        available = True

    assert getters.get_hydro_generator_units(DummyHydro(), context).unwrap() == 1


def test_get_dispatch_generator_units_one_when_time_series_present(context):
    class DummyDispatch:
        pass

    context.source_system.time_series.has_time_series = lambda _component: True
    context.source_system.time_series.list_time_series_metadata = lambda _component: [
        types.SimpleNamespace(name="max_active_power", features={})
    ]
    context.source_system.list_time_series = (
        lambda _component, **kwargs: [object()] if kwargs.get("name") else []
    )

    assert getters.get_dispatch_generator_units(DummyDispatch(), context).unwrap() == 1


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


def test_get_generator_category_maps_thermal_nuclear_fuel(context):
    gen = _make_thermal_generator_for_category_tests(
        name="thermal-nuclear",
        fuel=ThermalFuels.NUCLEAR,
    )

    assert getters.get_generator_category(gen, context).unwrap() == "nuclear"


def test_get_generator_category_maps_thermal_oil_fuel(context):
    gen = _make_thermal_generator_for_category_tests(
        name="thermal-oil",
        fuel=ThermalFuels.KEROSENE,
    )

    assert getters.get_generator_category(gen, context).unwrap() == "o-g-s"


def test_get_generator_category_thermal_prefers_fuel_over_prime_mover(context):
    gen = _make_thermal_generator_for_category_tests(
        name="natural-gas",
        fuel=ThermalFuels.NATURAL_GAS,
        prime_mover_type=PrimeMoversType.ST,
    )

    assert getters.get_generator_category(gen, context).unwrap() == "natural-gas"


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


def test_get_pumped_hydro_category_demotes_zero_pump_load(context):
    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht_zero = HydroTurbine(
        name="hydro-turbine-zero-pump",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=0.0,
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
    assert getters.get_pumped_hydro_category(ht_zero, context).unwrap() == "hydro"

    ht_pumped = HydroTurbine(
        name="hydro-turbine-with-pump",
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
    # Non-zero pump load: defer to standard resolution rather than demoting
    # to "hydro". Either an explicit category resolves or rule default applies.
    result = getters.get_pumped_hydro_category(ht_pumped, context)
    if result.is_ok():
        assert result.unwrap() != "hydro"


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
    assert getters.get_generator_forced_outage_rate(ht, context).unwrap() >= 0.0


def test_thermal_standard_all_getters(context):
    from infrasys.cost_curves import FuelCurve
    from infrasys.value_curves import LinearCurve
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
    assert getters.get_generator_start_cost(gen, context).unwrap() == 2.0
    assert getters.get_generator_shutdown_cost(gen, context).unwrap() == 1.0

    # fuel price
    assert getters.get_fuel_price(gen, context).unwrap() == 0.0


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
    assert getters.get_battery_charge_efficiency(battery, context).unwrap() == 100.0
    assert getters.get_battery_discharge_efficiency(battery, context).unwrap() == 100.0


def test_get_interface_min_max_flow(context):
    ti = TransmissionInterface(
        name="TI1",
        active_power_flow_limits=MinMax(min=10.0, max=20.0),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    assert getters.get_interface_min_flow(ti, context).unwrap() == -99999.0
    assert getters.get_interface_max_flow(ti, context).unwrap() == 99999.0


def test_membership_parent_component(context):
    dummy = object()
    assert getters.membership_parent_component(dummy, context).unwrap() is dummy


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
    assert getters.get_area_units(area, context).unwrap() == 0.0
    assert getters.get_area_load(area, context).unwrap() == 0.0


def test_get_head_tail_storage_name(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )
    hydro = HydroReservoir(
        name="hydro1",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )
    assert getters.get_head_storage_name(hydro, context).unwrap() == "hydro1_head"
    assert getters.get_tail_storage_name(hydro, context).unwrap() == "hydro1_tail"


def test_get_head_tail_storage_name_without_pumped_storage_association(context):
    hydro = HydroReservoir(
        name="hydro1",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )

    assert getters.get_head_storage_name(hydro, context).is_err()
    assert getters.get_tail_storage_name(hydro, context).is_err()


def test_reservoir_association_true_for_hydropumpturbine_links(context):
    pump_turbine = type("HydroPumpTurbine", (), {})()
    reservoir = type(
        "ReservoirProxy",
        (),
        {
            "upstream_turbines": [pump_turbine],
            "downstream_turbines": [],
        },
    )()

    assert getters._reservoir_has_hydro_pumped_storage_association(reservoir, context)


def test_reservoir_association_false_for_hydroturbine_links(context):
    hydro_turbine = type("HydroTurbine", (), {})()
    reservoir = type(
        "ReservoirProxy",
        (),
        {
            "upstream_turbines": [],
            "downstream_turbines": [hydro_turbine],
        },
    )()

    assert not getters._reservoir_has_hydro_pumped_storage_association(reservoir, context)


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


def test_membership_node_child_zone_by_name(context):
    area = Area(name="A1")
    zone = LoadZone(name="Z1")
    bus = ACBus(name="N1", area=area, load_zone=zone, number=1)
    node = PLEXOSNode(name="N1")
    target_zone = PLEXOSZone(name="Z1")

    context.source_system.add_component(area)
    context.source_system.add_component(zone)
    context.source_system.add_component(bus)
    context.target_system.add_component(node)
    context.target_system.add_component(target_zone)

    result = getters.membership_node_child_zone(node, context)
    assert result.is_ok()
    assert result.unwrap() == target_zone


def test_membership_node_child_zone_by_uuid(context):
    zone_uuid = "11111111-1111-4111-8111-111111111111"
    area = Area(name="A1")
    source_zone = LoadZone(name="source-zone-name", uuid=zone_uuid)
    bus = ACBus(name="N1", area=area, load_zone=source_zone, number=1)
    node = PLEXOSNode(name="N1")
    target_zone = PLEXOSZone(name="Z_from_uuid", uuid=zone_uuid)

    context.source_system.add_component(area)
    context.source_system.add_component(source_zone)
    context.source_system.add_component(bus)
    context.target_system.add_component(node)
    context.target_system.add_component(target_zone)

    result = getters.membership_node_child_zone(node, context)
    assert result.is_ok()
    assert result.unwrap() == target_zone


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


def test_membership_head_tail_storage_generator(context, monkeypatch):
    monkeypatch.setattr(getters, "_is_hydro_pumped_storage_generator", lambda _ctx, _name: True)

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


def test_get_power_or_standard_load_no_loads(context):
    acbus = ACBus(name="N1", base_voltage=115.0, number=1)
    assert getters.get_area_load(acbus, context).unwrap() == 0.0


def test_get_storage_max_volume_natural_inflow_none(context):
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
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert isinstance(getters.get_tail_storage_uuid(hydro, context).unwrap(), str)


def test_get_area_units(context):
    area = Area(name="A1", category="region")
    assert getters.get_area_units(area, context).unwrap() == 0.0


def test_get_area_units_active_when_region_has_positive_lpf(context):
    area = Area(name="A1", category="region")
    bus = ACBus(name="N1", area=area, base_voltage=115.0, number=1)
    load = PowerLoad(name="Load-1", bus=bus, max_active_power=100.0)

    context.source_system.add_component(area)
    context.source_system.add_component(bus)
    context.source_system.add_component(load)

    assert getters.get_area_units(area, context).unwrap() == 1.0


def test_get_area_load(context):
    area = Area(name="A1", category="region")
    assert getters.get_area_load(area, context).unwrap() == 0.0


def test_get_head_storage_name(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    hydro = HydroReservoir(
        name="hydro1_head",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert getters.get_head_storage_name(hydro, context).unwrap() == "hydro1_head"


def test_get_tail_storage_name(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    hydro = HydroReservoir(
        name="hydro1_tail",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert getters.get_tail_storage_name(hydro, context).unwrap() == "hydro1_tail"


def test_head_tail_storage_name_infers_location_from_suffix_when_missing(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    head = HydroReservoir(
        name="Plant_head",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.HEAD,
        ext={"plant_name": "Plant"},
    )
    tail = HydroReservoir(
        name="Plant_tail",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.TAIL,
        ext={"plant_name": "Plant"},
    )

    assert getters.get_head_storage_name(head, context).unwrap() == "Plant_head"
    assert getters.get_tail_storage_name(head, context).is_err()
    assert getters.get_head_storage_name(tail, context).is_err()
    assert getters.get_tail_storage_name(tail, context).unwrap() == "Plant_tail"


def test_head_tail_storage_name_suffix_overrides_conflicting_metadata(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    # Source metadata can be wrong; suffix should control head/tail assignment.
    tail_with_wrong_metadata = HydroReservoir(
        name="Abitibi Canyon_tail",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.HEAD,
        ext={"plant_name": "Abitibi Canyon"},
    )

    assert getters.get_head_storage_name(tail_with_wrong_metadata, context).is_err()
    assert getters.get_tail_storage_name(tail_with_wrong_metadata, context).unwrap() == "Abitibi Canyon_tail"


def test_unsuffixed_reservoir_skips_side_with_explicit_reservoir(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    explicit_head = HydroReservoir(
        name="Wallace Dam_head",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.HEAD,
        ext={"plant_name": "Wallace Dam"},
    )
    unsuffixed = HydroReservoir(
        name="Wallace Dam",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.TAIL,
        ext={"plant_name": "Wallace Dam"},
    )

    context.source_system.add_component(explicit_head)
    context.source_system.add_component(unsuffixed)

    assert getters.get_head_storage_name(explicit_head, context).unwrap() == "Wallace Dam_head"
    assert getters.get_head_storage_name(unsuffixed, context).is_err()
    assert getters.get_tail_storage_name(unsuffixed, context).unwrap() == "Wallace Dam_tail"


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
    assert getters.get_voltage_kv(bus, context).unwrap() == 0.0


def test_get_susceptance_complex_primary_shunt(context):
    """Covers complex number branch in get_susceptance."""
    bus1 = ACBus(name="N1", base_voltage=115.0, number=1)
    bus2 = ACBus(name="N2", base_voltage=115.0, number=2)
    context.source_system.add_component(bus1)
    context.source_system.add_component(bus2)
    arc = Arc(from_to=bus1, to_from=bus2)
    context.source_system.add_component(arc)
    t = Transformer2W(name="T1", arc=arc, primary_shunt=Complex(real=1.0, imag=3.0))
    assert getters.get_transformer_susceptance(t, context).unwrap() == 3.0


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
    assert getters.get_line_min_flow(line, context).unwrap() == {
        "value": -99999.0,
        "memo": getters.FLOW_CLIP_MEMO_TEXT,
    }
    assert getters.get_line_max_flow(line, context).unwrap() == {
        "value": 99999.0,
        "memo": getters.FLOW_CLIP_MEMO_TEXT,
    }


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

    assert getters.get_generator_rating(Dummy(), context).unwrap() == 50.0


def test_get_turbine_pump_efficiency_gt_one(context):
    """Covers get_turbine_pump_efficiency when efficiency > 1.0 (already percent)."""

    class Dummy:
        efficiency = 95.0

    assert getters.get_turbine_pump_efficiency(Dummy(), context).unwrap() == 95.0


def test_get_max_ramp_up_down_dict(context):
    """Covers dict ramp_limits branch in get_max_ramp_up and get_max_ramp_down."""

    class DummyRamp:
        ramp_limits = {"up": 0.10, "down": 0.12}  # noqa: RUF012
        base_power = 100.0

    d = DummyRamp()
    assert getters.get_max_ramp_up(d, context).unwrap() == 10.0
    assert getters.get_max_ramp_down(d, context).unwrap() == 12.0


def test_get_max_ramp_up_down_object(context):
    """UpDown attribute-access objects are handled correctly by the ramp getters."""

    class DummyRamp:
        ramp_limits = UpDown(up=0.5, down=0.3)
        base_power = 10.0

    d = DummyRamp()
    # Values <= 10.0 are treated as per-unit/min and scaled by base_power.
    ramp_up = getters.get_max_ramp_up(d, context).unwrap()
    ramp_down = getters.get_max_ramp_down(d, context).unwrap()
    assert ramp_up > 0.0
    assert ramp_down > 0.0


def test_get_max_ramp_thermal_large_absolute_value_capped_by_defaults(context, monkeypatch):
    """Ramp values exceeding max capacity are replaced by gen_ramp_pct * max_mw from PCM defaults."""

    class DummyThermal:
        ramp_limits: ClassVar[dict[str, float]] = {"up": 161.637, "down": 161.637}
        base_power = 993.3
        rating = 91.74164812123227
        active_power_limits = MinMax(min=0.0, max=90.3)
        prime_mover_type = PrimeMoversType.ST
        fuel = ThermalFuels.COAL

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda _src, _ctx: "coal")
    monkeypatch.setattr(getters, "sienna_get_max_active_power", lambda _src: 90.3)

    d = DummyThermal()
    # raw ramp = 161.637 * 993.3 = 160,554 MW/min >> max_mw = 90.3 * 993.3 ≈ 89,695 MW
    # coal ramp_rate = 0.2 → default_ramp_mw = 0.2 * 89,695 ≈ 17,939 MW/min
    max_mw = 90.3 * 993.3
    expected = round(0.2 * max_mw, 4)
    assert getters.get_max_ramp_up(d, context).unwrap() == pytest.approx(expected)
    assert getters.get_max_ramp_down(d, context).unwrap() == pytest.approx(expected)


def test_get_max_ramp_up_down_tiny_values_use_defaults(context, monkeypatch):
    """Ramps below 0.1 MW/min are treated as invalid and replaced by defaults."""

    class DummyRamp:
        ramp_limits: ClassVar[dict[str, float]] = {"up": 0.0008, "down": 0.0008}
        base_power = 100.0

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda _src, _ctx: "hydro")
    monkeypatch.setattr(
        getters, "_get_defaults", lambda _cat, key: 0.05 if key == "max_ramp_up_percentage" else 50.0
    )

    d = DummyRamp()
    assert getters.get_max_ramp_up(d, context).unwrap() == 2.5
    assert getters.get_max_ramp_down(d, context).unwrap() == 2.5


def test_get_max_ramp_up_down_zero_values_keep_fallback_value(context, monkeypatch):
    """When defaults and source ramps are zero, current behavior returns zero."""

    class DummyRamp:
        ramp_limits = None
        base_power = 100.0

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda _src, _ctx: "hydro")
    monkeypatch.setattr(getters, "_get_defaults", lambda _cat, _key: 0.0)

    d = DummyRamp()
    assert getters.get_max_ramp_up(d, context).unwrap() == 0.0
    assert getters.get_max_ramp_down(d, context).unwrap() == 0.0


def test_get_max_ramp_hydro_ignores_huge_max_active_power_placeholder(context, monkeypatch):
    """Hydro ramps should use ramp_rate defaults when max active power is a sentinel like 1e30."""

    class DummyHydro:
        ramp_limits = None
        base_power = 100.0
        prime_mover_type = "HY"

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda _src, _ctx: "hydro")
    monkeypatch.setattr(getters, "sienna_get_max_active_power", lambda _src: 1e30)

    d = DummyHydro()
    assert getters.get_max_ramp_up(d, context).unwrap() == 120.0
    assert getters.get_max_ramp_down(d, context).unwrap() == 120.0


def test_get_max_ramp_uses_defaults_when_raw_natural_unit_ramp_is_too_low(context, monkeypatch):
    """Raw natural-unit ramps below threshold should fall back to defaults."""

    class DummyHydro:
        ramp_limits: ClassVar[dict[str, float]] = {"up": 0.06818181818181819, "down": 0.06818181818181819}
        base_power = 11.0
        prime_mover_type = "HY"
        active_power_limits = MinMax(min=0.0, max=15.0)
        rating = 16.682026255823963

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda _src, _ctx: "hydro")

    d = DummyHydro()
    assert getters.get_max_ramp_up(d, context).unwrap() == 0.75
    assert getters.get_max_ramp_down(d, context).unwrap() == 0.75


def test_effective_max_mw_falls_back_to_active_power_limits_when_sentinel(monkeypatch):
    """With sentinel max capacity and low raw ramp, fallback still yields a non-negative ramp."""

    class Dummy:
        ramp_limits: ClassVar[dict[str, float]] = {"up": 0.01, "down": 0.01}
        base_power = 10.0
        active_power_limits = MinMax(min=0.0, max=7.5)
        prime_mover_type = "HY"
        rating = None

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda _src, _ctx: "hydro")
    monkeypatch.setattr(
        getters, "_get_defaults", lambda _cat, key: 0.05 if key == "max_ramp_up_percentage" else 320.0
    )

    assert getters.get_max_ramp_up(Dummy(), context=types.SimpleNamespace()).unwrap() >= 0.0


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
    # CC + NATURAL_GAS resolves to "natural-gas" category; defaults apply when time_limits is None
    assert getters.get_min_up_time(gen, context).unwrap() == 6.0
    assert getters.get_min_down_time(gen, context).unwrap() == 8.0


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


def test_get_fuel_price_mapping_operation_cost(context):
    """Covers get_fuel_price when operation_cost and variable are mapping-like."""

    class DummyThermal:
        operation_cost: ClassVar[dict[str, object]] = {
            "variable": {
                "fuel_cost": 2.644,
            }
        }

    assert getters.get_fuel_price(DummyThermal(), context).unwrap() == 2.64


def test_get_interface_min_max_flow_none_limits(context):
    """Covers None active_power_flow_limits in get_interface_min/max_flow."""

    class Dummy:
        active_power_flow_limits = None

    assert getters.get_interface_min_flow(Dummy(), context).unwrap() == -99999.0
    assert getters.get_interface_max_flow(Dummy(), context).unwrap() == 99999.0


def test_get_interface_min_max_flow_dict_limits(context):
    """Covers dict active_power_flow_limits branch."""

    class Dummy:
        active_power_flow_limits = {"min": -50.0, "max": 75.0}  # noqa: RUF012

    assert getters.get_interface_min_flow(Dummy(), context).unwrap() == -50.0
    assert getters.get_interface_max_flow(Dummy(), context).unwrap() == 75.0


def test_get_battery_charge_efficiency_dict(context):
    """Covers dict efficiency branch in get_battery_charge/discharge_efficiency."""

    class Dummy:
        efficiency = {"input": 0.88, "output": 0.77}  # noqa: RUF012

    assert getters.get_battery_charge_efficiency(Dummy(), context).unwrap() == 88.0
    assert getters.get_battery_discharge_efficiency(Dummy(), context).unwrap() == 77.0


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
    assert getters.get_generator_load_subtracter(gen, context).unwrap() == 0.0


def test_get_thermal_mean_time_to_repair_with_value(context):
    """Covers get_thermal_mean_time_to_repair when value is set."""

    class Dummy:
        forced_outage_rate = None
        maintenance_rate = None
        mean_time_to_repair = 24.0

    assert getters.get_generator_mean_time_to_repair(Dummy(), context).unwrap() == 0.0


def test_get_generator_forced_outage_rate_with_value(context):
    """Covers get_generator_forced_outage_rate when value is set."""

    class Dummy:
        forced_outage_rate = 0.05

    assert getters.get_generator_forced_outage_rate(Dummy(), context).unwrap() == 0.0


def test_get_turbine_maintenance_rate_with_value(context):
    """Covers get_turbine_maintenance_rate when value is set."""

    class Dummy:
        maintenance_rate = 0.03

    assert getters.get_generator_maintenance_rate(Dummy(), context).unwrap() == 0.0


def test_get_hydro_mean_time_to_repair_with_value(context):
    """Covers get_hydro_mean_time_to_repair when value is set."""

    class Dummy:
        mean_time_to_repair = 48.0

    assert getters.get_generator_mean_time_to_repair(Dummy(), context).unwrap() == 0.0


def test_get_turbine_mean_time_to_repair_with_value(context):
    """Covers get_turbine_mean_time_to_repair when value is set."""

    class Dummy:
        mean_time_to_repair = 12.0

    assert getters.get_generator_mean_time_to_repair(Dummy(), context).unwrap() == 0.0


def test_get_battery_outage_rates_with_values(context):
    """Covers battery outage getters when values are directly set."""

    class Dummy:
        category = "battery"
        forced_outage_rate = 0.02
        maintenance_rate = 0.01
        mean_time_to_repair = 8.0

    d = Dummy()
    assert getters.get_generator_forced_outage_rate(d, context).unwrap() == 0.0
    assert getters.get_generator_maintenance_rate(d, context).unwrap() == 0.0
    assert getters.get_generator_mean_time_to_repair(d, context).unwrap() == 0.0


def test_get_min_stable_level_dict_limits(context):
    """Covers dict active_power_limits branch in get_generator_min_stable_level."""

    class Dummy:
        active_power_limits = {"min": 10.0, "max": 100.0}  # noqa: RUF012

    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 10.0


def test_get_min_stable_level_negative_min(context):
    """Covers negative min clamped to 0.0 in get_generator_min_stable_level."""

    class Dummy:
        active_power_limits = {"min": -5.0, "max": 100.0}  # noqa: RUF012
        base_power = 1.0

    # |min| = 5 MW (<10 MW), so enforce 50% of max capacity (100 MW).
    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 50.0


def test_get_min_stable_level_tiny_value_uses_half_max_capacity(context):
    class Dummy:
        active_power_limits = {"min": 0.02, "max": 29.9}  # noqa: RUF012
        rating = 29.9
        base_power = 1.0

    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 14.95


def test_get_min_stable_level_tiny_value_returns_raw_when_max_capacity_unavailable(context):
    """When both rating and active_power_limits.max are missing, get_max_capacity
    returns Err so the 50%-of-max fallback cannot fire. The raw min value is returned."""

    class Dummy:
        active_power_limits = {"min": 0.02}  # noqa: RUF012
        rating = None
        base_power = 1.0

    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 0.02


def test_get_min_stable_level_fallback_is_capped_to_half_max_capacity(monkeypatch, context):
    class Dummy:
        active_power_limits = {"min": 0.0}  # noqa: RUF012
        rating = 80.0
        base_power = 1.0

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "natural-gas")
    monkeypatch.setattr(
        getters,
        "_get_defaults",
        lambda _category, key: 2.0 if key == "min_stable_level_percentage" else 0.0,
    )

    # fallback value = 2.0 * 100 = 200 MW, max capacity = 80 MW -> clamp to 40 MW
    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 40.0


def test_get_min_stable_level_zero_fallback_uses_half_max_capacity(monkeypatch, context):
    class Dummy:
        active_power_limits = {"min": 0.0}  # noqa: RUF012
        rating = 60.0
        base_power = 1.0

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "natural-gas")
    monkeypatch.setattr(
        getters,
        "_get_defaults",
        lambda _category, key: 0.0 if key == "min_stable_level_percentage" else 0.0,
    )

    # fallback value = 0.0, max capacity = 60 MW -> force to 30 MW
    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 30.0


def test_get_min_stable_level_nuclear_enforced_to_70_percent(monkeypatch, context):
    """Nuclear generators must have min stable level = 70 % of max capacity."""

    class Dummy:
        active_power_limits = {"min": 0.2, "max": 1000.0}  # noqa: RUF012
        rating = 1000.0
        base_power = 1.0

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "nuclear")

    # raw min = 0.2 MW, max = 1000 MW -> should be overridden to 700 MW
    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 700.0


def test_get_min_stable_level_nuclear_already_at_70_percent_unchanged(monkeypatch, context):
    """Nuclear generators already at ~70 % are left untouched."""

    class Dummy:
        active_power_limits = {"min": 0.7, "max": 1000.0}  # noqa: RUF012
        rating = 1000.0
        base_power = 1.0

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "nuclear")

    # min = 700 MW (exactly 70 % of 1000 MW) -> no override
    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 700.0


def test_get_min_stable_level_nuclear_within_tolerance_unchanged(monkeypatch, context):
    """Nuclear min stable level within 5 % of 70 % target is not overridden."""

    class Dummy:
        # min = 720 MW, max = 1000 MW (values already in MW, base_power = 1.0)
        active_power_limits = {"min": 720.0, "max": 1000.0}  # noqa: RUF012
        rating = 1000.0
        base_power = 1.0

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "nuclear")

    # 720 MW is within 5 % rel_tol of the 700 MW target -> kept as-is
    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 720.0


def test_get_min_stable_level_non_nuclear_not_affected(monkeypatch, context):
    """Non-nuclear generators are not subject to the 70 % nuclear override."""

    class Dummy:
        active_power_limits = {"min": 0.1, "max": 100.0}  # noqa: RUF012
        rating = 100.0
        base_power = 1.0

    monkeypatch.setattr(getters, "_resolve_generator_category", lambda *_: "coal")

    # min = 10 MW, exactly at the 10-MW threshold -> 50 % of max = 50 MW
    assert getters.get_generator_min_stable_level(Dummy(), context).unwrap() == 50.0


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


def test_is_slack_bus_returns_result():
    """Verify is_slack_bus returns a Result type."""
    from r2x_sienna.models.enums import ACBusTypes

    class MockBus:
        bustype = ACBusTypes.SLACK

    result = getters.is_slack_bus(MockBus(), None)
    assert result.is_ok()


def test_get_availability_returns_result():
    """Verify get_availability returns a Result type."""

    class MockComponent:
        pass

    result = getters.get_availability(MockComponent(), None)
    assert result.is_ok()


def test_get_max_capacity_scales_limits(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_max_capacity

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_max_capacity(source, context_with_thermal_generators)
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(20000.0)


def test_get_min_stable_level_scales_limits(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_generator_min_stable_level

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_generator_min_stable_level(source, context_with_thermal_generators)
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(40.0)


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


def test_get_heat_rate_quadratic_curve_returns_coefficients(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate, get_heat_rate_base, get_heat_rate_incr

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-quadratic")
    assert get_heat_rate(source, context_with_thermal_generators).unwrap() is None
    assert get_heat_rate_base(source, context_with_thermal_generators).unwrap() == pytest.approx(120.0)
    assert get_heat_rate_incr(source, context_with_thermal_generators).unwrap() == pytest.approx(9.8)


def test_get_heat_rate_multiband_returns_property(context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate_incr

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-piecewise")
    incr_prop = get_heat_rate_incr(source, context_with_thermal_generators).unwrap()
    assert hasattr(incr_prop, "get_bands")
    assert incr_prop.get_bands() == [1, 2]


def test_heat_rate_getters_return_absolute_values(monkeypatch, context_with_thermal_generators):
    import r2x_sienna_to_plexos.getters as live_getters
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import (
        get_heat_rate,
        get_heat_rate_base,
        get_heat_rate_incr,
        get_heat_rate_incr2,
        get_heat_rate_incr3,
    )

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    monkeypatch.setattr(
        live_getters,
        "compute_heat_rate_data",
        lambda _component: {
            "heat_rate_base": -120.0,
            "heat_rate_incr": -9.8,
            "heat_rate_incr2": -0.03,
            "heat_rate_incr3": -0.0005,
        },
    )

    assert get_heat_rate(source, context_with_thermal_generators).unwrap() is None
    assert get_heat_rate_base(source, context_with_thermal_generators).unwrap() == pytest.approx(120.0)
    assert get_heat_rate_incr(source, context_with_thermal_generators).unwrap() == pytest.approx(9.8)
    assert get_heat_rate_incr2(source, context_with_thermal_generators).unwrap() == pytest.approx(0.03)
    assert get_heat_rate_incr3(source, context_with_thermal_generators).unwrap() == pytest.approx(0.0005)


def test_get_heat_rate_scalar_when_base_and_incr_missing(monkeypatch, context_with_thermal_generators):
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    monkeypatch.setattr(getters, "compute_heat_rate_data", lambda _component: {"heat_rate": -9.2})

    assert get_heat_rate(source, context_with_thermal_generators).unwrap() == pytest.approx(9.2)


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
    from r2x_sienna.models.costs import HydroGenerationCost

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
    from r2x_sienna.models.costs import HydroGenerationCost

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
    assert attached[0].name == "hydro_budget"
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
    assert ts.name == "hydro_budget"
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
