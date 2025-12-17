"""Direct getter coverage tests for ReEDS-to-Sienna."""

from __future__ import annotations

from r2x_reeds.models import (
    ReEDSDemand,
    ReEDSHydroGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSVariableGenerator,
)
from r2x_reeds_to_sienna import getters
from r2x_sienna.models import ACBus, Area
from r2x_sienna.units import Voltage

from r2x_core import PluginConfig, System, TranslationContext


def test_basic_getters_return_values() -> None:
    """Invoke getters directly to ensure coverage and registration."""

    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters")),
        rules=[],
    )

    region = ReEDSRegion(name="REG1")
    area = Area(name="REG1")
    context.target_system.add_component(area)
    bus = ACBus(name="REG1_BUS", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus)
    thermal = ReEDSThermalGenerator(
        name="THERM",
        region=region,
        technology="coal-new",
        capacity=10.0,
        heat_rate=7.5,
        fuel_type="coal",
    )
    variable = ReEDSVariableGenerator(
        name="WIND",
        region=region,
        technology="wind-ons",
        capacity=5.0,
    )
    hydro = ReEDSHydroGenerator(
        name="HYDRO",
        region=region,
        technology="hydro",
        capacity=8.0,
        is_dispatchable=True,
    )
    storage = ReEDSStorage(
        name="STORE",
        region=region,
        technology="battery",
        capacity=4.0,
        storage_duration=2.0,
        round_trip_efficiency=0.9,
    )
    demand = ReEDSDemand(name="LOAD", region=region, max_active_power=3.0)
    interface = ReEDSInterface(name="IFACE", from_region=region, to_region=region)

    assert getters.get_capacity_as_rating(context, thermal).unwrap() == 10.0
    assert getters.get_capacity_as_base_power(context, thermal).unwrap() == 10.0
    limits = getters.get_active_power_limits(context, thermal).unwrap()
    assert limits.max == 10.0
    assert getters.get_thermal_operation_cost(context, thermal).unwrap() is not None
    assert getters.get_prime_mover(context, thermal).unwrap() is not None
    assert getters.get_fuel_enum(context, thermal).unwrap() is not None

    assert getters.get_renewable_operation_cost(context, variable).unwrap() is not None
    assert getters.get_renewable_prime_mover(context, variable).unwrap() is not None
    assert getters.get_zero_active_power(context, variable).unwrap() == 0.0
    assert getters.get_zero_reactive_power(context, variable).unwrap() == 0.0
    assert getters.get_default_must_run(context, variable).unwrap() is False
    assert getters.get_default_status(context, variable).unwrap() is True
    assert getters.get_default_time_at_status(context, variable).unwrap() == 0.0
    assert getters.get_area_for_region(context, region).unwrap() == area
    assert getters.bus_name_from_region(context, region).unwrap() == "REG1_BUS"
    assert getters.base_voltage_default(context, region).unwrap() > 0
    assert getters.bustype_default(context, region).unwrap() is not None
    assert getters.get_bus_for_region(context, thermal).unwrap() == bus
    assert getters.demand_max_active_power(context, demand).unwrap() == 3.0
    assert getters.demand_max_reactive_power(context, demand).unwrap() == 0.0
    assert getters.hydro_rating(context, hydro).unwrap() == 8.0
    assert getters.hydro_operation_cost(context, hydro).unwrap() is not None
    assert getters.storage_capacity_mwh(context, storage).unwrap() == 8.0
    assert getters.storage_power_limits(context, storage).unwrap().max == 4.0
    assert getters.storage_efficiency(context, storage).unwrap().output == 0.9
    assert getters.storage_tech(context, storage).unwrap() is not None
    assert getters.get_area_from(context, interface).unwrap() == area
    assert getters.get_area_to(context, interface).unwrap() == area
    assert getters.get_interface_flow_limits(context, interface).unwrap().from_to == 0.0
    assert getters.get_zero_flow(context, interface).unwrap() == 0.0
