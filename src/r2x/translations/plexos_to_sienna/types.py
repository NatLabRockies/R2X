"""Data models for PLEXOS to Sienna category mappings."""

from typing import Literal

from pydantic import BaseModel, Field


class GeneratorCategoryMapping(BaseModel):
    """Mapping configuration for a single generator category.

    Parameters
    ----------
    sienna_type : str
        Target Sienna component type ("ThermalStandard", "RenewableDispatch", "HydroDispatch")
    prime_mover : str
        Prime mover type code (e.g., "ST", "CT", "GT", "WT", "PVe", "HY")
    fuel_type : str | None
        Fuel type code (e.g., "COAL", "NATURAL_GAS", "NUCLEAR") or None for renewables

    Examples
    --------
    >>> mapping = GeneratorCategoryMapping(
    ...     sienna_type="ThermalStandard",
    ...     prime_mover="ST",
    ...     fuel_type="COAL"
    ... )
    """

    sienna_type: Literal["ThermalStandard", "RenewableDispatch", "HydroDispatch"]
    prime_mover: str
    fuel_type: str | None = None


class CategoryMappings(BaseModel):
    """Complete set of category mappings.

    Parameters
    ----------
    generator_categories : dict[str, GeneratorCategoryMapping]
        Mapping from PLEXOS category name to Sienna component configuration

    Examples
    --------
    >>> mappings = CategoryMappings(
    ...     generator_categories={
    ...         "Coal": GeneratorCategoryMapping(
    ...             sienna_type="ThermalStandard",
    ...             prime_mover="ST",
    ...             fuel_type="COAL"
    ...         )
    ...     }
    ... )
    """

    generator_categories: dict[str, GeneratorCategoryMapping] = Field(default_factory=dict)


class MappingFileConfig(BaseModel):
    """Configuration for loading mappings from an external file.

    Parameters
    ----------
    defaults : str
        How to handle default mappings: "built-in" to use defaults, "none" to start empty
    overrides : dict[str, GeneratorCategoryMapping]
        Category mappings that override defaults
    additions : dict[str, GeneratorCategoryMapping]
        New category mappings to add (not in defaults)

    Examples
    --------
    >>> config = MappingFileConfig(
    ...     defaults="built-in",
    ...     overrides={"Coal": GeneratorCategoryMapping(...)},
    ...     additions={"Custom Type": GeneratorCategoryMapping(...)}
    ... )
    """

    defaults: Literal["built-in", "none"] = "built-in"
    overrides: dict[str, GeneratorCategoryMapping] = Field(default_factory=dict)
    additions: dict[str, GeneratorCategoryMapping] = Field(default_factory=dict)
