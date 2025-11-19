"""Configuration for Sienna-to-PLEXOS translation."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from r2x_core import PluginConfig


class SiennaToPlexosConfig(PluginConfig):
    prime_mover_mapping: Annotated[
        dict[str, list[str]],
        Field(
            default_factory=dict,
            description="Prime mover/fuel to technology category mappings",
        ),
    ]
