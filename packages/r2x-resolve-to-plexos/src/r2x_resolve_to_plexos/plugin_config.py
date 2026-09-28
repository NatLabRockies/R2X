"""Configuration for Resolve-to-PLEXOS translation."""

from __future__ import annotations

from r2x_core import PluginConfig


class ResolveToPlexosConfig(PluginConfig):
    """Configuration for the Resolve-to-PLEXOS transform."""

    models: tuple[str, ...] = (
        "r2x_resolve",
        "r2x_plexos.models",
        "r2x_resolve_to_plexos.getters",
    )
