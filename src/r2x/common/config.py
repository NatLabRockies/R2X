"""Translation configuration classes."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class TranslationConfig(BaseModel):
    """Base configuration for translations."""

    verbose: bool = Field(
        default=False,
        description="Enable verbose logging",
    )


class PLEXOSToSiennaConfig(TranslationConfig):
    """Configuration for PLEXOS to Sienna translation."""

    system_base_power: float = Field(
        default=100.0,
        description="System base power in MW for per-unit calculations",
        gt=0,
    )

    default_voltage_kv: float = Field(
        default=110.0,
        description="Default voltage in kV for buses without voltage data",
        gt=0,
    )

    category_mappings: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Inline category mapping overrides (PLEXOS category -> {sienna_type, prime_mover, fuel_type})",
    )

    mappings_file: str | None = Field(
        default=None,
        description="Path to external category mappings YAML file",
    )

    mapping_strategy: Literal["merge", "replace", "extend"] = Field(
        default="merge",
        description="How to combine mappings: merge (override defaults), replace (ignore defaults), extend (only add new)",
    )
