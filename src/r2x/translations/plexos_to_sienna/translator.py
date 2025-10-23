"""Main translator for PLEXOS to Sienna conversion."""

import itertools
import sys
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger
from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator, PLEXOSLine, PLEXOSNode, PLEXOSRegion

from r2x.common.config import PLEXOSToSiennaConfig
from r2x_core import Err, Ok, Result, System

from .converters import convert_component, post_process_component
from .mapping_loader import load_default_mappings, load_mappings_from_file, merge_mappings, resolve_mapping
from .mappings import initialize_all_mappings
from .registry import get_registry
from .utils import configure_plexos_context, get_plexos_property


def initialize_mappings_from_config(config: PLEXOSToSiennaConfig) -> None:
    """Initialize category mappings registry from configuration.

    Loads and merges mappings from multiple sources according to the strategy:
    1. Load defaults (unless strategy="replace")
    2. Load from mappings_file if provided
    3. Apply inline category_mappings
    4. Merge according to mapping_strategy
    5. Register all final mappings

    Parameters
    ----------
    config : PLEXOSToSiennaConfig
        Translation configuration with mapping settings

    Examples
    --------
    >>> config = PLEXOSToSiennaConfig(
    ...     category_mappings={"Coal": {"sienna_type": "ThermalStandard", ...}},
    ...     mapping_strategy="merge"
    ... )
    >>> initialize_mappings_from_config(config)
    """
    registry = get_registry()

    # Step 1: Load defaults (unless strategy is "replace")
    if config.mapping_strategy != "replace":
        defaults = load_default_mappings()
        logger.debug("Loaded {} default mappings", len(defaults))
    else:
        defaults = {}
        logger.debug("Skipping defaults (strategy=replace)")

    # Step 2: Load from external file if provided
    file_mappings = {}
    if config.mappings_file:
        result = load_mappings_from_file(config.mappings_file)
        if result.is_ok():
            file_config = result.unwrap()

            # Handle file's defaults setting
            if file_config.defaults == "none":
                defaults = {}
                logger.debug("File specified defaults=none, clearing defaults")

            # Merge file overrides and additions
            for category, mapping in file_config.overrides.items():
                file_mappings[category] = mapping.model_dump()
            for category, mapping in file_config.additions.items():
                file_mappings[category] = mapping.model_dump()

            logger.debug("Loaded {} mappings from file", len(file_mappings))
        else:
            logger.warning("Failed to load mappings file: {}", result.err())

    # Step 3: Merge inline category_mappings with file mappings
    all_overrides = {**file_mappings, **config.category_mappings}

    # Step 4: Merge according to strategy
    final_mappings = merge_mappings(defaults, all_overrides, config.mapping_strategy)

    # Step 5: Clear registry and register all final mappings
    registry.clear()

    for category, mapping in final_mappings.items():
        # Resolve string values to actual types/enums
        resolve_result = resolve_mapping(mapping)
        if resolve_result.is_ok():
            sienna_type, prime_mover, fuel_type = resolve_result.unwrap()
            registry.register_from_dict(
                category,
                {
                    "sienna_type": sienna_type,
                    "prime_mover": prime_mover,
                    "fuel_type": fuel_type,
                },
            )
        else:
            logger.warning(
                "Failed to resolve mapping for category '{}': {}",
                category,
                resolve_result.err(),
            )

    logger.info(
        "Initialized {} category mappings (strategy={})", len(registry.list_keys()), config.mapping_strategy
    )


