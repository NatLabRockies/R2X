"""System modifiers for r2x translations."""

from typing import Any

from r2x_core import PluginManager, System

from .common.config import PLEXOSToSiennaConfig
from .translations import plexos_to_sienna


@PluginManager.register_system_modifier(  # type: ignore
    "plexos_to_sienna",
    config=PLEXOSToSiennaConfig,
)
def plexos_to_sienna_modifier(system: System, **kwargs: Any) -> System:
    """Convert PLEXOS system to Sienna format.

    Parameters
    ----------
    system : System
        PLEXOS system to convert
    config : PLEXOSToSiennaConfig, optional
        Translation configuration (can be passed via kwargs)
    **kwargs
        Config fields passed as individual kwargs

    Returns
    -------
    System
        Sienna system

    Raises
    ------
    RuntimeError
        If translation fails

    Examples
    --------
    Via PluginManager:

    >>> from r2x_core import PluginManager
    >>> pm = PluginManager()
    >>> modifier = pm.registered_modifiers["plexos_to_sienna"]
    >>> sienna_system = modifier(plexos_system, system_base_power=200.0)

    Via CLI (auto-generated):

    $ plexos_to_sienna -i input.json -o output.json --system-base-power 200.0
    """
    # Extract or build config
    config = kwargs.pop("config", None)
    if config is None:
        config = PLEXOSToSiennaConfig(**kwargs)

    # Call translation function
    result = plexos_to_sienna.translate_system(system, config)

    # Unwrap Result or raise
    if result.is_err():
        raise RuntimeError(f"Translation failed: {result.err()}")

    return result.unwrap()


@PluginManager.register_system_modifier("validate_plexos")  # type: ignore
def validate_plexos_modifier(system: System, **kwargs: Any) -> System:
    """Validate PLEXOS system before translation.

    Parameters
    ----------
    system : System
        PLEXOS system to validate
    **kwargs
        Validation options

    Returns
    -------
    System
        Same system (unchanged)

    Raises
    ------
    RuntimeError
        If validation has errors

    Examples
    --------
    $ validate_plexos -i input.json
    """
    result = plexos_to_sienna.validate_input(system, **kwargs)

    if result.is_err():
        raise RuntimeError(f"Validation failed: {result.err()}")

    report = result.unwrap()
    if report.has_errors:
        raise RuntimeError(f"Validation errors found:\n{report.summary()}")

    # Return unchanged
    return system
