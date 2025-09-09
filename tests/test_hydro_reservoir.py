import pytest

from r2x.api import System
from r2x.enums import ReservoirDataType
from r2x.models import ACBus, MinMax
from r2x.models.generators import HydroReservoir, HydroTurbine


@pytest.fixture
def bus():
    return ACBus.example()


@pytest.fixture
def hydro_reservoir():
    return HydroReservoir(
        name="Reservoir1",
        available=True,
        initial_level=1.0,
        storage_level_limits={"min": 0.0, "max": 1.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=0.0,
        travel_time=0.0,
        level_data_type=ReservoirDataType.TOTAL_VOLUME,
        intake_elevation=0.0,
    )


@pytest.fixture
def hydro_turbine(bus):
    return HydroTurbine(
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
    )


@pytest.fixture
def test_hydro_reservoir_system(bus, hydro_reservoir, hydro_turbine):
    sys = System(name="Test system", auto_add_composed_components=True)
    sys.add_component(bus)
    sys.add_component(hydro_reservoir)
    hydro_turbine.bus = bus
    sys.add_component(hydro_turbine)
    return sys


def test_hydro_turbine_field_set(hydro_turbine):
    hydro_turbine.powerhouse_elevation = 10.0
    assert hydro_turbine.powerhouse_elevation == 10.0


def test_hydro_reservoir_fields_set(hydro_reservoir):
    hydro_reservoir.intake_elevation = 10.0
    assert hydro_reservoir.intake_elevation == 10.0
    assert hydro_reservoir.initial_level == 1.0
    assert hydro_reservoir.storage_level_limits.min == 0.0
    assert hydro_reservoir.storage_level_limits.max == 1.0
    assert hydro_reservoir.inflow == 0.0
    assert hydro_reservoir.outflow == 0.0
    assert hydro_reservoir.level_targets == 0.0
    assert hydro_reservoir.available is True


def test_single_turbine_single_reservoir(test_hydro_reservoir_system, hydro_turbine, hydro_reservoir):
    system = test_hydro_reservoir_system
    hydro_turbine.reservoirs = [hydro_reservoir]
    assert hydro_turbine.reservoirs == [hydro_reservoir]

    system.remove_component(hydro_reservoir)
    hydro_turbine.reservoirs == []


def test_multiple_turbines_single_reservoir(bus, hydro_reservoir):
    sys = System(auto_add_composed_components=True)
    sys.add_component(bus)
    sys.add_component(hydro_reservoir)

    turbines = []
    for i in range(5):
        turbine = HydroTurbine(
            name=f"Turbine{i + 1}",
            available=True,
            bus=bus,
            active_power=0.0,
            reactive_power=0.0,
            rating=1.0,
            base_power=100.0,
            powerhouse_elevation=10.0,
            active_power_limits={"min": 0.0, "max": 1.0},
        )
        turbine.reservoirs = [hydro_reservoir]
        sys.add_component(turbine)
        turbines.append(turbine)

    collected_turbines = list(sys.get_components(HydroTurbine))
    assert len(turbines) == len(collected_turbines)

    for turbine in collected_turbines:
        assert turbine.reservoirs == [hydro_reservoir]
