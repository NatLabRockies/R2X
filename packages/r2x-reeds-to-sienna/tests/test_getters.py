"""Direct getter coverage tests for ReEDS-to-Sienna."""

from __future__ import annotations

import math

import pytest
from infrasys.cost_curves import FuelCurve, LinearCurve
from r2x_reeds.models import (
    ReEDSDataCenterDemand,
    ReEDSDemand,
    ReEDSElectrolyzerDemand,
    ReEDSHydroGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSReserve,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSTransmissionLine,
    ReEDSVariableGenerator,
)
from r2x_reeds_to_sienna import getters
from r2x_sienna.models import ACBus, Arc, Area
from r2x_sienna.models.costs import ThermalGenerationCost
from r2x_sienna.models.enums import ACBusTypes, PrimeMoversType, StorageTechs, ThermalFuels
from r2x_sienna.models.named_tuples import MinMax
from r2x_sienna.units import Voltage

from r2x_core import DataStore, PluginConfig, PluginContext, System, UnitSystem


def make_context(tmp_path) -> PluginContext:
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    return PluginContext(config=config, store=store)


def test_basic_getters_return_values(tmp_path) -> None:
    """Invoke getters directly to ensure coverage and registration."""

    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = ReEDSRegion(name="p1")
    context.source_system.add_component(region)

    region2 = ReEDSRegion(name="p2")
    context.source_system.add_component(region2)

    region_non_numeric = ReEDSRegion(name="otx")
    context.source_system.add_component(region_non_numeric)

    area = Area(name="p1", category="region")
    context.target_system.add_component(area)

    area2 = Area(name="p2", category="region")
    context.target_system.add_component(area2)

    bus = ACBus(name="p1_BUS", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus)

    bus2 = ACBus(name="p2_BUS", area=area2, number=2, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus2)

    thermal = ReEDSThermalGenerator(
        name="p1_THERM",
        region=region,
        technology="coal-new",
        capacity=10.0,
        heat_rate=7.5,
        fuel_type="coal",
    )
    context.source_system.add_component(thermal)

    variable = ReEDSVariableGenerator(
        name="p1_WIND",
        region=region,
        technology="wind-ons",
        capacity=5.0,
    )
    context.source_system.add_component(variable)

    variable_pv = ReEDSVariableGenerator(
        name="p1_DISTPV",
        region=region,
        technology="distpv",
        capacity=3.0,
    )
    context.source_system.add_component(variable_pv)

    hydro = ReEDSHydroGenerator(
        name="p1_HYDRO",
        region=region,
        technology="hydro",
        capacity=8.0,
        is_dispatchable=True,
        ramp_rate=10.0,
    )
    context.source_system.add_component(hydro)

    storage = ReEDSStorage(
        name="p1_STORE",
        region=region,
        technology="battery_4",
        capacity=4.0,
        storage_duration=2.0,
        round_trip_efficiency=0.9,
    )
    context.source_system.add_component(storage)

    demand = ReEDSDemand(name="p1_LOAD", region=region, max_active_power=3.0)
    context.source_system.add_component(demand)

    interface = ReEDSInterface(name="IFACE", from_region=region, to_region=region2)
    context.source_system.add_component(interface)

    reserve = ReEDSReserve(
        name="REG_UP",
        reserve_type="REGULATION",
        direction="Up",
        time_frame=300.0,
        duration=3600.0,
    )
    context.source_system.add_component(reserve)

    line = ReEDSTransmissionLine(
        name="p1_p2_ac",
        interface=interface,
        max_active_power={"from_to": 100.0, "to_from": 100.0},
    )
    context.source_system.add_component(line)

    # Test thermal generator getters
    assert getters.unique_component_name(thermal, context).unwrap() == "p1_THERM"
    assert getters.get_capacity_as_rating(thermal, context).unwrap() == 10.0
    assert getters.get_capacity_as_base_power(thermal, context).unwrap() == 10.0
    limits = getters.get_active_power_limits(thermal, context).unwrap()
    assert limits.max == 10.0
    assert limits.min == pytest.approx(0.4 * 10.0)  # min_stable_level_percentage from defaults.json
    assert getters.get_thermal_operation_cost(thermal, context).unwrap() is not None
    assert getters.get_prime_mover(thermal, context).unwrap() == PrimeMoversType.ST
    assert getters.get_fuel_enum(thermal, context).unwrap() == ThermalFuels.COAL

    # Test renewable generator getters
    assert getters.get_renewable_operation_cost(variable, context).unwrap() is not None
    assert getters.get_renewable_prime_mover(variable, context).unwrap() == PrimeMoversType.WT
    assert getters.get_renewable_prime_mover(variable_pv, context).unwrap() == PrimeMoversType.PVe
    assert getters.get_zero_active_power(variable, context).unwrap() == 0.0
    assert getters.get_zero_reactive_power(variable, context).unwrap() == 0.0
    assert getters.get_default_must_run(variable, context).unwrap() is False
    assert getters.get_default_status(variable, context).unwrap() is True
    assert getters.get_default_time_at_status(variable, context).unwrap() == 0.0

    # Test region/bus getters
    assert getters.get_area_for_region(region, context).unwrap() == area
    assert getters.bus_name_from_region(region, context).unwrap() == "p1_BUS"
    assert getters.base_voltage_default(region, context).unwrap() == 115.0
    assert getters.bustype_default(region, context).unwrap() == ACBusTypes.PQ
    assert getters.get_bus_for_region(thermal, context).unwrap() == bus
    assert getters.get_bus_number(region, context).unwrap() == 1
    assert getters.get_bus_number(region_non_numeric, context).unwrap() == 999999
    assert getters.get_area_category(region, context).unwrap() == "region"

    # Test demand getters
    assert getters.demand_max_active_power(demand, context).unwrap() == 3.0
    assert getters.demand_max_reactive_power(demand, context).unwrap() == 0.0
    assert getters.get_load_base_power(demand, context).unwrap() == 100.0

    # Test hydro getters
    assert getters.hydro_rating(hydro, context).unwrap() == 8.0
    assert getters.hydro_operation_cost(hydro, context).unwrap() is not None
    hydro_limits = getters.hydro_active_power_limits(hydro, context).unwrap()
    assert hydro_limits.max == 8.0
    assert hydro_limits.min == 0.0
    ramp_limits = getters.hydro_ramp_limits(hydro, context).unwrap()
    assert ramp_limits.up == pytest.approx(8.0 * 10.0 / 60.0)  # cap * rate / 60
    assert ramp_limits.down == pytest.approx(8.0 * 10.0 / 60.0)
    time_limits = getters.hydro_time_limits(hydro, context).unwrap()
    assert time_limits.up == 0.0
    assert time_limits.down == 0.0

    # Test storage getters
    assert getters.storage_rating(storage, context).unwrap() == 4.0
    assert getters.storage_capacity_mwh(storage, context).unwrap() == 8.0
    storage_limits = getters.storage_level_limits(storage, context).unwrap()
    assert storage_limits.min == 0.0
    assert storage_limits.max == 1.0
    power_limits = getters.storage_power_limits(storage, context).unwrap()
    assert power_limits.max == 4.0
    efficiency = getters.storage_efficiency(storage, context).unwrap()
    assert efficiency.output == pytest.approx(math.sqrt(0.9))  # sqrt(rte)
    assert efficiency.input == pytest.approx(math.sqrt(0.9))  # symmetric
    assert getters.storage_tech(storage, context).unwrap() == StorageTechs.LIB
    assert getters.storage_prime_mover(storage, context).unwrap() == PrimeMoversType.ES
    assert getters.storage_initial_level(storage, context).unwrap() == 0.0
    assert getters.storage_conversion_factor(storage, context).unwrap() == 1.0

    # Test interface getters
    assert getters.get_area_from(interface, context).unwrap() == area
    assert getters.get_area_to(interface, context).unwrap() == area2
    flow_limits = getters.get_interface_flow_limits(interface, context).unwrap()
    assert flow_limits.from_to == 0.0
    assert getters.get_zero_flow(interface, context).unwrap() == 0.0

    # Test reserve getters
    assert getters.get_reserve_type(reserve, context).unwrap() == "REGULATION"
    assert getters.get_reserve_direction(reserve, context).unwrap() == "UP"
    assert getters.get_reserve_requirement(reserve, context).unwrap() == 0.0
    assert getters.get_reserve_time_frame(reserve, context).unwrap() == 300.0
    assert getters.get_reserve_sustained_time(reserve, context).unwrap() == 3600.0
    assert getters.get_reserve_max_output_fraction(reserve, context).unwrap() == 1.0
    assert getters.get_reserve_max_participation_factor(reserve, context).unwrap() == 1.0
    assert getters.get_reserve_deployed_fraction(reserve, context).unwrap() == 1.0

    # Test line getters
    assert getters.get_line_rating(line, context).unwrap() == 100.0
    assert getters.get_line_active_power_flow(line, context).unwrap() == 100.0
    assert getters.get_line_reactive_power_flow(line, context).unwrap() == 0.0
    assert getters.get_line_resistance(line, context).unwrap() == 0.0
    assert getters.get_line_reactance(line, context).unwrap() == 0.0
    susceptance = getters.get_line_susceptance(line, context).unwrap()
    assert susceptance.from_to == 0.0
    conductance = getters.get_line_conductance(line, context).unwrap()
    assert conductance.from_to == 0.0
    angle_limits = getters.get_line_angle_limits(line, context).unwrap()
    assert angle_limits.min == -90.0
    assert angle_limits.max == 90.0

    # Test arc getter
    arc = getters.get_arc_for_line(line, context).unwrap()
    assert isinstance(arc, Arc)
    assert arc.from_to == bus or arc.from_to == bus2
    assert arc.to_from == bus or arc.to_from == bus2


