"""PLEXOS system fixtures for translation testing.

Memberships follow PLEXOS parent/child conventions: generators and batteries
own their ``Nodes`` membership, nodes own their ``Region`` membership, lines own
``NodeFrom``/``NodeTo``, and reserves own ``Generators``/``Batteries``.
"""

from datetime import datetime, timedelta

import numpy as np
import pytest
from infrasys import SingleTimeSeries
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSReserve,
)

from r2x_core import System

PROFILE_START = datetime(2025, 1, 1)
PROFILE_HOURS = 48


def _connect(system: System, parent, child, collection: CollectionEnum) -> None:
    membership = PLEXOSMembership(parent_object=parent, child_object=child, collection=collection)
    system.add_supplemental_attribute(parent, membership)
    system.add_supplemental_attribute(child, membership)


def _profile_mw(capacity: float, shape: np.ndarray) -> SingleTimeSeries:
    return SingleTimeSeries(
        name="max_active_power",
        data=capacity * shape,
        resolution=timedelta(hours=1),
        initial_timestamp=PROFILE_START,
    )


def solar_shape() -> np.ndarray:
    hours = np.arange(PROFILE_HOURS) % 24
    return np.clip(np.sin((hours - 6) / 12 * np.pi), 0.0, None)


def wind_shape() -> np.ndarray:
    hours = np.arange(PROFILE_HOURS)
    return 0.5 + 0.4 * np.cos(hours / 24 * 2 * np.pi)


@pytest.fixture
def plexos_2node_base():
    return System(name="plexos_2node", auto_add_composed_components=True)


@pytest.fixture
def plexos_2node_topology(plexos_2node_base):
    """One region with 30 MW of load, two 110 kV nodes, and one 100 MW line."""
    system = plexos_2node_base

    region = PLEXOSRegion(object_id=1, name="Area1", load=30.0)
    system.add_component(region)

    nodes = [
        PLEXOSNode(object_id=2, name="Node1", voltage=110.0, is_slack_bus=-1),
        PLEXOSNode(object_id=3, name="Node2", voltage=110.0),
    ]
    for node in nodes:
        system.add_component(node)
        _connect(system, node, region, CollectionEnum.Region)

    line = PLEXOSLine(
        object_id=4,
        name="Line_1_2",
        min_flow=-100.0,
        max_flow=100.0,
        resistance=0.01,
        reactance=0.1,
        units=1,
    )
    system.add_component(line)
    _connect(system, line, nodes[0], CollectionEnum.NodeFrom)
    _connect(system, line, nodes[1], CollectionEnum.NodeTo)

    return system


@pytest.fixture
def plexos_2node_with_generation(plexos_2node_topology):
    """Add a 50 MW gas generator at Node1."""
    system = plexos_2node_topology

    gen = PLEXOSGenerator(object_id=5, name="Gen1", category="Natural Gas", max_capacity=50.0, units=1)
    system.add_component(gen)
    _connect(system, gen, system.get_component(PLEXOSNode, "Node1"), CollectionEnum.Nodes)

    return system


@pytest.fixture
def plexos_2node_complete(plexos_2node_with_generation):
    return plexos_2node_with_generation


@pytest.fixture
def plexos_5bus_base():
    return System(name="plexos_5bus", auto_add_composed_components=True)


