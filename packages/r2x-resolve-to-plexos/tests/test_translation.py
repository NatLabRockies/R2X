"""End-to-end tests for Resolve-to-PLEXOS translation."""

from __future__ import annotations

from r2x_plexos.models import PLEXOSGenerator, PLEXOSInterface, PLEXOSMembership, PLEXOSNode, PLEXOSPurchaser
from r2x_resolve_to_plexos import ResolveToPlexosConfig, resolve_to_plexos
from source_components import ResolveGenerator, ResolveInterface, ResolveLoad, ResolveZone

from r2x_core import System


class ResolveTestConfig(ResolveToPlexosConfig):
    """Resolve-to-PLEXOS configuration using test-local source model types."""

    models: tuple[str, ...] = (
        "source_components",
        "r2x_resolve_to_plexos.getters",
        "r2x_plexos.models",
    )


def test_resolve_to_plexos_translates_components_and_memberships() -> None:
    """The public transform creates all target components and memberships."""
    source = System(name="resolve", auto_add_composed_components=True)
    zone_a = ResolveZone(name="z1")
    zone_b = ResolveZone(name="z2")
    source.add_component(zone_a)
    source.add_component(zone_b)
    source.add_component(ResolveGenerator(name="g1", zone=zone_a, capacity_mw=10))
    source.add_component(ResolveLoad(name="l1", zone=zone_a, demand_mw=5))
    source.add_component(ResolveInterface(name="i1", from_zone=zone_a, to_zone=zone_b, transfer_limit_mw=20))

    target = resolve_to_plexos(source, ResolveTestConfig())

    assert [node.name for node in target.get_components(PLEXOSNode)] == ["z1", "z2"]
    assert [generator.name for generator in target.get_components(PLEXOSGenerator)] == ["g1"]
    assert [purchaser.name for purchaser in target.get_components(PLEXOSPurchaser)] == ["l1"]
    assert [interface.name for interface in target.get_components(PLEXOSInterface)] == ["i1"]

    memberships = list(target.get_supplemental_attributes(PLEXOSMembership))
    assert len(memberships) == 4
    assert {
        (membership.parent_object.name, membership.child_object.name, membership.collection.value)
        for membership in memberships
    } == {
        ("l1", "z1", "Nodes"),
        ("g1", "z1", "Nodes"),
        ("i1", "z1", "NodeFrom"),
        ("i1", "z2", "NodeTo"),
    }
