"""Validation utilities for power system translation."""

from r2x_core import System

from .reports import ValidationReport


def validate_system_basic(system: System) -> ValidationReport:
    """Perform basic validation checks on a power system.

    Parameters
    ----------
    system : System
        System to validate

    Returns
    -------
    ValidationReport
        Report with validation results

    Examples
    --------
    >>> report = validate_system_basic(system)
    >>> if report.has_errors:
    ...     print(report.summary())
    """
    report = ValidationReport()

    if system.name is None or system.name == "":
        report.add_warning("System has no name")

    component_count = sum(1 for _ in system.iter_all_components())
    if component_count == 0:
        report.add_error("System has no components")

    return report
