"""Dry-run utilities for previewing translations."""

from .reports import DryRunReport


def create_empty_preview() -> DryRunReport:
    """Create an empty dry-run preview report.

    Returns
    -------
    DryRunReport
        Empty preview report

    Examples
    --------
    >>> preview = create_empty_preview()
    >>> preview.add_conversion("PLEXOSGenerator", "ThermalStandard", 10)
    >>> print(preview.summary())
    """
    return DryRunReport()
