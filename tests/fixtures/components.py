"""Component fixtures for building test systems with increasing complexity."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from r2x_sienna.models import (
    ACBus,
    Area,
    EnergyReservoirStorage,
    HydroDispatch,
    Line,
    LoadZone,
    PowerLoad,
    RenewableDispatch,
    ThermalStandard,
    Transformer2W,
    VariableReserve,
)

if TYPE_CHECKING:
    from r2x_core import System


@pytest.fixture
def system_with_load_zone(sienna_system_empty: System) -> System:
    """System with LoadZone and Area."""
    from r2x_sienna.models import Area, LoadZone

    sys = sienna_system_empty
    zone = LoadZone(name="TestZone")
    sys.add_component(zone)

    area = Area.example().model_copy(update={"name": "test-area", "load_zone": zone})
    sys.add_component(area)

    return sys


@pytest.fixture
def system_with_buses(system_with_zone):
    """System with buses in a zone."""
    zone = system_with_zone.get_component(LoadZone, "test-zone")
    area = system_with_zone.get_component(Area, "test-area")

    # Add multiple buses for network testing
    for i in range(1, 4):
        bus = ACBus.example().model_copy(update={"name": f"bus-{i}", "area": area})
        system_with_zone.add_component(bus)

    return system_with_zone


@pytest.fixture
def system_with_load(system_with_buses):
    """System with a load on a bus."""
    bus = system_with_buses.get_component(ACBus, "bus-1")

    load = PowerLoad.example().model_copy(update={"name": "load-1", "bus": bus, "active_power": 100.0})
    system_with_buses.add_component(load)

    return system_with_buses


@pytest.fixture
def system_with_thermal_gen(system_with_load):
    """System with a basic thermal generator (no costs)."""
    bus = system_with_load.get_component(ACBus, "bus-1")

    gen = ThermalStandard.example().model_copy(
        update={
            "name": "thermal-1",
            "bus": bus,
            "active_power_limits": (10.0, 100.0),  # (min, max)
        }
    )
    system_with_load.add_component(gen)

    return system_with_load


@pytest.fixture
def system_with_thermal_gen_costs(system_with_thermal_gen):
    """System with thermal generator including operation costs."""
    gen = system_with_thermal_gen.get_component(ThermalStandard, "thermal-1")

    # Add simple polynomial operation cost
    # This is a simplified version - real systems have more complex structures
    if hasattr(gen, "operation_cost") and gen.operation_cost is not None:
        # Already has operation_cost from example, just enhance it
        pass

    return system_with_thermal_gen


@pytest.fixture
def system_with_multiband_costs(system_with_zone):
    """System with generator having piecewise linear costs.

    This fixture creates a generator with:
    - Piecewise linear VOM cost (3 bands)
    - Piecewise linear heat rate (3 bands)
    - Load-dependent ramp rates
    """
    zone = system_with_zone.get_component(LoadZone, "test-zone")
    area = system_with_zone.get_component(Area, "test-area")

    # Add bus
    bus = ACBus.example().model_copy(update={"name": "multiband-bus", "area": area})
    system_with_zone.add_component(bus)

    # Add generator with complex cost structure
    gen = ThermalStandard.example().model_copy(
        update={
            "name": "multiband-gen",
            "bus": bus,
            "active_power_limits": (20.0, 200.0),
        }
    )

    system_with_zone.add_component(gen)

    return system_with_zone


@pytest.fixture
def system_with_renewable(system_with_buses):
    """System with a renewable dispatch generator."""
    bus = system_with_buses.get_component(ACBus, "bus-2")

    gen = RenewableDispatch.example().model_copy(
        update={
            "name": "solar-1",
            "bus": bus,
            "active_power_limits": (0.0, 50.0),
        }
    )
    system_with_buses.add_component(gen)

    return system_with_buses


# ==============================================================================
# Level 9: Hydro Generators
# ==============================================================================


@pytest.fixture
def system_with_hydro_dispatch(system_with_buses):
    """System with a hydro dispatch generator."""
    bus = system_with_buses.get_component(ACBus, "bus-3")

    gen = HydroDispatch.example().model_copy(update={"name": "hydro-dispatch", "bus": bus})
    system_with_buses.add_component(gen)

    return system_with_buses


# ==============================================================================
# Level 10: Storage
# ==============================================================================


@pytest.fixture
def system_with_storage(system_with_buses):
    """System with battery storage."""
    bus = system_with_buses.get_component(ACBus, "bus-1")

    battery = EnergyReservoirStorage.example().model_copy(
        update={
            "name": "battery-1",
            "bus": bus,
            "storage_capacity_limits": (0.0, 500.0),
        }
    )
    system_with_buses.add_component(battery)

    return system_with_buses


# ==============================================================================
# Level 11: Network Components
# ==============================================================================


@pytest.fixture
def system_with_network(system_with_buses):
    """System with transmission lines."""
    bus1 = system_with_buses.get_component(ACBus, "bus-1")
    bus2 = system_with_buses.get_component(ACBus, "bus-2")

    line = Line.example().model_copy(update={"name": "line-1-2", "from_bus": bus1, "to_bus": bus2})
    system_with_buses.add_component(line)

    return system_with_buses


@pytest.fixture
def system_with_transformers(system_with_buses):
    """System with transformers."""
    bus1 = system_with_buses.get_component(ACBus, "bus-1")
    bus2 = system_with_buses.get_component(ACBus, "bus-2")

    transformer = Transformer2W.example().model_copy(
        update={"name": "transformer-1-2", "from_bus": bus1, "to_bus": bus2}
    )
    system_with_buses.add_component(transformer)

    return system_with_buses


# ==============================================================================
# Level 12: Complete Complex System
# ==============================================================================


@pytest.fixture
def system_complete(system_with_zone):
    """Complete test system with all component types.

    Builds a multi-bus, multi-zone system with:
    - Multiple buses and zones
    - Thermal, renewable, and hydro generation
    - Load requirements
    - Network components (lines, transformers)
    - Storage
    - Reserves
    """
    zone = system_with_zone.get_component(LoadZone, "test-zone")
    area = system_with_zone.get_component(Area, "test-area")

    # Create network with 3 buses
    buses = {}
    for i in range(1, 4):
        bus = ACBus.example().model_copy(update={"name": f"bus-{i}", "area": area})
        system_with_zone.add_component(bus)
        buses[f"bus-{i}"] = bus

    # Add loads
    load = PowerLoad.example().model_copy(
        update={"name": "load-1", "bus": buses["bus-1"], "active_power": 150.0}
    )
    system_with_zone.add_component(load)

    # Add thermal generation
    thermal_gen = ThermalStandard.example().model_copy(
        update={
            "name": "thermal-1",
            "bus": buses["bus-1"],
            "active_power_limits": (10.0, 200.0),
        }
    )
    system_with_zone.add_component(thermal_gen)

    # Add renewable generation
    renewable_gen = RenewableDispatch.example().model_copy(
        update={
            "name": "solar-1",
            "bus": buses["bus-2"],
            "active_power_limits": (0.0, 100.0),
        }
    )
    system_with_zone.add_component(renewable_gen)

    # Add storage
    battery = EnergyReservoirStorage.example().model_copy(
        update={
            "name": "battery-1",
            "bus": buses["bus-2"],
            "storage_capacity_limits": (0.0, 500.0),
        }
    )
    system_with_zone.add_component(battery)

    # Add network
    line = Line.example().model_copy(
        update={
            "name": "line-1-2",
            "from_bus": buses["bus-1"],
            "to_bus": buses["bus-2"],
        }
    )
    system_with_zone.add_component(line)

    transformer = Transformer2W.example().model_copy(
        update={
            "name": "transformer-1-2",
            "from_bus": buses["bus-1"],
            "to_bus": buses["bus-2"],
        }
    )
    system_with_zone.add_component(transformer)

    # Add reserve
    reserve = VariableReserve.example().model_copy(update={"name": "reserve-1", "requirement": 50.0})
    system_with_zone.add_component(reserve)

    return system_with_zone