def test_unique_component_name_collision(tmp_path) -> None:
    """Test that unique_component_name handles name collisions."""
    from r2x_sienna.models import ThermalStandard

    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = ReEDSRegion(name="p1")
    area = Area(name="p1", category="region")
    context.target_system.add_component(area)  # Add area first

    bus = ACBus(name="p1_BUS", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus)

    existing = ThermalStandard(
        name="COAL_1",
        bus=bus,
        active_power=0.0,
        reactive_power=0.0,
        must_run=1,
        status=True,
        time_at_status=0.0,
        operation_cost=ThermalGenerationCost(
            fixed=0.0,
            shut_down=0.0,
            start_up=0.0,
            variable=FuelCurve(
                value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS, fuel_cost=0.0
            ),
        ),
        active_power_limits=MinMax(min=0.0, max=100.0),
        rating=100.0,
        base_power=100.0,
        prime_mover_type=PrimeMoversType.ST,
        fuel=ThermalFuels.COAL,
    )
    context.target_system.add_component(existing)

    component = ReEDSThermalGenerator(
        name="COAL_1",
        region=region,
        technology="coal",
        capacity=50.0,
        heat_rate=9.0,
        fuel_type="coal",
    )

    # Should return "COAL_1_1" to avoid collision
    unique_name = getters.unique_component_name(component, context).unwrap()
    assert unique_name == "COAL_1_1"


