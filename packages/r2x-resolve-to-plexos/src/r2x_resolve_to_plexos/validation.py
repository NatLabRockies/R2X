"""Validation helpers for Resolve-to-PLEXOS translations."""

from __future__ import annotations

from typing import Any

from infrasys import Component

from r2x_core import Err, Ok, Result, System

_COMPONENT_COUNT_MAP: tuple[tuple[str, str, str], ...] = (
    ("ResolveZone", "PLEXOSNode", "zones"),
    ("ResolveGenerator", "PLEXOSGenerator", "generators"),
    ("ResolveLoad", "PLEXOSPurchaser", "loads"),
    ("ResolveInterface", "PLEXOSInterface", "interfaces"),
)


def _count_components(system: System, component_type: type[Any]) -> int:
    """Count components of one type in a system."""
    return sum(1 for _ in system.get_components(component_type))


def _count_named_components(system: System, type_name: str) -> int:
    """Count components by their public class name."""
    return sum(1 for component in system.get_components(Component) if type(component).__name__ == type_name)


def validate_component_counts(source: System, target: System) -> Result[None, ValueError]:
    """Validate one-to-one Resolve-to-PLEXOS component counts.

    Resolve zones, generators, loads, and interfaces each produce one PLEXOS
    component of the corresponding target type. The check is intentionally at
    the package boundary so a partially applied or incomplete rule set cannot
    be reported as a successful translation.
    """
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSInterface, PLEXOSNode, PLEXOSPurchaser

    target_types: dict[str, type[Any]] = {
        "PLEXOSNode": PLEXOSNode,
        "PLEXOSGenerator": PLEXOSGenerator,
        "PLEXOSPurchaser": PLEXOSPurchaser,
        "PLEXOSInterface": PLEXOSInterface,
    }

    source_components = list(source.get_components(Component))
    source_type_by_name = {type(component).__name__: type(component) for component in source_components}
    mismatches: list[str] = []
    for source_name, target_name, label in _COMPONENT_COUNT_MAP:
        source_type = source_type_by_name.get(source_name)
        source_count = _count_components(source, source_type) if source_type is not None else 0
        target_count = _count_components(target, target_types[target_name])
        if source_count != target_count:
            mismatches.append(f"{label}: {source_count} Resolve -> {target_count} PLEXOS")

    if mismatches:
        return Err(ValueError("Component count validation failed: " + "; ".join(mismatches)))
    return Ok(None)
