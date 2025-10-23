"""Category mapping loader and merger for PLEXOS to Sienna translation."""

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from loguru import logger
from r2x_sienna.models import HydroDispatch, RenewableDispatch, ThermalStandard
from r2x_sienna.models.base import SiennaComponent
from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels

from r2x_core import Err, Ok, Result

from .types import GeneratorCategoryMapping, MappingFileConfig

# Type string to class mapping
SIENNA_TYPE_MAP: dict[str, type[SiennaComponent]] = {
    "ThermalStandard": ThermalStandard,
    "RenewableDispatch": RenewableDispatch,
    "HydroDispatch": HydroDispatch,
}

# Prime mover string to enum mapping
PRIME_MOVER_MAP: dict[str, PrimeMoversType] = {
    "ST": PrimeMoversType.ST,
    "GT": PrimeMoversType.GT,
    "CT": PrimeMoversType.CT,
    "CC": PrimeMoversType.CC,
    "IC": PrimeMoversType.IC,
    "CA": PrimeMoversType.CA,
    "WT": PrimeMoversType.WT,
    "PVe": PrimeMoversType.PVe,
    "HY": PrimeMoversType.HY,
    "PS": PrimeMoversType.PS,
    "OT": PrimeMoversType.OT,
}

# Fuel type string to enum mapping
FUEL_TYPE_MAP: dict[str, ThermalFuels] = {
    "COAL": ThermalFuels.COAL,
    "NATURAL_GAS": ThermalFuels.NATURAL_GAS,
    "DISTILLATE_FUEL_OIL": ThermalFuels.DISTILLATE_FUEL_OIL,
    "NUCLEAR": ThermalFuels.NUCLEAR,
    "GEOTHERMAL": ThermalFuels.GEOTHERMAL,
    "AG_BIOPRODUCT": ThermalFuels.AG_BIOPRODUCT,
    "MUNICIPAL_WASTE": ThermalFuels.MUNICIPAL_WASTE,
    "WOOD_WASTE": ThermalFuels.WOOD_WASTE,
    "OTHER": ThermalFuels.OTHER,
}


def load_default_mappings() -> dict[str, GeneratorCategoryMapping]:
    """Load built-in default category mappings from translation config.

    Returns
    -------
    dict[str, GeneratorCategoryMapping]
        Dictionary mapping PLEXOS category names to mapping configurations

    Examples
    --------
    >>> defaults = load_default_mappings()
    >>> coal_mapping = defaults["Coal"]
    >>> print(coal_mapping.sienna_type)
    ThermalStandard
    """
    # Get the path to defaults.json in the config directory
    config_dir = Path(__file__).parent / "config"
    defaults_file = config_dir / "defaults.json"

    if not defaults_file.exists():
        logger.warning("Defaults file not found: {}", defaults_file)
        return {}

    try:
        with open(defaults_file) as f:
            data = json.load(f)

        generator_categories = data.get("generator_categories", {})

        # Convert to GeneratorCategoryMapping objects
        mappings = {}
        for category, mapping_data in generator_categories.items():
            try:
                mappings[category] = GeneratorCategoryMapping(**mapping_data)
            except Exception as e:
                logger.warning("Failed to parse mapping for category '{}': {}", category, e)

        logger.debug("Loaded {} default category mappings", len(mappings))
        return mappings

    except json.JSONDecodeError as e:
        logger.error("Failed to parse defaults JSON from {}: {}", defaults_file, e)
        return {}


