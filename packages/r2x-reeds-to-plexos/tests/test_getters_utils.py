import types

import pytest
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSStorage,
)
from r2x_reeds.models import FromTo_ToFrom, ReEDSInterface, ReEDSRegion, ReEDSTransmissionLine
from r2x_reeds_to_plexos import getters_utils

from r2x_core import PluginContext, System


@pytest.fixture
def context(tmp_path):
    # Minimal context with source and target systems
    context = PluginContext(config=None, store=None)
    context.source_system = System(name="source")
    context.target_system = System(name="target")
    return context


def test_attach_region_load_time_series(context):
    getters_utils.attach_region_load_time_series(context)


def test_attach_reserve_time_series(context):
    getters_utils.attach_reserve_time_series(context)


def test_attach_time_series_to_generators(context):
    getters_utils.attach_time_series_to_generators(context)


def test_ensure_region_node_memberships(context):
    # Add region and node with same name
    region = PLEXOSRegion(name="R1")
    node = PLEXOSNode(name="R1")
    context.target_system.add_component(region)
    context.target_system.add_component(node)
    getters_utils.ensure_region_node_memberships(context)

    memberships = context.target_system.get_supplemental_attributes_with_component(node, PLEXOSMembership)
    assert any(m.collection.name == "Region" for m in memberships)


def test_ensure_generator_node_memberships(context):
    from r2x_reeds.models import ReEDSRegion, ReEDSThermalGenerator

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    gen = ReEDSThermalGenerator(
        name="GEN1", region=region, technology="coal", capacity=10.0, heat_rate=9.0, fuel_type="coal"
    )
    node = PLEXOSNode(name="R1")
    plexos_gen = PLEXOSGenerator(name="GEN1")
    context.source_system.add_component(region)  # <-- Add this line
    context.source_system.add_component(gen)
    context.target_system.add_component(plexos_gen)
    context.target_system.add_component(node)
    getters_utils.ensure_generator_node_memberships(context)
    memberships = context.target_system.get_supplemental_attributes_with_component(
        plexos_gen, PLEXOSMembership
    )
    assert any(m.collection.name == "Nodes" for m in memberships)


def test_link_line_memberships(context):
    region1 = ReEDSRegion(name="R1", transmission_region="Z1")
    region2 = ReEDSRegion(name="R2", transmission_region="Z2")
    interface = ReEDSInterface(name="IFACE", from_region=region1, to_region=region2)
    line = ReEDSTransmissionLine(
        name="LINE1", interface=interface, max_active_power=FromTo_ToFrom(from_to=100.0, to_from=100.0)
    )
    node1 = PLEXOSNode(name="R1")
    node2 = PLEXOSNode(name="R2")
    plexos_line = PLEXOSLine(name="LINE1")
    context.source_system.add_component(region1)
    context.source_system.add_component(region2)
    context.source_system.add_component(interface)
    context.source_system.add_component(line)
    context.target_system.add_component(plexos_line)
    context.target_system.add_component(node1)
    context.target_system.add_component(node2)
    getters_utils.link_line_memberships(context)
    assert context.target_system.get_supplemental_attributes_with_component(node1, PLEXOSMembership)
    assert context.target_system.get_supplemental_attributes_with_component(node2, PLEXOSMembership)


def test_gu_attach_emissions_to_generators(context):
    getters_utils.attach_emissions_to_generators(context)


def test_gu_convert_pumped_storage_generators(context):
    getters_utils.convert_pumped_storage_generators(context)


def test_attach_region_load_time_series_with_demand(context, monkeypatch):
    from r2x_plexos.models import PLEXOSRegion
    from r2x_reeds.models import ReEDSRegion
    from r2x_reeds.models.components import ReEDSDemand

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    demand = ReEDSDemand(name="D1", region=region)
    context.source_system.add_component(region)
    context.source_system.add_component(demand)
    context.target_system.add_component(PLEXOSRegion(name="R1"))

    # Patch time_series methods
    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda x: [types.SimpleNamespace(name="max_active_power", features={})],
    )
    monkeypatch.setattr(
        context.source_system,
        "list_time_series",
        lambda x, **kwargs: [types.SimpleNamespace(name="max_active_power", __class__=object)],
    )
    context.target_system.has_time_series = lambda *args, **kwargs: False
    context.target_system.add_time_series = lambda *args, **kwargs: None

    getters_utils.attach_region_load_time_series(context)


