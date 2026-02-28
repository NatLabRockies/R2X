"""PLEXOS system fixtures for translation testing."""

import pytest
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSPropertyValue,
    PLEXOSRegion,
    PLEXOSReserve,
)

from r2x_core import System


@pytest.fixture
def plexos_2node_base():
    """Empty PLEXOS system for 2-node test case.

    Returns
    -------
    System
        Empty infrasys System
    """
    system = System(name="plexos_2node", auto_add_composed_components=True)
    return system


@pytest.fixture
def plexos_2node_topology(plexos_2node_base):
    """PLEXOS 2-node system with topology: 1 area, 2 nodes, 1 line.

    Returns
    -------
    System
        System with basic topology
    """
    system = plexos_2node_base

    region = PLEXOSRegion(object_id=1, name="Area1")
    system.add_component(region)

    node1 = PLEXOSNode(object_id=2, name="Node1", category="Area1", voltage=110.0)
    node2 = PLEXOSNode(object_id=3, name="Node2", category="Area1", voltage=110.0)
    system.add_component(node1)
    system.add_component(node2)

    node_1_region_membership = PLEXOSMembership(
        parent_object=region,
        child_object=node1,
        collection=CollectionEnum.Nodes,
    )

    node_2_region_membership = PLEXOSMembership(
        parent_object=region,
        child_object=node2,
        collection=CollectionEnum.Nodes,
    )
    system.add_supplemental_attribute(node1, node_1_region_membership)
    system.add_supplemental_attribute(node2, node_2_region_membership)
    system.add_supplemental_attribute(region, node_1_region_membership)
    system.add_supplemental_attribute(region, node_2_region_membership)

    line = PLEXOSLine(
        object_id=4,
        name="Line_1_2",
        max_flow=100.0,
        units=1,
    )
    system.add_component(line)

    # Connect line to nodes using NodeFrom and NodeTo memberships
    # The line is the parent, nodes are referenced via parent_object (representing the connected node)
    from_membership = PLEXOSMembership(
        parent_object=node1,  # This membership connects to Node1
        child_object=line,  # This membership connects to Node1
        collection=CollectionEnum.NodeFrom,
    )
    to_membership = PLEXOSMembership(
        parent_object=node2,  # This membership connects to Node2
        child_object=line,  # This membership connects to Node2
        collection=CollectionEnum.NodeTo,
    )
    system.add_supplemental_attribute(line, from_membership)
    system.add_supplemental_attribute(line, to_membership)

    return system


@pytest.fixture
def plexos_2node_with_generation(plexos_2node_topology):
    """PLEXOS 2-node system with 1 thermal generator at Node1.

    Returns
    -------
    System
        System with generator added
    """
    system = plexos_2node_topology

    gen = PLEXOSGenerator(
        object_id=5,
        name="Gen1",
        category="Natural Gas",
        max_capacity=50.0,
        units=1,
    )
    system.add_component(gen)

    # Connect generator to Node1
    nodes = list(system.get_components(PLEXOSNode))
    node1 = next(n for n in nodes if n.name == "Node1")

    gen_node_membership = PLEXOSMembership(
        parent_object=gen,  # Node contains the generator
        child_object=node1,
        collection=CollectionEnum.Nodes,
    )
    system.add_supplemental_attribute(gen, gen_node_membership)
    system.add_supplemental_attribute(node1, gen_node_membership)

    return system


@pytest.fixture
def plexos_2node_complete(plexos_2node_with_generation):
    """Complete PLEXOS 2-node system with load at Node2.

    Returns
    -------
    System
        Complete 2-node system
    """
    system = plexos_2node_with_generation

    nodes = list(system.get_components(PLEXOSNode))
    node2 = next(n for n in nodes if n.name == "Node2")
    node2.load = 30.0
    node2.ac_reactive_power = 10.0

    return system


@pytest.fixture
def plexos_5bus_base():
    """Empty PLEXOS system for IEEE 5-bus test case.

    Returns
    -------
    System
        Empty infrasys System
    """
    system = System(name="plexos_5bus", auto_add_composed_components=True)
    return system


