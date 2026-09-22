"""Minimal Resolve-shaped source components for package tests."""

from __future__ import annotations

from infrasys import Component
from pydantic import Field


class ResolveZone(Component):
    """Resolve zone-shaped test component."""

    ext: dict[str, object] = Field(default_factory=dict)


class ResolveGenerator(Component):
    """Resolve generator-shaped test component."""

    zone: ResolveZone
    capacity_mw: float
    ext: dict[str, object] = Field(default_factory=dict)


class ResolveLoad(Component):
    """Resolve load-shaped test component."""

    zone: ResolveZone
    demand_mw: float
    ext: dict[str, object] = Field(default_factory=dict)


class ResolveInterface(Component):
    """Resolve interface-shaped test component."""

    from_zone: ResolveZone
    to_zone: ResolveZone
    transfer_limit_mw: float
    ext: dict[str, object] = Field(default_factory=dict)
