"""Configuration for ReEDS-to-PLEXOS translation."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator

from r2x_core import PluginConfig


class ReedsToPlexosConfig(PluginConfig):
    models: tuple[str, ...] = Field(
        default=("r2x_reeds.models", "r2x_plexos.models", "r2x_reeds_to_plexos.getters_utils"),
        description="Modules used to resolve ReEDS sources and PLEXOS targets.",
    )
    commit_technologies: Annotated[
        list[str] | None,
        Field(
            default_factory=list,
            description="Technologies to commit.",
        ),
    ]
    hydro_budget_ts: Literal["hourly", "daily", "weekly", "monthly"] = Field(
        default="daily",
        description="Output resolution for hydro budget time series.",
    )
    missing_ramp_rate_fraction_per_minute: float | None = Field(
        default=1.0,
        ge=0.0,
        allow_inf_nan=False,
        description=(
            "Fraction of final generator capacity per minute used for generators whose "
            "translation rules apply ramp limits, with neither a source ramp rate nor "
            "a usable translator default. "
            "Set to null to fail translation instead."
        ),
    )

    @field_validator("missing_ramp_rate_fraction_per_minute", mode="before")
    @classmethod
    def reject_boolean_ramp_rate(cls, value: object) -> object:
        """Require a numeric fallback or null, not a boolean."""
        if isinstance(value, bool):
            raise ValueError("missing_ramp_rate_fraction_per_minute must be numeric or null, not boolean")
        return value

    use_fuel_objects: bool = Field(
        default=False,
        description=(
            "Create PLEXOS Fuel objects from ReEDS fuel data and link generators through the "
            "Fuels collection instead of writing fuel price on each generator."
        ),
    )