@pytest.fixture
def plexos_5bus_topology(plexos_5bus_base):
    """PLEXOS 5-bus system with topology: 1 area, 5 nodes, 7 lines.

    Based on IEEE 5-bus system specifications.

    Returns
    -------
    System
        System with 5-bus topology
    """
    system = plexos_5bus_base

    region = PLEXOSRegion(object_id=0, name="Area1")
    system.add_component(region)

    bus_specs = [
        ("Bus1", 1.06, 0.0, 0.0),
        ("Bus2", 1.0, 20.0, 10.0),
        ("Bus3", 1.0, 45.0, 15.0),
        ("Bus4", 1.0, 40.0, 5.0),
        ("Bus5", 1.0, 60.0, 10.0),
    ]

    for object_id, (name, voltage, load_mw, load_mvar) in enumerate(bus_specs, start=1):
        node = PLEXOSNode(
            object_id=object_id,
            name=name,
            category="Area1",
            voltage=voltage,
            load=load_mw,
            ac_reactive_power=load_mvar,
        )
        system.add_component(node)

    line_specs = [
        ("Line_1_2", "Bus1", "Bus2", 0.8),
        ("Line_1_3", "Bus1", "Bus3", 0.3),
        ("Line_2_3", "Bus2", "Bus3", 0.2),
        ("Line_2_4", "Bus2", "Bus4", 0.2),
        ("Line_2_5", "Bus2", "Bus5", 0.6),
        ("Line_3_4", "Bus3", "Bus4", 0.1),
        ("Line_4_5", "Bus4", "Bus5", 0.1),
    ]

    # Get all nodes for connectivity
    nodes = {node.name: node for node in system.get_components(PLEXOSNode)}

    system_base_mva = 100.0
    for object_id, (name, from_bus, to_bus, limit_pu) in enumerate(line_specs, start=6):
        line = PLEXOSLine(
            object_id=object_id,
            name=name,
            max_flow=limit_pu * system_base_mva,
            units=1,
        )
        system.add_component(line)

        # Add connectivity memberships for the line
        from_membership = PLEXOSMembership(
            parent_object=nodes[from_bus],
            child_object=line,
            collection=CollectionEnum.NodeFrom,
        )
        to_membership = PLEXOSMembership(
            parent_object=nodes[to_bus],
            child_object=line,
            collection=CollectionEnum.NodeTo,
        )
        system.add_supplemental_attribute(line, from_membership)
        system.add_supplemental_attribute(line, to_membership)

    return system


@pytest.fixture
def plexos_5bus_with_generation(plexos_5bus_topology):
    """PLEXOS 5-bus system with generators (1 per type for translation testing).

    Adds:
    - 1 ThermalStandard (Natural Gas) at Bus2: 40 MW
    - 1 HydroDispatch (Hydro) at Bus1: 50 MW
    - 1 RenewableDispatch (Solar) at Bus3: 30 MW
    - 1 RenewableDispatch (Wind) at Bus5: 25 MW

    Returns
    -------
    System
        System with generators
    """
    system = plexos_5bus_topology

    # Generator specifications: (name, category, capacity, units, bus)
    generators = [
        ("ThermalGen", "Natural Gas", 40.0, 1, "Bus2"),
        ("HydroGen", "Hydro", 50.0, 1, "Bus1"),
        ("SolarGen", "Solar", 30.0, 1, "Bus3"),
        ("WindGen", "Wind", 25.0, 1, "Bus5"),
    ]

    # Get all nodes for connectivity
    nodes = {node.name: node for node in system.get_components(PLEXOSNode)}

    for object_id, (name, category, capacity, units, bus_name) in enumerate(generators, start=13):
        gen = PLEXOSGenerator(
            object_id=object_id,
            name=name,
            category=category,
            max_capacity=capacity,
            units=units,
        )
        system.add_component(gen)

        # Connect generator to its bus
        gen_node_membership = PLEXOSMembership(
            parent_object=gen, child_object=nodes[bus_name], collection=CollectionEnum.Nodes
        )
        system.add_supplemental_attribute(gen, gen_node_membership)

    return system


@pytest.fixture
def plexos_5bus_with_storage(plexos_5bus_with_generation):
    """PLEXOS 5-bus system with 1 battery storage.

    Returns
    -------
    System
        System with battery storage
    """
    system = plexos_5bus_with_generation

    battery = PLEXOSBattery(
        object_id=17,
        name="Battery1",
        capacity=20.0,
        units=1,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
    )
    system.add_component(battery)

    # Connect battery to Bus4
    nodes = {node.name: node for node in system.get_components(PLEXOSNode)}
    battery_node_membership = PLEXOSMembership(
        parent_object=battery,
        child_object=nodes["Bus4"],  # Node contains the battery
        collection=CollectionEnum.Nodes,
    )
    system.add_supplemental_attribute(battery, battery_node_membership)

    return system


@pytest.fixture
def plexos_5bus_with_reserves(plexos_5bus_with_storage):
    """PLEXOS 5-bus system with 2 reserves (Spinning and Non-Spinning).

    Reserve assignments:
    - Spinning: Region + all generators
    - Non-Spinning: Region + subset of generators

    Returns
    -------
    System
        System with reserves
    """
    system = plexos_5bus_with_storage

    spin_reserve = PLEXOSReserve(
        object_id=18,
        name="SpinningReserve",
        type=1,
        is_enabled=-1,
    )
    system.add_component(spin_reserve)

    non_spin_reserve = PLEXOSReserve(
        object_id=19,
        name="NonSpinningReserve",
        type=2,
        is_enabled=-1,
    )
    system.add_component(non_spin_reserve)

    return system


@pytest.fixture
def plexos_5bus_complete(
    plexos_5bus_with_reserves, example_solar_profile, example_wind_profile, datetime_single_component_data
):
    """Complete PLEXOS 5-bus system with time series for renewables.

    Returns
    -------
    System
        Complete 5-bus system with time series
    """
    from datetime import date

    system = plexos_5bus_with_reserves

    gens = list(system.get_components(PLEXOSGenerator))
    solar_gen = next(g for g in gens if g.name == "SolarGen")
    solar_profile = datetime_single_component_data(
        solar_gen.name, start_date=date(2025, 1, 1), days=30, profile=example_solar_profile()
    )
    prop_value: PLEXOSPropertyValue = PLEXOSPropertyValue.from_dict(
        {"value": 0.0, "text": str(solar_profile)}
    )
    solar_gen.rating = prop_value

    return system
