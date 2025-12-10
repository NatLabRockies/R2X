"""Tests for ReEDS-to-PLEXOS getter utility functions."""

import pytest


def test_ensure_membership_creates_membership() -> None:
    """_ensure_membership creates and adds membership to system."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSMembership, PLEXOSNode
    from r2x_reeds_to_plexos.getters_utils import _ensure_membership

    from r2x_core import System

    system = System(name="test", auto_add_composed_components=True)

    parent = PLEXOSGenerator(name="gen1")
    child = PLEXOSNode(name="node1")

    _ensure_membership(system, parent, child, CollectionEnum.Nodes)

    memberships = list(system.get_supplemental_attributes(PLEXOSMembership))
    assert len(memberships) == 1
    assert memberships[0].parent_object is parent
    assert memberships[0].child_object is child
    assert memberships[0].collection == CollectionEnum.Nodes


def test_ensure_membership_does_not_duplicate() -> None:
    """_ensure_membership does not create duplicate memberships."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSMembership, PLEXOSNode
    from r2x_reeds_to_plexos.getters_utils import _ensure_membership

    from r2x_core import System

    system = System(name="test", auto_add_composed_components=True)

    parent = PLEXOSGenerator(name="gen1")
    child = PLEXOSNode(name="node1")

    # Add twice
    _ensure_membership(system, parent, child, CollectionEnum.Nodes)
    _ensure_membership(system, parent, child, CollectionEnum.Nodes)

    memberships = list(system.get_supplemental_attributes(PLEXOSMembership))
    # Should only have one membership
    assert len(memberships) == 1


def test_ensure_region_node_memberships_creates_memberships() -> None:
    """ensure_region_node_memberships creates region-node memberships."""
    from r2x_plexos.models import PLEXOSNode, PLEXOSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import ensure_region_node_memberships

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    # Add matching region and node
    region = PLEXOSRegion(name="WEST")
    node = PLEXOSNode(name="WEST")
    target_system.add_component(region)
    target_system.add_component(node)

    ensure_region_node_memberships(context)

    # Should have created membership
    from r2x_plexos.models import PLEXOSMembership

    memberships = list(target_system.get_supplemental_attributes(PLEXOSMembership))
    assert len(memberships) >= 1


def test_ensure_region_node_memberships_handles_missing_node() -> None:
    """ensure_region_node_memberships handles region without matching node."""
    from r2x_plexos.models import PLEXOSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import ensure_region_node_memberships

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    # Add region without matching node
    region = PLEXOSRegion(name="WEST")
    target_system.add_component(region)

    # Should not raise error
    ensure_region_node_memberships(context)


def test_ensure_generator_node_memberships_creates_memberships() -> None:
    """ensure_generator_node_memberships creates generator-node memberships."""
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSNode
    from r2x_reeds.models import ReEDSGenerator, ReEDSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import ensure_generator_node_memberships

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    # Create source generator with region
    region = ReEDSRegion(name="WEST")
    source_gen = ReEDSGenerator(name="gen1", region=region, capacity=100.0, technology="COAL")
    source_system.add_component(region)
    source_system.add_component(source_gen)

    # Create target generator and node
    target_gen = PLEXOSGenerator(name="gen1")
    node = PLEXOSNode(name="WEST")
    target_system.add_component(target_gen)
    target_system.add_component(node)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    ensure_generator_node_memberships(context)

    # Should have created membership
    from r2x_plexos.models import PLEXOSMembership

    memberships = list(target_system.get_supplemental_attributes(PLEXOSMembership))
    assert len(memberships) >= 1


def test_link_line_memberships_creates_node_memberships() -> None:
    """link_line_memberships creates node-from and node-to memberships."""
    from r2x_plexos.models import PLEXOSLine, PLEXOSNode
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion, ReEDSTransmissionLine
    from r2x_reeds.models.base import FromTo_ToFrom
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import link_line_memberships

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    # Create source regions and interface
    region_a = ReEDSRegion(name="WEST")
    region_b = ReEDSRegion(name="EAST")
    interface = ReEDSInterface(name="WEST_EAST", from_region=region_a, to_region=region_b)

    # Create transmission line with required fields
    max_power = FromTo_ToFrom(from_to=1000.0, to_from=1000.0)
    source_line = ReEDSTransmissionLine(name="line1", interface=interface, max_active_power=max_power)

    source_system.add_component(region_a)
    source_system.add_component(region_b)
    source_system.add_component(interface)
    source_system.add_component(source_line)

    # Create target line and nodes
    target_line = PLEXOSLine(name="line1")
    node_a = PLEXOSNode(name="WEST")
    node_b = PLEXOSNode(name="EAST")
    target_system.add_component(target_line)
    target_system.add_component(node_a)
    target_system.add_component(node_b)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    link_line_memberships(context)

    # Should have created NodeFrom and NodeTo memberships
    from r2x_plexos.models import PLEXOSMembership

    memberships = list(target_system.get_supplemental_attributes(PLEXOSMembership))
    assert len(memberships) >= 2


def test_attach_region_load_profiles_transfers_load() -> None:
    """attach_region_load_profiles transfers demand to regions."""
    from r2x_plexos.models import PLEXOSRegion
    from r2x_reeds.models import ReEDSDemand, ReEDSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import attach_region_load_profiles

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    # Create source region and demand
    source_region = ReEDSRegion(name="WEST")
    demand = ReEDSDemand(name="demand1", region=source_region, max_active_power=500.0)
    source_system.add_component(source_region)
    source_system.add_component(demand)

    # Create target region
    target_region = PLEXOSRegion(name="WEST")
    target_system.add_component(target_region)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    attach_region_load_profiles(context)

    # Should have set fixed_load
    assert target_region.fixed_load == pytest.approx(500.0)


