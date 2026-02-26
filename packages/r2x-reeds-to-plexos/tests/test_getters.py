"""Direct getter coverage tests for ReEDS-to-PLEXOS."""

from __future__ import annotations

from r2x_plexos.models import PLEXOSLine, PLEXOSNode, PLEXOSReserve, PLEXOSStorage, PLEXOSZone
from r2x_reeds.models import (
    FromTo_ToFrom,
    ReEDSConsumingTechnology,
    ReEDSHydroGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSReserve,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSTransmissionLine,
    ReEDSVariableGenerator,
)
from r2x_reeds_to_plexos import getters

from r2x_core import DataStore, PluginConfig, PluginContext, System


def make_context(tmp_path) -> PluginContext:
    config = PluginConfig(models=("r2x_reeds.models", "r2x_plexos.models", "r2x_reeds_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    return PluginContext(config=config, store=store)


def setup_systems(context):
    # Source system
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Regions
    region = ReEDSRegion(name="R1", transmission_region="Z1")
    region2 = ReEDSRegion(name="R2", transmission_region="Z2")
    context.source_system.add_component(region)
    context.source_system.add_component(region2)

    # Zones (target)
    zone = PLEXOSZone(name="Z1")
    zone2 = PLEXOSZone(name="Z2")
    context.target_system.add_component(zone)
    context.target_system.add_component(zone2)

    # Nodes (target)
    node = PLEXOSNode(name="R1", voltage=115.0)
    node2 = PLEXOSNode(name="R2", voltage=230.0)
    context.target_system.add_component(node)
    context.target_system.add_component(node2)

    # Generators
    thermal = ReEDSThermalGenerator(
        name="GEN1",
        region=region,
        technology="coal",
        capacity=50.0,
        heat_rate=9.0,
        fuel_type="coal",
        forced_outage_rate=0.02,
        ramp_rate=1.0,
        min_stable_level=0.2,
        min_up_time=2.0,
        min_down_time=1.0,
    )
    variable = ReEDSVariableGenerator(
        name="WIND1",
        region=region,
        technology="wind-ons_1",
        capacity=30.0,
    )
    hydro = ReEDSHydroGenerator(
        name="HYDRO1",
        region=region,
        technology="hydro",
        capacity=20.0,
        is_dispatchable=False,
        ramp_rate=2.0,
    )
    storage = ReEDSStorage(
        name="BAT1",
        region=region,
        technology="battery",
        capacity=10.0,
        storage_duration=4.0,
        energy_capacity=35.0,
        fom_cost=2.0,
        vom_cost=1.0,
        round_trip_efficiency=0.0,
        capital_cost=100.0,
    )
    consuming = ReEDSConsumingTechnology(
        name="CTECH1",
        technology="h2",
        region=region,
        capacity=12.0,
        electricity_efficiency=0.4,
    )
    context.source_system.add_component(thermal)
    context.source_system.add_component(variable)
    context.source_system.add_component(hydro)
    context.source_system.add_component(storage)
    context.source_system.add_component(consuming)

    # Reserve
    reserve = ReEDSReserve(
        name="REG1",
        reserve_type="REGULATION",
        direction="Up",
        time_frame=300.0,
        duration=3600.0,
        vors=200.0,
    )
    context.source_system.add_component(reserve)
    plexos_reserve = PLEXOSReserve(name="REG1")
    context.target_system.add_component(plexos_reserve)

    # Storage in target
    plexos_storage_head = PLEXOSStorage(name="BAT1_head")
    plexos_storage_tail = PLEXOSStorage(name="BAT1_tail")
    context.target_system.add_component(plexos_storage_head)
    context.target_system.add_component(plexos_storage_tail)

    # Interface and line
    interface = ReEDSInterface(name="IFACE1", from_region=region, to_region=region2)
    context.source_system.add_component(interface)
    line = ReEDSTransmissionLine(
        name="LINE1", interface=interface, max_active_power=FromTo_ToFrom(from_to=100.0, to_from=100.0)
    )
    context.source_system.add_component(line)
    plexos_line = PLEXOSLine(name="LINE1")
    context.target_system.add_component(plexos_line)

    return {
        "region": region,
        "region2": region2,
        "zone": zone,
        "zone2": zone2,
        "node": node,
        "node2": node2,
        "thermal": thermal,
        "variable": variable,
        "hydro": hydro,
        "storage": storage,
        "consuming": consuming,
        "reserve": reserve,
        "plexos_reserve": plexos_reserve,
        "plexos_storage_head": plexos_storage_head,
        "plexos_storage_tail": plexos_storage_tail,
        "interface": interface,
        "line": line,
        "plexos_line": plexos_line,
    }


def test_basic_getters_return_values(tmp_path):
    """Invoke ReEDS-to-PLEXOS getters directly to ensure coverage and registration."""
    context = make_context(tmp_path)
    objs = setup_systems(context)

    # Region and node getters
    assert getters.region_load(objs["region"], context).unwrap() == 0.0

    # Generator getters
    assert getters.rating(objs["thermal"], context).unwrap() == 50.0
    assert getters.load_subtracter(objs["thermal"], context).unwrap() == 0.0

    # Storage getters
    assert getters.add_head_suffix(objs["storage"], context).unwrap() == "BAT1_head"
    assert getters.add_tail_suffix(objs["storage"], context).unwrap() == "BAT1_tail"
    assert getters.storage_max_volume(objs["storage"], context).unwrap() == 40.0
    assert getters.storage_initial_volume(objs["storage"], context).unwrap() == 35.0
    assert getters.storage_natural_inflow(objs["storage"], context).unwrap() == 0.0

    # Reserve getters
    assert getters.reserve_type(objs["reserve"], context).unwrap() == 7
    assert getters.forced_outage_rate_percent(objs["thermal"], context).unwrap() == 2.0
    assert getters.maintenance_rate_percent(objs["thermal"], context).unwrap() == 0.0
    assert getters.charge_efficiency_percent(objs["storage"], context).unwrap() == 95.0
    assert getters.discharge_efficiency_percent(objs["storage"], context).unwrap() == 95.0
    assert getters.mean_time_to_repair_hours(objs["thermal"], context).unwrap() == 0.0
    assert getters.get_battery_max_soc(objs["storage"], context).unwrap() == 100.0
    assert getters.get_battery_initial_soc(objs["storage"], context).unwrap() == 50.0
    assert getters.get_battery_min_soc(objs["storage"], context).unwrap() == 0.0

    # Interface and line getters
    assert getters.interface_max_flow(objs["interface"], context).unwrap() == 100.0
    assert getters.interface_min_flow(objs["interface"], context).unwrap() == -100.0
    assert getters.get_interface_name(objs["interface"], context).unwrap() == "Z1_Z2-IFACE1"
    assert getters.min_capacity_factor_percent(objs["variable"], context).unwrap() == 0.0
    assert getters.line_max_flow(objs["line"], context).unwrap() == 100.0
    assert getters.line_min_flow(objs["line"], context).unwrap() == -100.0

    # Storage cost getters
    assert getters.storage_fom_cost_energy(objs["storage"], context).unwrap() == 2.0
    assert getters.storage_vom_cost_energy(objs["storage"], context).unwrap() == 1.0
    assert getters.reserve_vors_percent(objs["reserve"], context).unwrap() == 2.0
    assert getters.reserve_timeframe(objs["reserve"], context).unwrap() == 300.0
    assert getters.reserve_duration(objs["reserve"], context).unwrap() == 3600.0
    assert getters.reserve_requirement(objs["reserve"], context).unwrap() == 0.0

    # Storage energy/cost
    assert getters.storage_energy_from_duration_or_explicit(objs["storage"], context).unwrap() == 35.0
    assert getters.storage_capital_cost_power(objs["storage"], context).unwrap() == 100.0
    assert getters.storage_fom_cost_power(objs["storage"], context).unwrap() == 2.0

    # Hydro getters
    assert getters.hydro_min_flow(objs["hydro"], context).unwrap() == 0.0
    assert getters.hydro_must_run_flag(objs["hydro"], context).unwrap() == 1

    # Consuming tech
    assert getters.consuming_tech_load_mw(objs["consuming"], context).unwrap() == 12.0
    assert getters.consuming_tech_efficiency_to_heat_rate(objs["consuming"], context).unwrap() == 2.5

    # VRE category/resource class
    assert getters.vre_category_with_resource_class(objs["variable"], context).unwrap() == "wind-ons"

    # Supply curve cost
    variable2 = ReEDSVariableGenerator(
        name="PV1",
        region=objs["region"],
        technology="pv",
        capacity=10.0,
        supply_curve_cost=123.0,
    )
    context.source_system.add_component(variable2)
    assert getters.supply_curve_cost_getter(variable2, context).unwrap() == 123.0

    # Membership and collection enums
    assert getters.reeds_membership_collection_nodes(objs["thermal"], context).unwrap().name == "Nodes"
    assert getters.reeds_membership_collection_region(objs["thermal"], context).unwrap().name == "Region"
    assert getters.reeds_membership_parent_component(objs["thermal"], context).unwrap() == objs["thermal"]

    # Membership parent/child node lookups
    assert getters.reeds_membership_region_parent_node(objs["region"], context).unwrap().name == "R1"
    assert getters.reeds_membership_node_parent_zone(objs["node"], context).unwrap().name == "Z1"
    assert (
        getters.reeds_membership_storage_child_head_storage(objs["storage"], context).unwrap().name
        == "BAT1_head"
    )
    assert (
        getters.reeds_membership_storage_child_tail_storage(objs["storage"], context).unwrap().name
        == "BAT1_tail"
    )


def test_line_max_flow_and_min_flow_edge_cases(tmp_path):
    from r2x_reeds_to_plexos import getters

    class DummyLimits:
        from_to = 0
        to_from = 0

    class DummyLine:
        max_active_power = None

    # No limits
    line = DummyLine()
    assert getters.line_max_flow(line, None).unwrap() == 0.0
    assert getters.line_min_flow(line, None).unwrap() == 0.0

    # With limits
    class DummyLine2:
        max_active_power = DummyLimits()

    line2 = DummyLine2()
    assert getters.line_max_flow(line2, None).unwrap() == 0.0
    assert getters.line_min_flow(line2, None).unwrap() == -0.0


def test_vre_category_with_resource_class_edge_cases(tmp_path):
    from r2x_reeds_to_plexos import getters

    class Dummy:
        name = "X"
        technology = ""

    # No technology
    dummy = Dummy()
    result = getters.vre_category_with_resource_class(dummy, None)
    assert result.is_err()