def test_bus_number_with_z_prefix(tmp_path) -> None:
    """Test bus number extraction for z-prefixed regions."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = ReEDSRegion(name="z122")
    result = getters.get_bus_number(region, context).unwrap()
    assert result == 122


def test_get_gen_services_all_generator_types(tmp_path) -> None:
    """get_gen_services must work for all generator types, not just thermal.

    Regression test: previously only get_thermal_services existed; renewable,
    hydro, and storage generators had no services getter so they could never
    participate in reserves.
    """
    from r2x_sienna.models import VariableReserve

    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = ReEDSRegion(name="p1")
    area = Area(name="p1", category="region")
    context.target_system.add_component(area)
    bus = ACBus(name="p1_BUS", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus)

    # Add a VariableReserve to the target system
    reserve = VariableReserve(
        name="SPIN_UP",
        available=True,
        reserve_type="SPINNING",
        direction="UP",
        requirement=0.05,
        time_frame=300.0,
        sustained_time=3600.0,
        max_output_fraction=1.0,
        max_participation_factor=1.0,
        deployed_fraction=1.0,
    )
    context.target_system.add_component(reserve)

    reserve_ext = {"reserves": ["SPIN_UP"]}

    thermal = ReEDSThermalGenerator(
        name="p1_THERM",
        region=region,
        technology="coal-new",
        capacity=10.0,
        heat_rate=7.5,
        fuel_type="coal",
        ext=reserve_ext,
    )
    variable = ReEDSVariableGenerator(
        name="p1_WIND",
        region=region,
        technology="wind-ons",
        capacity=5.0,
        ext=reserve_ext,
    )
    hydro = ReEDSHydroGenerator(
        name="p1_HYDRO",
        region=region,
        technology="hydro",
        capacity=8.0,
        is_dispatchable=True,
        ext=reserve_ext,
    )
    storage = ReEDSStorage(
        name="p1_STORE",
        region=region,
        technology="battery_4",
        capacity=4.0,
        storage_duration=2.0,
        round_trip_efficiency=0.9,
        ext=reserve_ext,
    )

    # All generator types should resolve the reserve
    for component in (thermal, variable, hydro, storage):
        services = getters.get_gen_services(component, context).unwrap()
        assert len(services) == 1, f"{type(component).__name__} should have 1 service"
        assert services[0] is reserve, f"{type(component).__name__} service should be the VariableReserve"

    # Components without reserves return an empty list
    no_reserve = ReEDSVariableGenerator(
        name="p1_SOLAR",
        region=region,
        technology="upv",
        capacity=2.0,
    )
    assert getters.get_gen_services(no_reserve, context).unwrap() == []

    # Unknown reserve names are silently skipped
    partial_ext = ReEDSVariableGenerator(
        name="p1_WIND2",
        region=region,
        technology="wind-ons",
        capacity=3.0,
        ext={"reserves": ["SPIN_UP", "NONEXISTENT_RESERVE"]},
    )
    partial = getters.get_gen_services(partial_ext, context).unwrap()
    assert partial == [reserve]


def test_get_gen_services_resolves_non_spinning_reserve(tmp_path) -> None:
    """get_gen_services must attach VariableReserveNonSpinning, not silently drop it.

    Regression: the original implementation only searched VariableReserve, so a
    generator referencing a NON_SPINNING reserve would get an empty services list
    even after the reserve was translated.
    """
    from r2x_sienna.models import VariableReserveNonSpinning

    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = ReEDSRegion(name="p1")
    area = Area(name="p1", category="region")
    context.target_system.add_component(area)
    bus = ACBus(name="p1_BUS", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus)

    non_spin = VariableReserveNonSpinning(
        name="NON_SPIN_UP",
        available=True,
        requirement=0.03,
        time_frame=600.0,
        sustained_time=1800.0,
        max_output_fraction=1.0,
        max_participation_factor=1.0,
        deployed_fraction=1.0,
    )
    context.target_system.add_component(non_spin)

    ext = {"reserves": ["NON_SPIN_UP"]}

    for component in (
        ReEDSThermalGenerator(
            name="THERM",
            region=region,
            technology="coal",
            capacity=100.0,
            heat_rate=7.5,
            fuel_type="coal",
            ext=ext,
        ),
        ReEDSVariableGenerator(name="WIND", region=region, technology="wind-ons", capacity=50.0, ext=ext),
        ReEDSHydroGenerator(
            name="HYDRO", region=region, technology="hydro", capacity=80.0, is_dispatchable=True, ext=ext
        ),
        ReEDSStorage(
            name="BATT",
            region=region,
            technology="battery_4",
            capacity=40.0,
            storage_duration=4.0,
            round_trip_efficiency=0.9,
            ext=ext,
        ),
    ):
        services = getters.get_gen_services(component, context).unwrap()
        assert (
            len(services) == 1
        ), f"{type(component).__name__}: expected 1 NON_SPINNING service, got {len(services)}"
        assert (
            services[0] is non_spin
        ), f"{type(component).__name__}: service should be the VariableReserveNonSpinning instance"

    # A mix of spinning + non-spinning reserves both resolve correctly
    from r2x_sienna.models import VariableReserve

    spin = VariableReserve(
        name="SPIN_UP",
        available=True,
        reserve_type="SPINNING",
        direction="UP",
        requirement=0.05,
        time_frame=300.0,
        sustained_time=3600.0,
        max_output_fraction=1.0,
        max_participation_factor=1.0,
        deployed_fraction=1.0,
    )
    context.target_system.add_component(spin)

    mixed = ReEDSStorage(
        name="BATT2",
        region=region,
        technology="battery_4",
        capacity=20.0,
        storage_duration=2.0,
        round_trip_efficiency=0.95,
        ext={"reserves": ["SPIN_UP", "NON_SPIN_UP"]},
    )
    mixed_services = getters.get_gen_services(mixed, context).unwrap()
    assert len(mixed_services) == 2
    assert spin in mixed_services
    assert non_spin in mixed_services


def test_get_hydro_prime_mover(tmp_path) -> None:
    """get_hydro_prime_mover must always return PrimeMoversType.HY."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = ReEDSRegion(name="p1")
    hydro = ReEDSHydroGenerator(
        name="p1_HYDRO",
        region=region,
        technology="hydro",
        capacity=100.0,
        is_dispatchable=True,
    )
    result = getters.get_hydro_prime_mover(hydro, context).unwrap()
    assert result == PrimeMoversType.HY