def test_attach_reserve_time_series_with_reserve(context):
    from r2x_plexos.models import PLEXOSReserve
    from r2x_reeds.models.components import ReEDSReserve

    reserve = ReEDSReserve(
        name="RES1",
        reserve_type="REGULATION",
        direction="Up",
    )
    context.source_system.add_component(reserve)
    context.target_system.add_component(PLEXOSReserve(name="RES1"))

    context.source_system.has_time_series = lambda x: True
    context.source_system.list_time_series = lambda x: [types.SimpleNamespace()]
    context.target_system.add_time_series = lambda *args, **kwargs: None

    getters_utils.attach_reserve_time_series(context)


def test_attach_time_series_to_generators_with_hydro_and_variable(context):
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSGenerator, ReEDSHydroGenerator, ReEDSVariableGenerator

    reg = ReEDSRegion(name="R1", transmission_region="Z1")

    gen = ReEDSGenerator(
        name="GEN1",
        region=reg,
        technology="gas-cc",
        capacity=10.0,
    )
    hydro = ReEDSHydroGenerator(
        name="GEN1", region=reg, technology="hydro", capacity=5.0, is_dispatchable=True
    )
    var = ReEDSVariableGenerator(
        name="GEN2",
        region=reg,
        technology="solar",
        capacity=5.0,
    )
    context.source_system.add_component(reg)
    context.source_system.add_component(gen)
    context.source_system.add_component(hydro)
    context.source_system.add_component(var)
    context.target_system.add_component(PLEXOSGenerator(name="GEN1"))
    context.target_system.add_component(PLEXOSGenerator(name="GEN2"))

    context.source_system.list_time_series = lambda x: [
        types.SimpleNamespace(name="hydro_budget"),
        types.SimpleNamespace(name="max_active_power"),
    ]
    context.target_system.has_time_series = lambda *args, **kwargs: False
    context.target_system.add_time_series = lambda *args, **kwargs: None

    getters_utils.attach_time_series_to_generators(context)


def test_attach_emissions_to_generators(context):
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator

    reg = ReEDSRegion(name="R1", transmission_region="Z1")
    gen = ReEDSGenerator(
        name="GEN1",
        region=reg,
        technology="gas-cc",
        capacity=10.0,
    )
    context.source_system.add_component(reg)
    context.source_system.add_component(gen)
    context.target_system.add_component(PLEXOSGenerator(name="GEN1"))

    # Mock emission
    emission = ReEDSEmission(
        rate=0.5,
        type="CO2E",
    )
    context.source_system.get_supplemental_attributes_with_component = lambda x, y: [emission]
    context.target_system.add_supplemental_attribute = lambda *args, **kwargs: None

    getters_utils.attach_emissions_to_generators(context)


def test_convert_pumped_storage_generators(context):
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models.components import ReEDSGenerator

    reg = ReEDSRegion(name="R1", transmission_region="Z1")
    gen = ReEDSGenerator(
        name="PS1",
        technology="pumped-hydro",
        region=reg,
        capacity=10.0,
    )
    context.source_system.add_component(reg)
    context.source_system.add_component(gen)
    context.target_system.add_component(PLEXOSGenerator(name="PS1"))

    context.target_system.add_component = lambda x: None
    context.target_system.get_components = lambda x: []
    getters_utils.convert_pumped_storage_generators(context)


def test_attach_region_load_time_series_skips_unmapped_and_missing_series(context, monkeypatch):
    from r2x_plexos.models import PLEXOSRegion
    from r2x_reeds.models import ReEDSRegion
    from r2x_reeds.models.components import ReEDSDemand

    region = ReEDSRegion(name="R1", transmission_region="Z1")
    region_unmapped = ReEDSRegion(name="R0", transmission_region="Z0")
    demand_unmapped = ReEDSDemand(name="D0", region=region_unmapped)
    demand_mapped = ReEDSDemand(name="D1", region=region)
    context.source_system.add_component(region)
    context.source_system.add_component(region_unmapped)
    context.source_system.add_component(demand_unmapped)
    context.source_system.add_component(demand_mapped)
    context.target_system.add_component(PLEXOSRegion(name="R1"))

    monkeypatch.setattr(
        context.source_system.time_series,
        "list_time_series_metadata",
        lambda _x: [types.SimpleNamespace(name="max_active_power", features={})],
    )
    monkeypatch.setattr(context.source_system, "list_time_series", lambda *_args, **_kwargs: [])
    context.target_system.has_time_series = lambda *_args, **_kwargs: False
    added = []
    context.target_system.add_time_series = lambda *args, **kwargs: added.append((args, kwargs))

    getters_utils.attach_region_load_time_series(context)
    assert added == []


