"""Mock system fixtures for transformation rule testing."""

from typing import TYPE_CHECKING

import pytest
from infrasys.cost_curves import CostCurve, FuelCurve, UnitSystem
from infrasys.function_data import PiecewiseLinearData, QuadraticFunctionData, XYCoords
from infrasys.value_curves import InputOutputCurve, LinearCurve
from r2x_sienna.models import (
    ACBus,
    Area,
    LoadZone,
    MinMax,
    PowerLoad,
    ThermalStandard,
    UpDown,
)
from r2x_sienna.models.costs import ThermalGenerationCost
from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels

if TYPE_CHECKING:
    from r2x_core import System


@pytest.fixture
def sienna_system_empty() -> "System":
    """Mock Sienna system (read-only source).

    Represents the input system that contains Sienna components to be
    converted. This system should be read-only during the conversion process.

    Returns
    -------
    System
        An empty system object with name "sienna_system"
    """
    from r2x_core import System

    sys = System(name="sienna_system", auto_add_composed_components=True, system_base=100.0)
    return sys


@pytest.fixture
def plexos_system_empty() -> "System":
    """Mock PLEXOS system (writable target).

    Represents the output system where converted PLEXOS components will
    be added during the conversion process.

    Returns
    -------
    System
        An empty system object with name "plexos_system"
    """
    from r2x_core import System

    sys = System(name="plexos_system", auto_add_composed_components=True)
    return sys


@pytest.fixture
def sienna_system_with_area_and_zone() -> "System":
    """Sienna system with LoadZone and Area.

    Returns
    -------
    System
        System with a LoadZone named "test-zone" and an Area named "test-area"
    """
    from r2x_core import System

    sys = System(name="sienna_system", auto_add_composed_components=True)
    zone = LoadZone(name="test-zone")
    sys.add_component(zone)

    area = Area.example().model_copy(update={"name": "test-area", "load_zone": zone})
    sys.add_component(area)

    return sys


@pytest.fixture
def sienna_system_with_buses(sienna_system_with_area_and_zone) -> "System":
    """Sienna system with multiple ACBus components.

    Returns
    -------
    System
        System with 3 buses (bus-1, bus-2, bus-3) in the test-area
    """
    zone = sienna_system_with_area_and_zone.get_component(LoadZone, "test-zone")
    area = sienna_system_with_area_and_zone.get_component(Area, "test-area")

    for i in range(1, 4):
        bus = ACBus.example().model_copy(update={"name": f"bus-{i}", "area": area, "load_zone": zone})
        sienna_system_with_area_and_zone.add_component(bus)

    return sienna_system_with_area_and_zone


@pytest.fixture
def sienna_system_with_buses_and_power_load(sienna_system_with_buses) -> "System":
    """Sienna system with buses and a PowerLoad component.

    Returns
    -------
    System
        System with buses and a PowerLoad on bus-1
    """
    bus = sienna_system_with_buses.get_component(ACBus, "bus-1")

    load = PowerLoad.example().model_copy(update={"name": "load-1", "bus": bus, "max_active_power": 100.0})
    sienna_system_with_buses.add_component(load)

    return sienna_system_with_buses


@pytest.fixture
def sienna_system_with_thermal_generators(
    sienna_system_with_buses_and_power_load,
) -> "System":
    """System with multiple ThermalStandard generators for conversion tests."""

    system = sienna_system_with_buses_and_power_load
    bus = system.get_component(ACBus, "bus-1")

    thermal_fuel = ThermalStandard(
        name="thermal-fuel",
        bus=bus,
        base_power=100.0,
        rating=200.0,
        active_power=0.65,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.4, max=0.9),
        ramp_limits=UpDown(up=12.0, down=8.0),
        time_limits=UpDown(up=3.0, down=1.5),
        must_run=False,
        status=True,
        time_at_status=6.0,
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            fixed=7.5,
            start_up=120.0,
            shut_down=25.0,
            variable=FuelCurve(
                value_curve=LinearCurve(9.2),
                fuel_cost=2.4,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )

    thermal_vom = ThermalStandard(
        name="thermal-vom",
        bus=bus,
        base_power=120.0,
        rating=240.0,
        active_power=0.3,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.2, max=0.8),
        ramp_limits=UpDown(up=12.0, down=8.4),
        time_limits=UpDown(up=4.0, down=2.5),
        must_run=False,
        status=False,
        time_at_status=8.0,
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            fixed=5.0,
            start_up=90.0,
            shut_down=12.0,
            variable=CostCurve(
                value_curve=LinearCurve(50.0),
                vom_cost=LinearCurve(14.0),
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )

    system.add_component(thermal_fuel)
    system.add_component(thermal_vom)

    thermal_piecewise = ThermalStandard(
        name="thermal-piecewise",
        bus=bus,
        base_power=90.0,
        rating=180.0,
        active_power=0.5,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.3, max=0.95),
        ramp_limits=UpDown(up=10.0, down=7.0),
        time_limits=UpDown(up=2.0, down=1.0),
        must_run=True,
        status=True,
        time_at_status=4.0,
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.COAL,
        operation_cost=ThermalGenerationCost(
            fixed=6.5,
            start_up=150.0,
            shut_down=30.0,
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=PiecewiseLinearData(
                        points=[
                            XYCoords(0.0, 0.0),
                            XYCoords(60.0, 720.0),
                            XYCoords(120.0, 1560.0),
                        ]
                    )
                ),
                fuel_cost=2.8,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )

    thermal_quadratic = ThermalStandard(
        name="thermal-quadratic",
        bus=bus,
        base_power=110.0,
        rating=220.0,
        active_power=0.55,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.25, max=0.9),
        ramp_limits=UpDown(up=11.0, down=9.0),
        time_limits=UpDown(up=3.5, down=1.8),
        must_run=False,
        status=True,
        time_at_status=5.0,
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            fixed=6.0,
            start_up=95.0,
            shut_down=15.0,
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

    thermal_markup_piecewise = ThermalStandard(
        name="thermal-markup-piecewise",
        bus=bus,
        base_power=130.0,
        rating=260.0,
        active_power=0.45,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.2, max=0.85),
        ramp_limits=UpDown(up=9.0, down=6.0),
        time_limits=UpDown(up=4.0, down=2.0),
        must_run=False,
        status=False,
        time_at_status=2.0,
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.COAL,
        operation_cost=ThermalGenerationCost(
            fixed=4.0,
            start_up=70.0,
            shut_down=10.0,
            variable=CostCurve(
                value_curve=InputOutputCurve(
                    function_data=PiecewiseLinearData(
                        points=[
                            XYCoords(0.0, 0.0),
                            XYCoords(40.0, 400.0),
                            XYCoords(80.0, 960.0),
                        ]
                    )
                ),
                vom_cost=InputOutputCurve(
                    function_data=PiecewiseLinearData(
                        points=[
                            XYCoords(0.0, 0.0),
                            XYCoords(40.0, 520.0),
                            XYCoords(80.0, 1280.0),
                        ]
                    )
                ),
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )

    system.add_component(thermal_piecewise)
    system.add_component(thermal_quadratic)
    system.add_component(thermal_markup_piecewise)

    return system
