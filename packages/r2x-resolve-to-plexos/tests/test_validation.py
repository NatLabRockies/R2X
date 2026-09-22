"""Tests for package-level Resolve-to-PLEXOS validation."""

from __future__ import annotations

from r2x_resolve_to_plexos.validation import validate_component_counts
from source_components import ResolveGenerator, ResolveInterface, ResolveLoad, ResolveZone

from r2x_core import System


def test_component_count_validation_rejects_incomplete_translation() -> None:
    """Mismatched source and target component counts fail validation."""
    source = System(name="source", auto_add_composed_components=True)
    zone = ResolveZone(name="z1")
    to_zone = ResolveZone(name="z2")
    source.add_component(zone)
    source.add_component(to_zone)
    source.add_component(ResolveGenerator(name="g1", zone=zone, capacity_mw=10))
    source.add_component(ResolveLoad(name="l1", zone=zone, demand_mw=5))
    source.add_component(
        ResolveInterface(
            name="i1",
            from_zone=zone,
            to_zone=to_zone,
            transfer_limit_mw=10,
        )
    )

    target = System(name="target")
    result = validate_component_counts(source, target)
    assert result.is_err()
    assert result.error is not None
    assert "Component count validation failed" in str(result.error)
    assert "generators: 1 Resolve -> 0 PLEXOS" in str(result.error)
