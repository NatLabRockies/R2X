"""Validation helpers for Resolve-to-PLEXOS translations."""

from __future__ import annotations

from typing import Any

from r2x_plexos.models import (
    PLEXOSFuel,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSRegion,
)
from r2x_resolve import (
    InvestmentComponent,
    ResolveFuel,
    ResolveGroupedInterface,
    ResolveTransmissionLine,
    ResolveZone,
)

from r2x_core import Err, Ok, Result, System

_COMPONENT_COUNT_MAP: tuple[tuple[type[Any], type[Any], str], ...] = (
    (ResolveZone, PLEXOSNode, "nodes"),
    (ResolveZone, PLEXOSRegion, "regions"),
    (InvestmentComponent, PLEXOSGenerator, "generators"),
    (ResolveFuel, PLEXOSFuel, "fuels"),
    (ResolveTransmissionLine, PLEXOSLine, "lines"),
    (ResolveGroupedInterface, PLEXOSInterface, "interfaces"),
)


def _count(system: System, component_type: type[Any]) -> int:
    """Count components of one type, including subclasses."""
    return sum(1 for _ in system.get_components(component_type))


def validate_component_counts(source: System, target: System) -> Result[None, ValueError]:
    """Validate one-to-one Resolve-to-PLEXOS component counts.

    Every Resolve zone becomes a PLEXOS Node and Region, and every generator,
    fuel, line, and grouped interface becomes one PLEXOS component. The check is
    at the package boundary so a partially applied rule set cannot be reported
    as a successful translation.
    """
    mismatches = [
        f"{label}: {_count(source, source_type)} Resolve -> {_count(target, target_type)} PLEXOS"
        for source_type, target_type, label in _COMPONENT_COUNT_MAP
        if _count(source, source_type) != _count(target, target_type)
    ]
    if mismatches:
        return Err(ValueError("Component count validation failed: " + "; ".join(mismatches)))
    return Ok(None)
