"""Direct getter coverage tests for ReEDS-to-Sienna."""

from __future__ import annotations

from infrasys.cost_curves import FuelCurve, LinearCurve
from r2x_reeds.models import (
    ReEDSDemand,
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

from r2x_core import PluginConfig, System, TranslationContext, UnitSystem


def test_basic_getters_return_values() -> None:
    """Invoke getters directly to ensure coverage and registration."""

    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters")),
        rules=[],
    )

    region = ReEDSRegion(name="p1")
    context.source_system.add_component(region)

    region2 = ReEDSRegion(name="p2")
    context.source_system.add_component(region2)

    # Test region with no numeric component
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
    assert getters.unique_component_name(context, thermal).unwrap() == "p1_THERM"
    assert getters.get_capacity_as_rating(context, thermal).unwrap() == 10.0
    assert getters.get_capacity_as_base_power(context, thermal).unwrap() == 10.0
    limits = getters.get_active_power_limits(context, thermal).unwrap()
    assert limits.max == 10.0
    assert limits.min == 0.0
    assert getters.get_thermal_operation_cost(context, thermal).unwrap() is not None
    assert getters.get_prime_mover(context, thermal).unwrap() == PrimeMoversType.ST
    assert getters.get_fuel_enum(context, thermal).unwrap() == ThermalFuels.COAL

    # Test renewable generator getters
    assert getters.get_renewable_operation_cost(context, variable).unwrap() is not None
    assert getters.get_renewable_prime_mover(context, variable).unwrap() == PrimeMoversType.WT
    assert getters.get_renewable_prime_mover(context, variable_pv).unwrap() == PrimeMoversType.PVe
    assert getters.get_zero_active_power(context, variable).unwrap() == 0.0
    assert getters.get_zero_reactive_power(context, variable).unwrap() == 0.0
    assert getters.get_default_must_run(context, variable).unwrap() is False
    assert getters.get_default_status(context, variable).unwrap() is True
    assert getters.get_default_time_at_status(context, variable).unwrap() == 0.0

    # Test region/bus getters
    assert getters.get_area_for_region(context, region).unwrap() == area
    assert getters.bus_name_from_region(context, region).unwrap() == "p1_BUS"
    assert getters.base_voltage_default(context, region).unwrap() == 115.0
    assert getters.bustype_default(context, region).unwrap() == ACBusTypes.PQ
    assert getters.get_bus_for_region(context, thermal).unwrap() == bus
    assert getters.get_bus_number(context, region).unwrap() == 1
    assert getters.get_bus_number(context, region_non_numeric).unwrap() == 999999
    assert getters.get_area_category(context, region).unwrap() == "region"

    # Test demand getters
    assert getters.demand_max_active_power(context, demand).unwrap() == 3.0
    assert getters.demand_max_reactive_power(context, demand).unwrap() == 0.0
    assert getters.get_load_base_power(context, demand).unwrap() == 100.0

    # Test hydro getters
    assert getters.hydro_rating(context, hydro).unwrap() == 8.0
    assert getters.hydro_operation_cost(context, hydro).unwrap() is not None
    hydro_limits = getters.hydro_active_power_limits(context, hydro).unwrap()
    assert hydro_limits.max == 8.0
    assert hydro_limits.min == 0.0
    ramp_limits = getters.hydro_ramp_limits(context, hydro).unwrap()
    assert ramp_limits.up == 0.8
    assert ramp_limits.down == 0.8
    time_limits = getters.hydro_time_limits(context, hydro).unwrap()
    assert time_limits.up == 0.0
    assert time_limits.down == 0.0

    # Test storage getters
    assert getters.storage_rating(context, storage).unwrap() == 4.0
    assert getters.storage_capacity_mwh(context, storage).unwrap() == 8.0
    storage_limits = getters.storage_level_limits(context, storage).unwrap()
    assert storage_limits.min == 0.0
    assert storage_limits.max == 1.0
    power_limits = getters.storage_power_limits(context, storage).unwrap()
    assert power_limits.max == 4.0
    efficiency = getters.storage_efficiency(context, storage).unwrap()
    assert efficiency.output == 0.9
    assert getters.storage_tech(context, storage).unwrap() == StorageTechs.LIB
    assert getters.storage_prime_mover(context, storage).unwrap() == PrimeMoversType.ES
    assert getters.storage_initial_level(context, storage).unwrap() == 0.0
    assert getters.storage_conversion_factor(context, storage).unwrap() == 1.0

    # Test interface getters
    assert getters.get_area_from(context, interface).unwrap() == area
    assert getters.get_area_to(context, interface).unwrap() == area2
    flow_limits = getters.get_interface_flow_limits(context, interface).unwrap()
    assert flow_limits.from_to == 0.0
    assert getters.get_zero_flow(context, interface).unwrap() == 0.0

    # Test reserve getters
    assert getters.get_reserve_type(context, reserve).unwrap() == "REGULATION"
    assert getters.get_reserve_direction(context, reserve).unwrap() == "UP"
    assert getters.get_reserve_requirement(context, reserve).unwrap() == 0.0
    assert getters.get_reserve_time_frame(context, reserve).unwrap() == 300.0
    assert getters.get_reserve_sustained_time(context, reserve).unwrap() == 3600.0
    assert getters.get_reserve_max_output_fraction(context, reserve).unwrap() == 1.0
    assert getters.get_reserve_max_participation_factor(context, reserve).unwrap() == 1.0
    assert getters.get_reserve_deployed_fraction(context, reserve).unwrap() == 1.0

    # Test line getters
    assert getters.get_line_rating(context, line).unwrap() == 100.0
    assert getters.get_line_active_power_flow(context, line).unwrap() == 100.0
    assert getters.get_line_reactive_power_flow(context, line).unwrap() == 0.0
    assert getters.get_line_resistance(context, line).unwrap() == 0.0
    assert getters.get_line_reactance(context, line).unwrap() == 0.0
    susceptance = getters.get_line_susceptance(context, line).unwrap()
    assert susceptance.from_to == 0.0
    conductance = getters.get_line_conductance(context, line).unwrap()
    assert conductance.from_to == 0.0
    angle_limits = getters.get_line_angle_limits(context, line).unwrap()
    assert angle_limits.min == -90.0
    assert angle_limits.max == 90.0

    # Test arc getter
    arc = getters.get_arc_for_line(context, line).unwrap()
    assert isinstance(arc, Arc)
    assert arc.from_to == bus or arc.from_to == bus2
    assert arc.to_from == bus or arc.to_from == bus2


def test_unique_component_name_collision() -> None:
    """Test that unique_component_name handles name collisions."""
    from r2x_sienna.models import ThermalStandard

    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models")),
        rules=[],
    )

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
    unique_name = getters.unique_component_name(context, component).unwrap()
    assert unique_name == "COAL_1_1"


def test_bus_number_with_z_prefix() -> None:
    """Test bus number extraction for z-prefixed regions."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models")),
        rules=[],
    )

    region = ReEDSRegion(name="z122")
    result = getters.get_bus_number(context, region).unwrap()
    assert result == 122
