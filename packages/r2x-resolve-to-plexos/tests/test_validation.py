"""Tests for package-level Resolve-to-PLEXOS validation."""

from __future__ import annotations

from fixture_system import resolve_system
from r2x_resolve_to_plexos.validation import validate_component_counts

from r2x_core import System


def test_component_count_validation_rejects_incomplete_translation() -> None:
    """Mismatched source and target component counts fail validation."""
    result = validate_component_counts(resolve_system(), System(name="target"))
    assert result.is_err()
    assert result.error is not None
    assert "Component count validation failed" in str(result.error)
    assert "generators: 8 Resolve -> 0 PLEXOS" in str(result.error)
    assert "regions: 3 Resolve -> 0 PLEXOS" in str(result.error)