def translate_system(
    plexos_system: System,
    config: PLEXOSToSiennaConfig | None = None,
) -> Result[System, str]:
    """Translate a PLEXOS system to a Sienna system.

    Parameters
    ----------
    plexos_system : System
        Source PLEXOS system
    config : PLEXOSToSiennaConfig | None
        Translation configuration (uses defaults if None)

    Returns
    -------
    Result[System, str]
        Ok with Sienna system or Err with error message

    Examples
    --------
    >>> # Use defaults
    >>> result = translate_system(plexos_sys)

    >>> # Custom system base
    >>> config = PLEXOSToSiennaConfig(system_base_power=1000.0)
    >>> result = translate_system(plexos_sys, config)

    >>> # With custom mappings file
    >>> config = PLEXOSToSiennaConfig(
    ...     system_base_power=100.0,
    ...     mappings_file="custom_mappings.yaml"
    ... )
    >>> result = translate_system(plexos_sys, config)
    """
    # Use default config if not provided
    if config is None:
        config = PLEXOSToSiennaConfig()

    # Configure PLEXOS context resolution
    configure_plexos_context(config)

    # Initialize category mappings from configuration
    # If config has custom mappings, use them; otherwise fall back to defaults
    if config.category_mappings or config.mappings_file or config.mapping_strategy != "merge":
        initialize_mappings_from_config(config)
    else:
        # Use default hardcoded mappings for backward compatibility
        initialize_all_mappings()

    # Create new Sienna system
    sienna_system = System(
        name=f"{plexos_system.name}_sienna" if plexos_system.name else "sienna_system",
        auto_add_composed_components=True,
    )

    # Track conversion errors
    errors = []

    # Convert all components
    logger.info(
        "Converting PLEXOS components to Sienna (system_base={} MW)...",
        config.system_base_power,
    )
    custom_order = [PLEXOSNode, PLEXOSRegion, PLEXOSGenerator, PLEXOSBattery]
    order_map: dict[type[Any], int] = {cls: idx for idx, cls in enumerate(custom_order)}
    sorted_components = sorted(
        plexos_system.iter_all_components(),
        key=lambda c: order_map.get(type(c), float("inf")),
    )
    for component_type, group in itertools.groupby(sorted_components, key=type):
        logger.debug("Processing component type {}", component_type)
        for component in group:
            result = convert_component(component, plexos_system, sienna_system, config)
            if result.is_err():
                error_msg = result.err()
                logger.warning(error_msg)
                errors.append(error_msg)

    # Post-process components
    logger.info("Post-processing Sienna components...")
    # Convert to list to avoid "dictionary changed size during iteration" error
    # since post_process_component may add new components
    for component in list(sienna_system.iter_all_components()):
        result = post_process_component(component, plexos_system, sienna_system, config)
        if result.is_err():
            error_msg = result.err()
            logger.warning(error_msg)
            errors.append(error_msg)

    if errors:
        logger.warning("Translation completed with {} errors", len(errors))
    else:
        logger.info("Translation completed successfully")

    return Ok(sienna_system)


def translate_from_json_file(
    input_path: Path, config: PLEXOSToSiennaConfig | None = None
) -> Result[System, str]:
    """Load PLEXOS system from JSON and translate to Sienna.

    Parameters
    ----------
    input_path : Path
        Path to PLEXOS system JSON file
    config : PLEXOSToSiennaConfig | None
        Translation configuration

    Returns
    -------
    Result[System, str]
        Ok with Sienna system or Err with error message
    """
    try:
        logger.info("Loading PLEXOS system from {}", input_path)
        plexos_system = System.from_json(input_path, auto_add_composed_components=True)
        return translate_system(plexos_system, config)
    except Exception as e:
        return Err(f"Failed to load PLEXOS system: {e}")


def translate_from_stdin(config: PLEXOSToSiennaConfig | None = None) -> Result[System, str]:
    """Read PLEXOS system JSON from stdin and translate to Sienna.

    Parameters
    ----------
    config : PLEXOSToSiennaConfig | None
        Translation configuration

    Returns
    -------
    Result[System, str]
        Ok with Sienna system or Err with error message
    """
    try:
        logger.info("Reading PLEXOS system from stdin...")

        # Read JSON from stdin to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp.write(sys.stdin.read())
            tmp_path = Path(tmp.name)

        # Load and translate
        result = translate_from_json_file(tmp_path, config)

        # Clean up temp file
        tmp_path.unlink()

        return result

    except Exception as e:
        return Err(f"Failed to read from stdin: {e}")


def translate_from_bytes(data: bytes, config: PLEXOSToSiennaConfig | None = None) -> Result[System, str]:
    """Translate PLEXOS system from JSON bytes.

    Parameters
    ----------
    data : bytes
        JSON data as bytes
    config : PLEXOSToSiennaConfig | None
        Translation configuration

    Returns
    -------
    Result[System, str]
        Ok with Sienna system or Err with error message
    """
    try:
        logger.info("Reading PLEXOS system from bytes...")

        # Write bytes to temporary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        # Load and translate
        result = translate_from_json_file(tmp_path, config)

        # Clean up temp file
        tmp_path.unlink()

        return result

    except Exception as e:
        return Err(f"Failed to read from bytes: {e}")


