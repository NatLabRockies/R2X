"""Common time series utilities for all translations."""

from infrasys import Component
from loguru import logger

from r2x_core import System


def copy_time_series(
    source_component: Component,
    target_component: Component,
    source_system: System,
    target_system: System,
    name_mapping: dict[str, str] | None = None,
) -> None:
    """Copy time series from source to target component.

    This is a generic utility that works for any component types.

    Parameters
    ----------
    source_component : Component
        Source component with time series
    target_component : Component
        Target component to attach time series
    source_system : System
        Source system containing the time series
    target_system : System
        Target system to add time series to
    name_mapping : dict[str, str] | None
        Optional mapping of source names to target names.
        If provided, only mapped time series will be copied.
        If None, all time series are copied with original names.

    Examples
    --------
    >>> # Copy all time series with original names
    >>> copy_time_series(plexos_gen, sienna_gen, plexos_sys, sienna_sys)

    >>> # Copy with name mapping
    >>> copy_time_series(
    ...     plexos_gen, sienna_gen, plexos_sys, sienna_sys,
    ...     name_mapping={"max_capacity": "max_active_power"}
    ... )
    """
    if not source_system.has_time_series(source_component):
        logger.trace("No time series found for {}", source_component.label)
        return

    # List all time series on source component
    time_series_list = source_system.list_time_series(source_component)

    copied_count = 0
    for ts in time_series_list:
        if name_mapping is not None:
            if ts.name not in name_mapping:
                logger.trace(
                    "Skipping time series '{}' (not in name_mapping)",
                    ts.name,
                )
                continue
            target_name = name_mapping[ts.name]
        else:
            target_name = ts.name

        # Create copy with new name
        ts_copy = type(ts).model_validate(ts.model_dump(round_trip=True))
        ts_copy.name = target_name

        target_system.add_time_series(ts_copy, target_component)
        copied_count += 1

        logger.trace(
            "Copied time series '{}' → '{}' for {}",
            ts.name,
            target_name,
            target_component.label,
        )

    if copied_count > 0:
        logger.debug(
            "Copied {} time series from {} to {}",
            copied_count,
            source_component.label,
            target_component.label,
        )


def has_time_series_data(component: Component, system: System) -> bool:
    """Check if component has any time series data.

    Parameters
    ----------
    component : Component
        Component to check
    system : System
        System containing the component

    Returns
    -------
    bool
        True if component has time series
    """
    return system.has_time_series(component)


def list_time_series_names(component: Component, system: System) -> list[str]:
    """Get list of all time series names for a component.

    Parameters
    ----------
    component : Component
        Component to check
    system : System
        System containing the component

    Returns
    -------
    list[str]
        List of time series names
    """
    if not system.has_time_series(component):
        return []

    time_series_list = system.list_time_series(component)
    return [ts.name for ts in time_series_list]
