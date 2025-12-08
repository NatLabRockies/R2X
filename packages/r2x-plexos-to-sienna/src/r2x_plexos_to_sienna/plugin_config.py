"""Configuration for PLEXOS-to-Sienna translation."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from r2x_core import PluginConfig


class PlexosToSiennaConfig(PluginConfig):
    models: tuple[str, ...] = Field(
        default=("r2x_plexos.models", "r2x_sienna.models"),
        description="Modules used to resolve PLEXOS sources and Sienna targets.",
    )
    technology_mapping: Annotated[
        dict[str, dict[str, str]],
        Field(
            default_factory=dict,
            description="Technology category to prime mover/fuel type mappings",
        ),
    ]
