"""Base protocol for translation modules."""

from pathlib import Path
from typing import Any, Protocol

from r2x_core import Result, System

from .reports import DryRunReport, ValidationReport


class TranslatorProtocol(Protocol):
    """Protocol that all translator modules should follow.

    This defines the interface that translation modules (e.g., plexos_to_sienna)
    should implement for consistency.

    Examples
    --------
    >>> class MyTranslator:
    ...     def translate_system(self, system, **options):
    ...         # Translation logic
    ...         return Ok(translated_system)
    ...
    ...     def validate_input(self, system, **options):
    ...         report = ValidationReport()
    ...         # Validation logic
    ...         return Ok(report)
    ...
    ...     def dry_run(self, system, **options):
    ...         report = DryRunReport()
    ...         # Preview logic
    ...         return Ok(report)
    """

    def translate_system(
        self,
        input_path: str | Path | System,
        **options: Any,
    ) -> Result[System, str]:
        """Translate system from input format to output format.

        Parameters
        ----------
        input_path : str | Path | System
            Input source (file path or System object)
        **options : Any
            Translation-specific configuration

        Returns
        -------
        Result[System, str]
            Ok with translated system or Err with error message
        """
        ...

    def validate_input(
        self,
        input_path: str | Path | System,
        **options: Any,
    ) -> Result[ValidationReport, str]:
        """Validate input before translation.

        Parameters
        ----------
        input_path : str | Path | System
            Input source to validate
        **options : Any
            Validation configuration

        Returns
        -------
        Result[ValidationReport, str]
            Ok with validation report or Err with error message
        """
        ...

    def dry_run(
        self,
        input_path: str | Path | System,
        **options: Any,
    ) -> Result[DryRunReport, str]:
        """Preview what translation would produce without executing.

        Parameters
        ----------
        input_path : str | Path | System
            Input source to preview
        **options : Any
            Translation configuration

        Returns
        -------
        Result[DryRunReport, str]
            Ok with preview report or Err with error message
        """
        ...
