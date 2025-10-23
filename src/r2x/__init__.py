"""R2X - Multi-system translations for power systems modeling."""

from importlib.metadata import version
from pathlib import Path
from typing import Any

from r2x_core import Err, Ok, Result, System

__version__ = version("r2x")

from . import modifiers  # Auto-register system modifiers
from ._core import DryRunReport, ValidationReport
from .common import PLEXOSToSiennaConfig
from .translations import plexos_to_sienna

_TRANSLATORS = {
    ("plexos", "sienna"): plexos_to_sienna.translate_system,
}

_VALIDATORS = {
    "plexos": plexos_to_sienna.validate_input,
}

_DRY_RUNNERS = {
    ("plexos", "sienna"): plexos_to_sienna.dry_run,
}


def translate(
    input: str | Path | System | bytes | None,
    from_format: str,
    to_format: str,
    output: str | Path | None = None,
    **options: Any,
) -> Result[System, str]:
    """Translate between power system formats.

    Parameters
    ----------
    input : str | Path | System | bytes | None
        Input source. Can be:
        - File path (str or Path)
        - System object (already loaded)
        - Bytes (JSON data)
        - None (read from stdin)
    from_format : str
        Source format (e.g., "plexos")
    to_format : str
        Target format (e.g., "sienna")
    output : str | Path | None
        Optional output destination. If provided, writes result to file.
    **options : Any
        Translation-specific configuration options

    Returns
    -------
    Result[System, str]
        Ok with translated system or Err with error message.
        System is returned even if written to output file.

    Examples
    --------
    >>> # Simple file translation
    >>> result = translate("input.json", "plexos", "sienna")
    >>> if result.is_ok():
    ...     system = result.unwrap()

    >>> # With configuration
    >>> result = translate(
    ...     "input.json",
    ...     "plexos",
    ...     "sienna",
    ...     system_base_power=100.0,
    ...     mappings_file="custom.yaml"
    ... )

    >>> # Write to file and get result
    >>> result = translate("input.json", "plexos", "sienna", output="out.json")

    >>> # Quick script with .expect()
    >>> system = translate("input.json", "plexos", "sienna").expect("Translation failed")
    """
    from . import io as r2x_io

    key = (from_format.lower(), to_format.lower())
    if key not in _TRANSLATORS:
        available = ", ".join(f"{f}→{t}" for f, t in _TRANSLATORS)
        return Err(f"No translator for {from_format} → {to_format}. Available: {available}")

    if input is None:
        system_result = r2x_io.from_stdin()
    elif isinstance(input, System):
        system_result = Ok(input)
    elif isinstance(input, bytes):
        system_result = r2x_io.from_bytes(input)
    elif isinstance(input, str | Path):
        system_result = r2x_io.from_file(input)
    else:
        return Err(f"Unsupported input type: {type(input)}")

    if system_result.is_err():
        return system_result

    system = system_result.unwrap()

    translator_fn = _TRANSLATORS[key]
    result = translator_fn(system, **options)

    if result.is_err():
        return result

    translated_system = result.unwrap()

    if output is not None:
        write_result = r2x_io.to_file(translated_system, output)
        if write_result.is_err():
            return Err(f"Translation succeeded but write failed: {write_result.err()}")

    return Ok(translated_system)


def validate(
    input: str | Path | System,
    format: str,
    **options: Any,
) -> Result[ValidationReport, str]:
    """Validate power system before translation.

    Parameters
    ----------
    input : str | Path | System
        Input source (file path or System object)
    format : str
        System format (e.g., "plexos")
    **options : Any
        Validation options

    Returns
    -------
    Result[ValidationReport, str]
        Ok with validation report or Err with error message

    Examples
    --------
    >>> result = validate("input.json", "plexos")
    >>> if result.is_ok():
    ...     report = result.unwrap()
    ...     if report.has_errors:
    ...         print(report.summary())
    """
    format_key = format.lower()
    if format_key not in _VALIDATORS:
        available = ", ".join(_VALIDATORS.keys())
        return Err(f"No validator for format '{format}'. Available: {available}")

    validator_fn = _VALIDATORS[format_key]
    return validator_fn(input, **options)


def dry_run(
    input: str | Path | System,
    from_format: str,
    to_format: str,
    **options: Any,
) -> Result[DryRunReport, str]:
    """Preview translation without executing it.

    Parameters
    ----------
    input : str | Path | System
        Input source (file path or System object)
    from_format : str
        Source format (e.g., "plexos")
    to_format : str
        Target format (e.g., "sienna")
    **options : Any
        Translation configuration

    Returns
    -------
    Result[DryRunReport, str]
        Ok with preview report or Err with error message

    Examples
    --------
    >>> result = dry_run("input.json", "plexos", "sienna")
    >>> if result.is_ok():
    ...     preview = result.unwrap()
    ...     print(preview.summary())
    """
    key = (from_format.lower(), to_format.lower())
    if key not in _DRY_RUNNERS:
        available = ", ".join(f"{f}→{t}" for f, t in _DRY_RUNNERS)
        return Err(f"No dry-run support for {from_format} → {to_format}. Available: {available}")

    dry_run_fn = _DRY_RUNNERS[key]
    return dry_run_fn(input, **options)  # type: ignore[return-value]


__all__ = [
    "DryRunReport",
    "PLEXOSToSiennaConfig",
    "ValidationReport",
    "__version__",
    "dry_run",
    "modifiers",
    "translate",
    "validate",
]
