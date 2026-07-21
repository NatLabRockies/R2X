"""Direct getter coverage tests for Sienna-to-PLEXOS."""

from __future__ import annotations

import types

import pytest
from infrasys.cost_curves import FuelCurve, UnitSystem
from infrasys.function_data import QuadraticFunctionData
from infrasys.value_curves import InputOutputCurve, LinearCurve
from r2x_plexos.models import (
    PLEXOSGenerator,
)
from r2x_sienna.models import (
    ACBus,
    Arc,
    EnergyReservoirStorage,
    HydroReservoir,
    HydroTurbine,
    Line,
    MinMax,
    PhaseShiftingTransformer,
    PowerLoad,
    TapTransformer,
    ThermalStandard,
    Transformer2W,
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
    PrimeMoversType,
    ReserveType,
    ReservoirDataType,
    ReservoirLocation,
    StorageTechs,
    ThermalFuels,
)
from r2x_sienna.models.named_tuples import Complex, FromTo_ToFrom, InputOutput
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
