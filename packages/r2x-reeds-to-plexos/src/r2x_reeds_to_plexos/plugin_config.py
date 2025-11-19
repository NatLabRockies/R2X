"""Configuration for ReEDS-to-PLEXOS translation."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from r2x_core import PluginConfig


class ReedsToPlexosConfig(PluginConfig):
    models: tuple[str, ...] = Field(
        default=("r2x_reeds.models", "r2x_plexos.models"),
        description="Modules used to resolve ReEDS sources and PLEXOS targets.",
    )
    commit_technologies: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Technologies to commit.",
        ),
    ]
