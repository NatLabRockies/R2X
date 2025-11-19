"""Configuration for Sienna-to-PLEXOS translation."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from r2x_core.plugin_config import PluginConfig


class SiennaToPlexosConfig(PluginConfig):
    prime_mover_mapping: Annotated[
        dict[str, list[str]],
        Field(
            default_factory=dict,
            description="Prime mover/fuel to technology category mappings",
        ),
    ]
    models: Annotated[
        list[str],
        Field(
            default_factory=lambda: ["r2x_sienna.models", "r2x_plexos.models"],
            description=(
                "Importable module paths where component types are defined. "
                "Each entry should be a fully qualified Python module path. "
                "Example: ['r2x_sienna.models', 'r2x_plexos.models']"
            ),
        ),
    ]