def test_get_zero_reactive_power_limits(tmp_path) -> None:
    """get_zero_reactive_power_limits always returns MinMax(0.0, 0.0) regardless of component type."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = ReEDSRegion(name="p1")

    # Works for any component type — hydro, storage, variable gen, etc.
    for component in (
        ReEDSHydroGenerator(
            name="H", region=region, technology="hydro", capacity=100.0, is_dispatchable=True
        ),
        ReEDSStorage(
            name="S",
            region=region,
            technology="battery_4",
            capacity=50.0,
            storage_duration=4.0,
            round_trip_efficiency=0.9,
        ),
        ReEDSVariableGenerator(name="V", region=region, technology="wind-ons", capacity=30.0),
    ):
        limits = getters.get_zero_reactive_power_limits(component, context).unwrap()
        assert limits.min == 0.0, f"{type(component).__name__} reactive_power_limits.min should be 0.0"
        assert limits.max == 0.0, f"{type(component).__name__} reactive_power_limits.max should be 0.0"


def test_consuming_tech_getters(tmp_path) -> None:
    """get_consuming_tech_max_active_power and get_consuming_tech_base_power work for both consuming tech types."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = ReEDSRegion(name="p1")

    electrolyzer = ReEDSElectrolyzerDemand(
        name="ELEC1",
        region=region,
        technology="electrolyzer",
        capacity=50.0,
        electricity_efficiency=55.0,
        max_active_power=40.0,
    )
    datacenter = ReEDSDataCenterDemand(
        name="DC1",
        region=region,
        technology="datacenter",
        capacity=30.0,
        electricity_efficiency=1.0,
        # max_active_power not set — should fall back to capacity
    )

    # Electrolyzer: prefers explicit max_active_power
    assert getters.get_consuming_tech_max_active_power(electrolyzer, context).unwrap() == 40.0
    assert getters.get_consuming_tech_base_power(electrolyzer, context).unwrap() == 50.0

    # DataCenter: no explicit max_active_power → uses capacity
    assert getters.get_consuming_tech_max_active_power(datacenter, context).unwrap() == 30.0
    assert getters.get_consuming_tech_base_power(datacenter, context).unwrap() == 30.0