def test_attach_region_load_profiles_handles_missing_region() -> None:
    """attach_region_load_profiles handles demand without matching region."""
    from r2x_reeds.models import ReEDSDemand, ReEDSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import attach_region_load_profiles

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    # Create source demand without target region
    source_region = ReEDSRegion(name="WEST")
    demand = ReEDSDemand(name="demand1", region=source_region, max_active_power=500.0)
    source_system.add_component(source_region)
    source_system.add_component(demand)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    # Should not raise error
    attach_region_load_profiles(context)


def test_attach_emissions_to_generators_copies_emissions() -> None:
    """attach_emissions_to_generators copies emission metadata."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models import ReEDSEmission, ReEDSGenerator, ReEDSRegion
    from r2x_reeds.models.enums import EmissionSource, EmissionType
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import attach_emissions_to_generators

    from r2x_core import System, TranslationContext

    source_system = System(name="source", auto_add_composed_components=True)
    target_system = System(name="target", auto_add_composed_components=True)

    # Create source generator with emission
    region = ReEDSRegion(name="WEST")
    source_gen = ReEDSGenerator(name="gen1", region=region, capacity=100.0, technology="COAL")
    emission = ReEDSEmission(rate=0.95, type=EmissionType.CO2, source=EmissionSource.COMBUSTION)
    source_system.add_component(region)
    source_system.add_component(source_gen)
    source_system.add_supplemental_attribute(source_gen, emission)

    # Create target generator
    target_gen = PLEXOSGenerator(name="gen1")
    target_system.add_component(target_gen)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    attach_emissions_to_generators(context)

    # Should have copied emission
    emissions = list(target_system.get_supplemental_attributes_with_component(target_gen, ReEDSEmission))
    assert len(emissions) >= 1


def test_convert_pumped_storage_generators_creates_storage() -> None:
    """convert_pumped_storage_generators creates storage components."""
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSStorage
    from r2x_reeds.models import ReEDSGenerator, ReEDSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import convert_pumped_storage_generators

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    # Create pumped hydro generator
    region = ReEDSRegion(name="WEST")
    source_gen = ReEDSGenerator(name="pumped1", region=region, capacity=100.0, technology="pumped-hydro")
    source_system.add_component(region)
    source_system.add_component(source_gen)

    # Create target generator
    target_gen = PLEXOSGenerator(name="pumped1")
    target_system.add_component(target_gen)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    convert_pumped_storage_generators(context)

    # Should have created storage component
    storages = list(target_system.get_components(PLEXOSStorage))
    assert len(storages) >= 1
    assert storages[0].name == "pumped1"


def test_convert_pumped_storage_generators_handles_non_pumped() -> None:
    """convert_pumped_storage_generators ignores non-pumped generators."""
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSStorage
    from r2x_reeds.models import ReEDSGenerator, ReEDSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import convert_pumped_storage_generators

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    # Create non-pumped generator
    region = ReEDSRegion(name="WEST")
    source_gen = ReEDSGenerator(name="coal1", region=region, capacity=100.0, technology="COAL")
    source_system.add_component(region)
    source_system.add_component(source_gen)

    # Create target generator
    target_gen = PLEXOSGenerator(name="coal1")
    target_system.add_component(target_gen)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    convert_pumped_storage_generators(context)

    # Should not have created storage
    storages = list(target_system.get_components(PLEXOSStorage))
    assert len(storages) == 0


def test_transfer_time_series_to_generators_transfers_series() -> None:
    """transfer_time_series_to_generators transfers time series data."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_reeds.models import ReEDSGenerator, ReEDSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import transfer_time_series_to_generators

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    # Create source generator
    region = ReEDSRegion(name="WEST")
    source_gen = ReEDSGenerator(name="gen1", region=region, capacity=100.0, technology="WIND")
    source_system.add_component(region)
    source_system.add_component(source_gen)

    # Create target generator
    target_gen = PLEXOSGenerator(name="gen1")
    target_system.add_component(target_gen)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    # Should not raise error even if no time series exist
    transfer_time_series_to_generators(context)


def test_ensure_generator_node_memberships_internal_function() -> None:
    """_ensure_generator_node_memberships creates memberships."""
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSNode
    from r2x_reeds.models import ReEDSRegion
    from r2x_reeds_to_plexos import ReedsToPlexosConfig
    from r2x_reeds_to_plexos.getters_utils import _ensure_generator_node_memberships

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=ReedsToPlexosConfig(),
        rules=[],
    )

    # Create mock source generator
    class MockSourceGen:
        def __init__(self):
            self.region = ReEDSRegion(name="WEST")

    source_gen = MockSourceGen()
    generator = PLEXOSGenerator(name="gen1")
    node = PLEXOSNode(name="WEST")
    target_system.add_component(generator)
    target_system.add_component(node)

    nodes_by_name = {"WEST": node}

    memberships = _ensure_generator_node_memberships(context, source_gen, generator, nodes_by_name)

    assert len(memberships) >= 1


def test_pumped_storage_techs_constant_exists() -> None:
    """PUMPED_STORAGE_TECHS constant is defined."""
    from r2x_reeds_to_plexos.getters_utils import PUMPED_STORAGE_TECHS

    assert isinstance(PUMPED_STORAGE_TECHS, set)
    assert "pumped-hydro" in PUMPED_STORAGE_TECHS
    assert "pumped_storage" in PUMPED_STORAGE_TECHS