def load_mappings_from_file(file_path: str) -> Result[MappingFileConfig, str]:
    """Load category mappings from an external YAML file.

    Parameters
    ----------
    file_path : str
        Path to the YAML mapping file

    Returns
    -------
    Result[MappingFileConfig, str]
        Ok with parsed configuration or Err with error message

    Examples
    --------
    >>> result = load_mappings_from_file("./custom-mappings.yaml")
    >>> if result.is_ok():
    ...     config = result.unwrap()
    ...     print(config.defaults)
    built-in
    """
    path = Path(file_path)

    if not path.exists():
        return Err(f"Mapping file not found: {file_path}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            return Err(f"Mapping file must contain a YAML dictionary: {file_path}")

        # Parse into MappingFileConfig
        config = MappingFileConfig(**data)
        logger.debug("Loaded mappings from file: {}", file_path)
        return Ok(config)

    except yaml.YAMLError as e:
        return Err(f"Failed to parse YAML from {file_path}: {e}")
    except Exception as e:
        return Err(f"Failed to load mappings from {file_path}: {e}")


def merge_mappings(
    defaults: dict[str, GeneratorCategoryMapping],
    overrides: dict[str, dict[str, Any]],
    strategy: str,
) -> dict[str, GeneratorCategoryMapping]:
    """Merge category mappings according to the specified strategy.

    Parameters
    ----------
    defaults : dict[str, GeneratorCategoryMapping]
        Default category mappings
    overrides : dict[str, dict[str, Any]]
        Override mappings to apply
    strategy : str
        Merge strategy: "merge", "replace", or "extend"

    Returns
    -------
    dict[str, GeneratorCategoryMapping]
        Merged category mappings

    Notes
    -----
    Strategies:
    - "merge": Start with defaults, override with user mappings (default behavior)
    - "replace": Ignore defaults, use only user mappings
    - "extend": Keep defaults, only add new categories (don't override existing)

    Examples
    --------
    >>> defaults = {"Coal": GeneratorCategoryMapping(...)}
    >>> overrides = {"Gas": {...}}
    >>> result = merge_mappings(defaults, overrides, "merge")
    """
    if strategy == "replace":
        # Ignore defaults, use only overrides
        result = {}
    elif strategy == "extend":
        # Start with defaults, only add new categories
        result = defaults.copy()
    else:  # "merge" is default
        # Start with defaults, allow overrides
        result = defaults.copy()

    # Apply overrides
    for category, mapping_data in overrides.items():
        if strategy == "extend" and category in result:
            # Skip if already exists (extend mode)
            logger.debug("Skipping category '{}' (extend mode, already exists)", category)
            continue

        try:
            result[category] = GeneratorCategoryMapping(**mapping_data)
            logger.debug("Applied mapping for category '{}'", category)
        except Exception as e:
            logger.warning("Failed to parse override mapping for category '{}': {}", category, e)

    logger.debug("Merged mappings: {} categories (strategy={})", len(result), strategy)
    return result


def resolve_mapping(
    mapping: GeneratorCategoryMapping,
) -> Result[tuple[type[SiennaComponent], PrimeMoversType, ThermalFuels | None], str]:
    """Convert a mapping configuration to actual types and enums.

    Parameters
    ----------
    mapping : GeneratorCategoryMapping
        Mapping configuration with string values

    Returns
    -------
    Result[tuple[type, PrimeMoversType, ThermalFuels | None], str]
        Ok with (sienna_type_class, prime_mover_enum, fuel_type_enum) or Err with message

    Examples
    --------
    >>> mapping = GeneratorCategoryMapping(
    ...     sienna_type="ThermalStandard",
    ...     prime_mover="ST",
    ...     fuel_type="COAL"
    ... )
    >>> result = resolve_mapping(mapping)
    >>> if result.is_ok():
    ...     sienna_type, prime_mover, fuel_type = result.unwrap()
    ...     print(sienna_type.__name__)
    ThermalStandard
    """
    # Resolve Sienna type
    sienna_type_class = SIENNA_TYPE_MAP.get(mapping.sienna_type)
    if sienna_type_class is None:
        return Err(f"Unknown sienna_type: {mapping.sienna_type}")

    # Resolve prime mover
    prime_mover_enum = PRIME_MOVER_MAP.get(mapping.prime_mover)
    if prime_mover_enum is None:
        return Err(f"Unknown prime_mover: {mapping.prime_mover}")

    # Resolve fuel type (optional)
    fuel_type_enum = None
    if mapping.fuel_type is not None:
        fuel_type_enum = FUEL_TYPE_MAP.get(mapping.fuel_type)
        if fuel_type_enum is None:
            return Err(f"Unknown fuel_type: {mapping.fuel_type}")

    return Ok((sienna_type_class, prime_mover_enum, fuel_type_enum))


def validate_mapping(mapping: dict[str, Any]) -> Result[None, str]:
    """Validate a single mapping dictionary.

    Parameters
    ----------
    mapping : dict[str, Any]
        Mapping dictionary to validate

    Returns
    -------
    Result[None, str]
        Ok if valid, Err with message if invalid

    Examples
    --------
    >>> mapping = {"sienna_type": "ThermalStandard", "prime_mover": "ST", "fuel_type": "COAL"}
    >>> result = validate_mapping(mapping)
    >>> assert result.is_ok()
    """
    try:
        # Try to create GeneratorCategoryMapping (validates structure)
        parsed = GeneratorCategoryMapping(**mapping)

        # Try to resolve to actual types (validates enum values)
        resolve_result = resolve_mapping(parsed)
        if resolve_result.is_err():
            err_msg: str = resolve_result.err() or "Unknown error"
            return Err(err_msg)

        return Ok(None)

    except Exception as e:
        return Err(f"Invalid mapping: {e}")


def validate_mappings_file(file_path: str) -> Result[None, str]:
    """Validate an entire category mappings file.

    Parameters
    ----------
    file_path : str
        Path to the mapping file

    Returns
    -------
    Result[None, str]
        Ok if valid, Err with message if invalid

    Examples
    --------
    >>> result = validate_mappings_file("./custom-mappings.yaml")
    >>> if result.is_ok():
    ...     print("Mapping file is valid")
    """
    # Load the file
    load_result = load_mappings_from_file(file_path)
    if load_result.is_err():
        err_msg: str = load_result.err() or "Unknown error"
        return Err(err_msg)

    config = load_result.unwrap()

    # Validate each mapping in overrides
    for category, mapping in config.overrides.items():
        dict_mapping = mapping.model_dump()
        validate_result = validate_mapping(dict_mapping)
        if validate_result.is_err():
            return Err(f"Invalid override for category '{category}': {validate_result.err()}")

    # Validate each mapping in additions
    for category, mapping in config.additions.items():
        dict_mapping = mapping.model_dump()
        validate_result = validate_mapping(dict_mapping)
        if validate_result.is_err():
            return Err(f"Invalid addition for category '{category}': {validate_result.err()}")

    return Ok(None)
