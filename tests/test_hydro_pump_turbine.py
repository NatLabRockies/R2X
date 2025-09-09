import pytest

from r2x.api import System
from r2x.models import ACBus, MinMax
from r2x.models.generators import HydroPumpTurbine, HydroReservoir


@pytest.fixture
def bus():
    return ACBus.example()


@pytest.fixture
def head_reservoir():
    return HydroReservoir(
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
    )


@pytest.fixture
def tail_reservoir():
    return HydroReservoir(
        name="TailReservoir",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=0.0,
        travel_time=0.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
    )


@pytest.fixture
def hydro_pump_turbine(bus, head_reservoir, tail_reservoir):
    return HydroPumpTurbine(
        name="PumpTurbine1",
        available=True,
        bus=bus,
        active_power=100.0,
        reactive_power=0.0,
        rating=100.0,
        active_power_limits=MinMax(min=0.0, max=100.0),
        active_power_limits_pump=MinMax(min=0.0, max=100.0),
        head_reservoir=head_reservoir,
        tail_reservoir=tail_reservoir,
        powerhouse_elevation=100.0,
        base_power=100.0,
        active_power_pump=50.0,
        efficiency={"turbine": 0.95, "pump": 0.85},
        conversion_factor=1.0,
        must_run=False,
    )


@pytest.fixture
def hydro_pump_system(bus, head_reservoir, tail_reservoir, hydro_pump_turbine):
    sys = System(name="Pumped Hydro System", auto_add_composed_components=True)
    sys.add_component(bus)
    sys.add_component(head_reservoir)
    sys.add_component(tail_reservoir)
    sys.add_component(hydro_pump_turbine)
    return sys


def test_pump_turbine_field_set(hydro_pump_turbine):
    hydro_pump_turbine.powerhouse_elevation = 200.0
    assert hydro_pump_turbine.powerhouse_elevation == 200.0


def test_head_tail_reservoir_fields(head_reservoir, tail_reservoir):
    head_reservoir.initial_level = 600.0
    tail_reservoir.initial_level = 400.0
    assert head_reservoir.initial_level == 600.0
    assert tail_reservoir.initial_level == 400.0
    assert head_reservoir.storage_level_limits.max == 1000.0
    assert tail_reservoir.storage_level_limits.min == 0.0


def test_single_pump_turbine_single_reservoir(
    hydro_pump_system, hydro_pump_turbine, head_reservoir, tail_reservoir
):
    hydro_pump_turbine.head_reservoir = head_reservoir
    hydro_pump_turbine.tail_reservoir = tail_reservoir
    assert hydro_pump_turbine.head_reservoir == head_reservoir
    assert hydro_pump_turbine.tail_reservoir == tail_reservoir


def test_multiple_pump_turbines_single_reservoir(bus, head_reservoir, tail_reservoir):
    sys = System(auto_add_composed_components=True)
    sys.add_component(bus)
    sys.add_component(head_reservoir)
    sys.add_component(tail_reservoir)

    turbines = []
    for i in range(5):
        turbine = HydroPumpTurbine(
            name=f"PumpTurbine{i + 1}",
            available=True,
            bus=bus,
            active_power=100.0,
            reactive_power=0.0,
            rating=100.0,
            active_power_limits=MinMax(min=0.0, max=100.0),
            active_power_limits_pump=MinMax(min=0.0, max=100.0),
            head_reservoir=head_reservoir,
            tail_reservoir=tail_reservoir,
            powerhouse_elevation=100.0,
            base_power=100.0,
            efficiency={"turbine": 0.95, "pump": 0.85},
        )
        sys.add_component(turbine)
        turbines.append(turbine)

    collected_turbines = list(sys.get_components(HydroPumpTurbine))
    assert len(turbines) == len(collected_turbines)

    for turbine in collected_turbines:
        assert turbine.head_reservoir == head_reservoir
        assert turbine.tail_reservoir == tail_reservoir
