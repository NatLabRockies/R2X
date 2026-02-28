"""5-bus system fixtures based on c_sys5_all_components.json structure.

This module provides comprehensive test fixtures that build progressively complex
5-bus systems using r2x-sienna components. These systems are designed to match the
structure and component diversity of c_sys5_all_components.json.

The fixtures follow a hierarchical pattern: 1. Network infrastructure (zones, buses, areas) 2. Basic generation (thermal, renewable)
3. Advanced generation (hydro with storage)
4. Transmission network (lines, transformers)
5. Loads and specialized loads
6. Complete complex systems
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_core import System


@pytest.fixture
def system_with_zones() -> System:
    """System with zone and area infrastructure.

    Returns
    -------
    System
        System with LoadZone "Zone-1" and Area "Area-1"
    """
    from importlib.metadata import version

    from r2x_sienna.models import Area, LoadZone

    from r2x_core import System

    sys = System(
        name="c_sys_5bus",
        auto_add_composed_components=True,
        system_base=100.0,
        description="IEEE 5-bus system example.",
        data_format_version=version("r2x_sienna"),
    )

    zone = LoadZone(name="Zone-1")
    sys.add_component(zone)

    area = Area(name="Area-1")
    sys.add_component(area)

    return sys


@pytest.fixture
def system_with_5_buses(system_with_zones) -> System:
    """System with 5 AC buses.

    Returns
    -------
    System
        System with buses: Bus-1 through Bus-5
    """
    from r2x_sienna.models import ACBus, Area, LoadZone

    zone = system_with_zones.get_component(LoadZone, "Zone-1")
    area = system_with_zones.get_component(Area, "Area-1")

    for i in range(1, 6):
        bus = ACBus(
            name=f"Bus-{i}",
            number=i,
            area=area,
            load_zone=zone,
            base_voltage=138.0,
        )
        system_with_zones.add_component(bus)

    return system_with_zones


@pytest.fixture
def system_with_loads(system_with_5_buses, load_single_time_series) -> System:
    """System with loads.

    Adds PowerLoad and StandardLoad components.

    Returns
    -------
    System
        System with loads
    """
    from r2x_sienna.models import ACBus, PowerLoad

    sys = system_with_5_buses
    bus1 = sys.get_component(ACBus, "Bus-1")
    bus2 = sys.get_component(ACBus, "Bus-2")

    power_load = PowerLoad(
        name="Load-1",
        bus=bus1,
        max_active_power=100.0,
    )
    sys.add_component(power_load)

    standard_load = PowerLoad(
        name="Load-2",
        bus=bus2,
        max_active_power=200.0,
    )
    sys.add_component(standard_load)

    sys.add_time_series(load_single_time_series, power_load, standard_load)

    return sys


@pytest.fixture
def system_with_thermal_generators(system_with_loads) -> System:
    """System with 5 thermal generators with diverse costs.

    Includes generators with:
    - Linear fuel curves
    - VOM + fuel curves
    - Piecewise linear costs
    - Quadratic costs
    - Piecewise linear VOM + fuel

    Returns
    -------
    System
        System with 5 thermal generators
    """
    from infrasys.cost_curves import CostCurve, FuelCurve, UnitSystem
    from infrasys.function_data import PiecewiseLinearData, QuadraticFunctionData, XYCoords
    from infrasys.value_curves import InputOutputCurve, LinearCurve
    from r2x_sienna.models import ACBus, MinMax, ThermalStandard, UpDown
    from r2x_sienna.models.costs import ThermalGenerationCost
    from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels

    sys = system_with_loads
    bus1 = sys.get_component(ACBus, "Bus-1")
    bus2 = sys.get_component(ACBus, "Bus-2")
    bus3 = sys.get_component(ACBus, "Bus-3")

    thermal_coal = ThermalStandard(
        name="thermal-coal",
        bus=bus1,
        active_power_limits=MinMax(min=50.0, max=400.0),
        ramp_limits=UpDown(up=100.0, down=80.0),
        time_limits=UpDown(up=5.0, down=3.0),
        prime_mover_type=PrimeMoversType.ST,
        fuel=ThermalFuels.COAL,
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=100,
        must_run=False,
        status=True,
        time_at_status=0.0,
        operation_cost=ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=PiecewiseLinearData(
                        points=[
                            XYCoords(0.0, 0.0),
                            XYCoords(150.0, 1200.0),
                            XYCoords(300.0, 2850.0),
                            XYCoords(400.0, 4000.0),
                        ]
                    )
                ),
                fuel_cost=2.8,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    sys.add_component(thermal_coal)

    thermal_gas_1 = ThermalStandard(
        name="thermal-gas-1",
        bus=bus1,
        active_power_limits=MinMax(min=30.0, max=300.0),
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=300,
        must_run=False,
        status=True,
        time_at_status=0.0,
        ramp_limits=UpDown(up=120.0, down=100.0),
        time_limits=UpDown(up=4.0, down=2.0),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=LinearCurve(9.2),
                fuel_cost=2.4,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    sys.add_component(thermal_gas_1)

    thermal_gas_2 = ThermalStandard(
        name="thermal-gas-2",
        bus=bus2,
        active_power_limits=MinMax(min=24.0, max=240.0),
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=240.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        ramp_limits=UpDown(up=96.0, down=84.0),
        time_limits=UpDown(up=3.5, down=2.5),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            variable=CostCurve(
                value_curve=LinearCurve(50.0),
                vom_cost=LinearCurve(14.0),
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    sys.add_component(thermal_gas_2)

    thermal_quad = ThermalStandard(
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
    sys.add_component(thermal_quad)

    thermal_markup = ThermalStandard(
        name="thermal-markup",
        bus=bus3,
        active_power_limits=MinMax(min=26.0, max=260.0),
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=260.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        ramp_limits=UpDown(up=104.0, down=78.0),
        time_limits=UpDown(up=4.5, down=2.0),
        prime_mover_type=PrimeMoversType.ST,
        fuel=ThermalFuels.COAL,
        operation_cost=ThermalGenerationCost(
            variable=CostCurve(
                value_curve=InputOutputCurve(
                    function_data=PiecewiseLinearData(
                        points=[
                            XYCoords(0.0, 0.0),
                            XYCoords(80.0, 600.0),
                            XYCoords(160.0, 1440.0),
                            XYCoords(260.0, 2600.0),
                        ]
                    )
                ),
                vom_cost=InputOutputCurve(
                    function_data=PiecewiseLinearData(
                        points=[
                            XYCoords(0.0, 0.0),
                            XYCoords(80.0, 800.0),
                            XYCoords(160.0, 1920.0),
                            XYCoords(260.0, 3380.0),
                        ]
                    )
                ),
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    sys.add_component(thermal_markup)

    return sys


@pytest.fixture
def system_with_renewables(system_with_thermal_generators, vre_single_time_series) -> System:
    """System with 3 renewable generators.

    Includes:
    - Solar on Bus-4
    - Wind on Bus-4
    - Solar on Bus-5

    Returns
    -------
    System
        System with renewable generators
    """
    from infrasys.cost_curves import CostCurve, UnitSystem
    from infrasys.value_curves import LinearCurve
    from r2x_sienna.models import ACBus, RenewableDispatch, RenewableGenerationCost
    from r2x_sienna.models.enums import PrimeMoversType

    sys = system_with_thermal_generators
    bus4 = sys.get_component(ACBus, "Bus-4")
    bus5 = sys.get_component(ACBus, "Bus-5")

    solar_1 = RenewableDispatch(
        name="solar-1",
        bus=bus4,
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=100.0,
        operation_cost=RenewableGenerationCost(
            curtailment_cost=CostCurve(value_curve=LinearCurve(0), power_units=UnitSystem.NATURAL_UNITS)
        ),
        prime_mover_type=PrimeMoversType.PVe,
    )
    sys.add_component(solar_1)

    wind_1 = RenewableDispatch(
        name="wind-1",
        bus=bus4,
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=150.0,
        operation_cost=RenewableGenerationCost(
            curtailment_cost=CostCurve(value_curve=LinearCurve(0), power_units=UnitSystem.NATURAL_UNITS)
        ),
        prime_mover_type=PrimeMoversType.WT,
    )
    sys.add_component(wind_1)

    solar_2 = RenewableDispatch(
        name="solar-2",
        bus=bus5,
        active_power=0.0,
        reactive_power=0.0,
        rating=1,
        base_power=200,
        operation_cost=RenewableGenerationCost(
            curtailment_cost=CostCurve(value_curve=LinearCurve(0), power_units=UnitSystem.NATURAL_UNITS)
        ),
        prime_mover_type=PrimeMoversType.PVe,
    )
    sys.add_component(solar_2)

    ts = vre_single_time_series

    sys.add_time_series(ts, solar_1, solar_2, wind_1)

    return sys


@pytest.fixture
def system_with_hydro(system_with_renewables) -> System:
    """System with hydro generation components.

    Includes:
    - HydroDispatch (run-of-river)
    - HydroTurbine (with efficiency)
    - HydroReservoir (with storage)

    Returns
    -------
    System
        System with comprehensive hydro generation
    """
    from r2x_sienna.models import (
        ACBus,
        HydroDispatch,
        HydroGenerationCost,
        HydroReservoir,
        HydroTurbine,
        MinMax,
        PrimeMoversType,
    )

    sys = system_with_renewables
    bus3 = sys.get_component(ACBus, "Bus-3")

    hydro_dispatch = HydroDispatch(
        name="hydro-dispatch",
        bus=bus3,
        active_power=0.0,
        reactive_power=0.0,
        base_power=180,
        rating=1,
        operation_cost=HydroGenerationCost().example(),
        active_power_limits=MinMax(min=10.0, max=180.0),
        prime_mover_type=PrimeMoversType.HY,
    )
    sys.add_component(hydro_dispatch)

    hydro_turbine = HydroTurbine(
        name="hydro-turbine",
        bus=bus3,
        active_power=0.0,
        reactive_power=0.0,
        base_power=150,
        rating=1,
        operation_cost=HydroGenerationCost().example(),
        active_power_limits=MinMax(min=5.0, max=150.0),
        prime_mover_type=PrimeMoversType.HY,
        conversion_factor=0.001,
    )
    sys.add_component(hydro_turbine)

    hydro_reservoir = HydroReservoir.example()  # Reservoir do not attach to bus
    sys.add_component(hydro_reservoir)

    return sys


@pytest.fixture
def system_with_storage(system_with_hydro) -> System:
    """System with energy storage.

    Includes:
    - Battery storage on Bus-5

    Returns
    -------
    System
        System with energy storage capability
    """
    from r2x_sienna.models import ACBus, EnergyReservoirStorage, MinMax

    sys = system_with_hydro
    bus5 = sys.get_component(ACBus, "Bus-5")

    battery = EnergyReservoirStorage.example()
    battery.storage_level_limits = MinMax(min=0.0, max=500.0)
    battery.bus = bus5
    sys.add_component(battery)

    return sys


@pytest.fixture
def system_with_network(system_with_storage) -> System:
    """System with transmission network.

    Includes:
    - 4 transmission lines
    - 1 transformer
    - 6 arc components

    Returns
    -------
    System
        System with complete transmission network
    """
    from r2x_sienna.models import ACBus, Arc, Line, MinMax, Transformer2W

    sys = system_with_storage
    bus1 = sys.get_component(ACBus, "Bus-1")
    bus2 = sys.get_component(ACBus, "Bus-2")
    bus3 = sys.get_component(ACBus, "Bus-3")
    bus4 = sys.get_component(ACBus, "Bus-4")
    bus5 = sys.get_component(ACBus, "Bus-5")

    line_1_2 = Line(
        name="line-1-2",
        arc=Arc(from_to=bus1, to_from=bus2),
        rating=100.0,
        active_power_flow=100,
        reactive_power_flow=100,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    sys.add_component(line_1_2)

    line_2_3 = Line(
        name="line-2-3",
        arc=Arc(from_to=bus2, to_from=bus3),
        active_power_flow=0.0,
        rating=100.0,
        reactive_power_flow=100,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    sys.add_component(line_2_3)

    line_3_4 = Line(
        name="line-3-4",
        arc=Arc(from_to=bus3, to_from=bus4),
        active_power_flow=0.0,
        rating=100.0,
        reactive_power_flow=100,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    sys.add_component(line_3_4)

    line_4_5 = Line(
        name="line-4-5",
        arc=Arc(from_to=bus4, to_from=bus5),
        active_power_flow=0.0,
        rating=100.0,
        reactive_power_flow=100,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    sys.add_component(line_4_5)

    transformer_1_5 = Transformer2W(
        name="transformer-1-5",
        arc=Arc(from_to=bus1, to_from=bus5),
        active_power_flow=0.0,
    )
    sys.add_component(transformer_1_5)

    return sys


@pytest.fixture
def system_with_reserves(system_with_network) -> System:
    """System with operating reserves.

    Includes:
    - 2 variable reserves

    Returns
    -------
    System
        System with operating reserves
    """
    from r2x_sienna.models import ReserveDirection, ReserveType, VariableReserve

    sys = system_with_network

    spin_reserve = VariableReserve(
        name="spin-reserve",
        reserve_type=ReserveType.SPINNING,
        direction=ReserveDirection.UP,
        requirement=100.0,
    )
    sys.add_component(spin_reserve)

    flex_reserve = VariableReserve(
        name="flex-reserve",
        reserve_type=ReserveType.FLEXIBILITY,
        direction=ReserveDirection.DOWN,
        requirement=100.0,
    )
    sys.add_component(flex_reserve)

    return sys


@pytest.fixture
def system_complete(system_with_reserves) -> System:
    """Complete 5-bus system with all components.

    Returns
    -------
    System
        Complete system with:
        - 2 zones and areas
        - 5 buses
        - 5 thermal generators
        - 3 renewable generators
        - 3 hydro generation components
        - 1 battery storage
        - 2 loads (PowerLoad, StandardLoad)
        - 4 transmission lines
        - 1 transformer
        - 6 arc components
        - 2 reserves
    """
    return system_with_reserves