def test_attach_reserve_time_series_skips_non_matching_target(context):
    from r2x_plexos.models import PLEXOSReserve
    from r2x_reeds.models.components import ReEDSReserve

    reserve = ReEDSReserve(name="SRC_ONLY", reserve_type="REGULATION", direction="Up")
    context.source_system.add_component(reserve)
    context.target_system.add_component(PLEXOSReserve(name="TARGET_ONLY"))
    context.source_system.has_time_series = lambda _x: True
    context.source_system.list_time_series = lambda _x: [types.SimpleNamespace(name="min_provision")]
    added = []
    context.target_system.add_time_series = lambda *args, **kwargs: added.append((args, kwargs))

    getters_utils.attach_reserve_time_series(context)
    assert added == []


def test_attach_time_series_to_generators_skips_missing_target(context):
    from r2x_reeds.models.components import ReEDSGenerator

    reg = ReEDSRegion(name="R1", transmission_region="Z1")
    src_gen = ReEDSGenerator(name="G_MISSING", region=reg, technology="gas-cc", capacity=10.0)
    context.source_system.add_component(reg)
    context.source_system.add_component(src_gen)
    context.source_system.list_time_series = lambda _x: [types.SimpleNamespace(name="max_active_power")]
    added = []
    context.target_system.add_time_series = lambda *args, **kwargs: added.append((args, kwargs))

    getters_utils.attach_time_series_to_generators(context)
    assert added == []


def test_membership_helpers_skip_paths(context):
    region = PLEXOSRegion(name="NO_NODE")
    context.target_system.add_component(region)
    getters_utils.ensure_region_node_memberships(context)

    src_with_no_target = types.SimpleNamespace(
        name="SRC_ONLY",
        region=ReEDSRegion(name="R1", transmission_region="Z1"),
    )
    src_no_region = types.SimpleNamespace(name="NO_REGION", region=None)
    context.source_system.get_components = lambda _component_type: [src_with_no_target, src_no_region]
    context.target_system.add_component(PLEXOSGenerator(name="NO_REGION"))
    getters_utils.ensure_generator_node_memberships(context)


def test_link_line_memberships_skips_when_missing_source_or_nodes(context):
    context.target_system.add_component(PLEXOSLine(name="NO_SOURCE"))
    getters_utils.link_line_memberships(context)

    r1 = ReEDSRegion(name="R1", transmission_region="Z1")
    r2 = ReEDSRegion(name="R2", transmission_region="Z2")
    iface = ReEDSInterface(name="IFACE", from_region=r1, to_region=r2)
    src_line = ReEDSTransmissionLine(
        name="HAS_SOURCE", interface=iface, max_active_power=FromTo_ToFrom(from_to=10.0, to_from=10.0)
    )
    context.source_system.add_component(r1)
    context.source_system.add_component(r2)
    context.source_system.add_component(iface)
    context.source_system.add_component(src_line)
    context.target_system.add_component(PLEXOSLine(name="HAS_SOURCE"))
    context.target_system.add_component(PLEXOSNode(name="R1"))
    getters_utils.link_line_memberships(context)


def test_attach_emissions_to_generators_skips_when_source_generator_missing(context):
    context.target_system.add_component(PLEXOSGenerator(name="ONLY_TARGET"))
    added = []
    context.target_system.add_supplemental_attribute = lambda *args, **kwargs: added.append((args, kwargs))
    getters_utils.attach_emissions_to_generators(context)
    assert added == []


def test_ensure_membership_does_not_duplicate_existing(context):
    parent = PLEXOSGenerator(name="PARENT")
    child = PLEXOSStorage(name="CHILD")
    context.target_system.add_component(parent)
    context.target_system.add_component(child)

    getters_utils._ensure_membership(context.target_system, parent, child, CollectionEnum.Storages)
    first = context.target_system.get_supplemental_attributes_with_component(child, PLEXOSMembership)
    getters_utils._ensure_membership(context.target_system, parent, child, CollectionEnum.Storages)
    second = context.target_system.get_supplemental_attributes_with_component(child, PLEXOSMembership)

    assert len(first) == 1
    assert len(second) == 1
