"""Configuration for Sienna-to-PLEXOS translation."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from r2x_core import PluginConfig


class SiennaToPlexosConfig(PluginConfig):
    models: tuple[str, ...] = Field(
        default=("r2x_sienna.models", "r2x_plexos.models"),
        description="Modules used to resolve Sienna sources and PLEXOS targets.",
    )
    prime_mover_mapping: Annotated[
        dict[str, list[str]],
        Field(
            default_factory=dict,
            description="Prime mover/fuel to technology category mappings",
        ),
    ]