def write_to_stdout(sienna_system: System) -> Result[None, str]:
    """Write Sienna system JSON to stdout.

    Parameters
    ----------
    sienna_system : System
        Sienna system to write

    Returns
    -------
    Result[None, str]
        Ok(None) on success, Err with error message on failure
    """
    try:
        # Write to temp file first
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "system.json"
            sienna_system.to_json(tmp_path, overwrite=True)

            # Read and write to stdout
            with open(tmp_path) as f:
                sys.stdout.write(f.read())

        return Ok(None)

    except Exception as e:
        return Err(f"Failed to write to stdout: {e}")


def system_to_bytes(sienna_system: System) -> Result[bytes, str]:
    """Convert Sienna system to JSON bytes.

    Parameters
    ----------
    sienna_system : System
        Sienna system to convert

    Returns
    -------
    Result[bytes, str]
        Ok with JSON bytes or Err with error message
    """
    try:
        # Write to temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "system.json"
            sienna_system.to_json(tmp_path, overwrite=True)

            # Read as bytes
            with open(tmp_path, "rb") as f:
                data = f.read()

        return Ok(data)

    except Exception as e:
        return Err(f"Failed to convert to bytes: {e}")


def dry_run(input_path: Path | str | System, config: PLEXOSToSiennaConfig | None = None) -> Result[None, str]:
    """Preview PLEXOS to Sienna translation without executing it.

    Parameters
    ----------
    input_path : Path | str | System
        PLEXOS system file path or System object
    config : PLEXOSToSiennaConfig | None
        Translation configuration

    Returns
    -------
    Result[DryRunReport, str]
        Ok with preview report or Err with error message

    Examples
    --------
    >>> result = dry_run("plexos_system.json")
    >>> if result.is_ok():
    ...     preview = result.unwrap()
    ...     print(preview.summary())
    """
    from r2x._core import DryRunReport

    try:
        if isinstance(input_path, System):
            plexos_system = input_path
        else:
            plexos_system = System.from_json(input_path, auto_add_composed_components=True)

        if config is None:
            config = PLEXOSToSiennaConfig()

        configure_plexos_context(config)

        if config.category_mappings or config.mappings_file or config.mapping_strategy != "merge":
            initialize_mappings_from_config(config)
        else:
            initialize_all_mappings()

        preview = DryRunReport()
        preview.metadata["system_base_power"] = config.system_base_power
        preview.metadata["default_voltage_kv"] = config.default_voltage_kv

        registry = get_registry()

        generators = list(plexos_system.get_components(PLEXOSGenerator))
        batteries = list(plexos_system.get_components(PLEXOSBattery))
        nodes = list(plexos_system.get_components(PLEXOSNode))
        regions = list(plexos_system.get_components(PLEXOSRegion))
        lines = list(plexos_system.get_components(PLEXOSLine))

        for gen in generators:
            if not gen.category:
                preview.add_skipped("PLEXOSGenerator", gen.name, "Missing category")
                continue

            mapping_result = registry.get(gen.category)
            if mapping_result.is_err():
                preview.add_skipped("PLEXOSGenerator", gen.name, f"Unknown category '{gen.category}'")
                continue

            capacity = get_plexos_property(plexos_system, gen, "max_capacity")
            rating_factor = get_plexos_property(plexos_system, gen, "rating_factor")

            if capacity * rating_factor == 0:
                preview.add_skipped("PLEXOSGenerator", gen.name, "Zero capacity")
                continue

            mapping = mapping_result.unwrap()
            sienna_type = mapping["sienna_type"].__name__
            preview.add_conversion("PLEXOSGenerator", sienna_type)
            preview.add_mapping(gen.category, sienna_type)

        for _battery in batteries:
            preview.add_conversion("PLEXOSBattery", "EnergyReservoirStorage")

        for node in nodes:
            preview.add_conversion("PLEXOSNode", "ACBus")
            load_value = get_plexos_property(plexos_system, node, "load")
            if load_value != 0:
                preview.add_conversion("PLEXOSNode", "PowerLoad")

        for region in regions:
            preview.add_conversion("PLEXOSRegion", "Area")
            load_value = get_plexos_property(plexos_system, region, "load")
            if load_value != 0:
                preview.add_conversion("PLEXOSRegion", "ACBus")
                preview.add_conversion("PLEXOSRegion", "PowerLoad")

        for _line in lines:
            preview.add_conversion("PLEXOSLine", "AreaInterchange")

        return Ok(preview)  # type: ignore[arg-type]

    except Exception as e:
        return Err(f"Dry-run failed: {e}")
