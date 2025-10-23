"""Validation for PLEXOS to Sienna translation."""

from pathlib import Path
from typing import Any

from loguru import logger
from r2x_plexos.models import PLEXOSBattery, PLEXOSGenerator

from r2x._core import ValidationReport, find_closest_match, format_mapping_error, format_validation_error
from r2x_core import Err, Ok, Result, System

from .registry import get_registry
from .utils import get_plexos_property


def validate_input(input_path: str | Path | System, **options: Any) -> Result[ValidationReport, str]:
    """Validate PLEXOS system before translation to Sienna.

    Parameters
    ----------
    input_path : str | Path | System
        PLEXOS system file path or System object
    **options
        Validation options

    Returns
    -------
    Result[ValidationReport, str]
        Ok with validation report or Err with error message

    Examples
    --------
    >>> result = validate_input("plexos_system.json")
    >>> if result.is_ok():
    ...     report = result.unwrap()
    ...     if report.has_errors:
    ...         print(report.summary())
    """
    try:
        if isinstance(input_path, System):
            plexos_system = input_path
        else:
            plexos_system = System.from_json(input_path, auto_add_composed_components=True)

        report = ValidationReport()
        registry = get_registry()

        _validate_generators(plexos_system, registry, report)
        _validate_batteries(plexos_system, report)
        _validate_system_basic(plexos_system, report)

        return Ok(report)

    except Exception as e:
        return Err(f"Validation failed: {e}")


def _validate_generators(plexos_system: System, registry: Any, report: ValidationReport) -> None:
    """Validate generator components."""
    generators = list(plexos_system.get_components(PLEXOSGenerator))

    if not generators:
        report.add_warning("No generators found in system")
        return

    unknown_categories = set()
    zero_capacity_generators = []

    for gen in generators:
        if not gen.category:
            error = format_validation_error(
                "Generator missing category",
                component_name=gen.name,
                component_type="PLEXOSGenerator",
                suggestion="Add category property to generator",
            )
            report.add_error(error)
            continue

        if registry.get(gen.category).is_err():
            unknown_categories.add(gen.category)

        capacity = get_plexos_property(plexos_system, gen, "max_capacity")
        rating_factor = get_plexos_property(plexos_system, gen, "rating_factor")

        if capacity * rating_factor == 0:
            zero_capacity_generators.append(gen.name)

    if unknown_categories:
        available = registry.list_keys()
        for category in unknown_categories:
            suggestion = find_closest_match(category, available)
            error = format_mapping_error(category, available, suggestion)
            report.add_error(error)

    if zero_capacity_generators:
        count = len(zero_capacity_generators)
        report.add_warning(
            f"{count} generator(s) have zero capacity and will be skipped: "
            f"{', '.join(zero_capacity_generators[:5])}" + (f" and {count - 5} more" if count > 5 else "")
        )


def _validate_batteries(plexos_system: System, report: ValidationReport) -> None:
    """Validate battery components."""
    batteries = list(plexos_system.get_components(PLEXOSBattery))

    zero_storage_batteries = []

    for battery in batteries:
        storage_capacity = get_plexos_property(plexos_system, battery, "capacity")

        if storage_capacity == 0:
            zero_storage_batteries.append(battery.name)

    if zero_storage_batteries:
        count = len(zero_storage_batteries)
        report.add_warning(
            f"{count} battery/batteries have zero storage capacity: "
            f"{', '.join(zero_storage_batteries[:5])}" + (f" and {count - 5} more" if count > 5 else "")
        )


def _validate_system_basic(plexos_system: System, report: ValidationReport) -> None:
    """Perform basic system-level validation."""
    if not plexos_system.name:
        report.add_warning("System has no name")

    component_count = sum(1 for _ in plexos_system.iter_all_components())
    if component_count == 0:
        report.add_error("System has no components")

    logger.debug(f"Validated system with {component_count} components")