@pytest.fixture
def plexos_5bus_topology(plexos_5bus_base):
    """IEEE 5-bus topology: one region with 165 MW of load, five 230 kV nodes, seven lines."""
    system = plexos_5bus_base

    region = PLEXOSRegion(object_id=0, name="Area1", load=165.0)
    system.add_component(region)

    for object_id, name in enumerate(["Bus1", "Bus2", "Bus3", "Bus4", "Bus5"], start=1):
        node = PLEXOSNode(
            object_id=object_id, name=name, voltage=230.0, is_slack_bus=-1 if object_id == 1 else 0
        )
        system.add_component(node)
        _connect(system, node, region, CollectionEnum.Region)

    line_specs = [
        ("Line_1_2", "Bus1", "Bus2", 80.0),
        ("Line_1_3", "Bus1", "Bus3", 30.0),
        ("Line_2_3", "Bus2", "Bus3", 20.0),
        ("Line_2_4", "Bus2", "Bus4", 20.0),
        ("Line_2_5", "Bus2", "Bus5", 60.0),
        ("Line_3_4", "Bus3", "Bus4", 10.0),
        ("Line_4_5", "Bus4", "Bus5", 10.0),
    ]
    for object_id, (name, from_bus, to_bus, limit_mw) in enumerate(line_specs, start=6):
        line = PLEXOSLine(
            object_id=object_id,
            name=name,
            min_flow=-limit_mw,
            max_flow=limit_mw,
            resistance=0.01,
            reactance=0.1,
            units=1,
        )
        system.add_component(line)
        _connect(system, line, system.get_component(PLEXOSNode, from_bus), CollectionEnum.NodeFrom)
        _connect(system, line, system.get_component(PLEXOSNode, to_bus), CollectionEnum.NodeTo)

    return system


@pytest.fixture
def plexos_5bus_with_generation(plexos_5bus_topology):
    """Add thermal, hydro, solar, and wind units with 25% min stable level and MW/min ramps."""
    system = plexos_5bus_topology

    generators = [
        ("ThermalGen", "Natural Gas", 40.0, "Bus2"),
        ("HydroGen", "Hydro", 50.0, "Bus1"),
        ("SolarGen", "Solar", 30.0, "Bus3"),
        ("WindGen", "Wind", 25.0, "Bus5"),
    ]
    for object_id, (name, category, capacity, bus_name) in enumerate(generators, start=13):
        gen = PLEXOSGenerator(
            object_id=object_id,
            name=name,
            category=category,
            max_capacity=capacity,
            min_stable_level=0.25 * capacity,
            max_ramp_up=0.1 * capacity,
            max_ramp_down=0.05 * capacity,
            units=1,
        )
        system.add_component(gen)
        _connect(system, gen, system.get_component(PLEXOSNode, bus_name), CollectionEnum.Nodes)

    return system


@pytest.fixture
def plexos_5bus_with_storage(plexos_5bus_with_generation):
    """Add a 20 MW / 80 MWh battery at Bus4."""
    system = plexos_5bus_with_generation

    battery = PLEXOSBattery(
        object_id=17,
        name="Battery1",
        category="battery",
        max_power=20.0,
        capacity=80.0,
        initial_soc=50.0,
        units=1,
        charge_efficiency=95.0,
        discharge_efficiency=95.0,
    )
    system.add_component(battery)
    _connect(system, battery, system.get_component(PLEXOSNode, "Bus4"), CollectionEnum.Nodes)

    return system


@pytest.fixture
def plexos_5bus_with_reserves(plexos_5bus_with_storage):
    """Add a spinning reserve provided by the thermal and hydro units and the battery."""
    system = plexos_5bus_with_storage

    reserve = PLEXOSReserve(object_id=18, name="SpinningReserve", type=1, timeframe=600.0, duration=3600.0)
    system.add_component(reserve)
    for name in ("ThermalGen", "HydroGen"):
        _connect(system, reserve, system.get_component(PLEXOSGenerator, name), CollectionEnum.Generators)
    _connect(system, reserve, system.get_component(PLEXOSBattery, "Battery1"), CollectionEnum.Batteries)

    return system


@pytest.fixture
def plexos_5bus_complete(plexos_5bus_with_reserves):
    """Attach hourly MW availability profiles to the solar and wind generators."""
    system = plexos_5bus_with_reserves

    for name, shape in (("SolarGen", solar_shape()), ("WindGen", wind_shape())):
        gen = system.get_component(PLEXOSGenerator, name)
        system.add_time_series(_profile_mw(gen.max_capacity, shape), gen)

    return system
