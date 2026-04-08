"""Sienna reference system fixtures for translation validation."""

import pytest
from r2x_sienna.models import (
    ACBus,
    Area,
    EnergyReservoirStorage,
    HydroDispatch,
    MonitoredLine,
    PowerLoad,
    RenewableDispatch,
    Reserve,
    ThermalStandard,
)
from r2x_sienna.models.enums import ACBusTypes, PrimeMoversType, StorageTechs
from r2x_sienna.models.named_tuples import MinMax
from r2x_sienna.units import ureg

from r2x_core import System


@pytest.fixture
def sienna_2node_complete():
    """Expected Sienna system from 2-node PLEXOS translation.

    Returns
    -------
    System
        Complete 2-node Sienna system
    """
    system = System(name="sienna_2node", auto_add_composed_components=True)

    area = Area(name="Area1")
    system.add_component(area)

    bus1 = ACBus(
        name="Node1",
        bus_type=ACBusTypes.PQ,
        voltage=ureg.Quantity(110.0, "kV"),
        magnitude=ureg.Quantity(1.0, "pu"),
        angle=ureg.Quantity(0.0, "rad"),
        area=area,
    )
    system.add_component(bus1)

    bus2 = ACBus(
        name="Node2",
        bus_type=ACBusTypes.PQ,
        voltage=ureg.Quantity(110.0, "kV"),
        magnitude=ureg.Quantity(1.0, "pu"),
        angle=ureg.Quantity(0.0, "rad"),
        area=area,
    )
    system.add_component(bus2)

    gen = ThermalStandard(
        name="Gen1",
        bus=bus1,
        base_power=ureg.Quantity(50.0, "MW"),
        prime_mover_type=PrimeMoversType.CT,
        active_power_limits=MinMax(
            min=ureg.Quantity(0.0, "MW"),
            max=ureg.Quantity(50.0, "MW"),
        ),
    )
    system.add_component(gen)

    load = PowerLoad(
        name="Node2_load",
        bus=bus2,
        max_active_power=ureg.Quantity(30.0, "MW"),
        max_reactive_power=ureg.Quantity(0.0, "MVAR"),
    )
    system.add_component(load)

    line = MonitoredLine(
        name="Line_1_2",
        arc={"from": bus1, "to": bus2},
        rating=ureg.Quantity(100.0, "MVA"),
    )
    system.add_component(line)

    return system


@pytest.fixture
def sienna_5bus_complete():
    """Expected Sienna system from 5-bus PLEXOS translation.

    Based on IEEE 5-bus system specifications.

    Returns
    -------
    System
        Complete 5-bus Sienna system
    """
    system = System(name="sienna_5bus", auto_add_composed_components=True)

    area = Area(name="Area1")
    system.add_component(area)

    bus_specs = [
        ("Bus1", 1.06, 0.0, 0.0),
        ("Bus2", 1.0, 20.0, 10.0),
        ("Bus3", 1.0, 45.0, 15.0),
        ("Bus4", 1.0, 40.0, 5.0),
        ("Bus5", 1.0, 60.0, 10.0),
    ]

    buses = {}
    for name, voltage_pu, load_mw, load_mvar in bus_specs:
        bus = ACBus(
            name=name,
            bus_type=ACBusTypes.PQ if name != "Bus1" else ACBusTypes.REF,
            voltage=ureg.Quantity(110.0, "kV"),
            magnitude=ureg.Quantity(voltage_pu, "pu"),
            angle=ureg.Quantity(0.0, "rad"),
            area=area,
        )
        system.add_component(bus)
        buses[name] = bus

        if load_mw > 0:
            load = PowerLoad(
                name=f"{name}_load",
                bus=bus,
                max_active_power=ureg.Quantity(load_mw, "MW"),
                max_reactive_power=ureg.Quantity(load_mvar, "MVAR"),
            )
            system.add_component(load)

    thermal_gen = ThermalStandard(
        name="ThermalGen",
        bus=buses["Bus2"],
        base_power=ureg.Quantity(40.0, "MW"),
        prime_mover_type=PrimeMoversType.CT,
        active_power_limits=MinMax(
            min=ureg.Quantity(0.0, "MW"),
            max=ureg.Quantity(40.0, "MW"),
        ),
    )
    system.add_component(thermal_gen)

    hydro_gen = HydroDispatch(
        name="HydroGen",
        bus=buses["Bus1"],
        base_power=ureg.Quantity(50.0, "MW"),
        active_power_limits=MinMax(
            min=ureg.Quantity(0.0, "MW"),
            max=ureg.Quantity(50.0, "MW"),
        ),
    )
    system.add_component(hydro_gen)

    solar_gen = RenewableDispatch(
        name="SolarGen",
        bus=buses["Bus3"],
        base_power=ureg.Quantity(30.0, "MW"),
        prime_mover_type=PrimeMoversType.PVe,
        rating=ureg.Quantity(30.0, "MW"),
    )
    system.add_component(solar_gen)

    wind_gen = RenewableDispatch(
        name="WindGen",
        bus=buses["Bus5"],
        base_power=ureg.Quantity(25.0, "MW"),
        prime_mover_type=PrimeMoversType.WT,
        rating=ureg.Quantity(25.0, "MW"),
    )
    system.add_component(wind_gen)

    battery = EnergyReservoirStorage(
        name="Battery1",
        bus=buses["Bus2"],
        storage_capacity=ureg.Quantity(20.0, "MWh"),
        charge_capacity=ureg.Quantity(20.0, "MW"),
        discharge_capacity=ureg.Quantity(20.0, "MW"),
        storage_tech=StorageTechs.Li_ion,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
    )
    system.add_component(battery)

    line_specs = [
        ("Line_1_2", "Bus1", "Bus2", 0.8),
        ("Line_1_3", "Bus1", "Bus3", 0.3),
        ("Line_2_3", "Bus2", "Bus3", 0.2),
        ("Line_2_4", "Bus2", "Bus4", 0.2),
        ("Line_2_5", "Bus2", "Bus5", 0.6),
        ("Line_3_4", "Bus3", "Bus4", 0.1),
        ("Line_4_5", "Bus4", "Bus5", 0.1),
    ]

    system_base_mva = 100.0
    for name, from_bus, to_bus, limit_pu in line_specs:
        line = MonitoredLine(
            name=name,
            arc={"from": buses[from_bus], "to": buses[to_bus]},
            rating=ureg.Quantity(limit_pu * system_base_mva, "MVA"),
        )
        system.add_component(line)

    spin_reserve = Reserve(
        name="SpinningReserve",
        time_frame=ureg.Quantity(600.0, "s"),
    )
    system.add_component(spin_reserve)

    non_spin_reserve = Reserve(
        name="NonSpinningReserve",
        time_frame=ureg.Quantity(1800.0, "s"),
    )
    system.add_component(non_spin_reserve)

    return system
