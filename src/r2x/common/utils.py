"""Common utility functions for all translations."""

from typing import Any

from r2x_core import System


def get_component_property(
    system: System,
    component: Any,
    property_name: str,
    use_max_from_timeseries: bool = True,
) -> float:
    """Get property value from component, optionally checking time series.

    Generic utility that works for any component type.

    Parameters
    ----------
    system : System
        System containing the component
    component : Any
        Component with the property
    property_name : str
        Name of the property
    use_max_from_timeseries : bool
        If True and time series exists, return max value from time series

    Returns
    -------
    float
        Property value
    """
    # Check for time series first
    if use_max_from_timeseries and system.has_time_series(component, property_name):
        ts = system.get_time_series(component, property_name)
        return float(max(ts.data))

    # Get scalar value
    value = getattr(component, property_name, None)
    if value is None:
        return 0.0

    return float(value)


def create_unit_value(value: float, unit: str) -> dict[str, Any]:
    """Create Sienna-compatible unit value dictionary.

    Sienna components accept values as {"value": X, "unit": "MW"}
    and automatically convert to per-device units.

    Parameters
    ----------
    value : float
        Numeric value
    unit : str
        Unit string (e.g., "MW", "kV", "MWh")

    Returns
    -------
    dict[str, Any]
        Dictionary with value and unit

    Examples
    --------
    >>> create_unit_value(100.0, "MW")
    {"value": 100.0, "unit": "MW"}
    """
    return {"value": value, "unit": unit}


def get_object_id(component: Any) -> int | None:
    """Extract object_id from component.

    Checks both direct attribute and ext dict.

    Parameters
    ----------
    component : Any
        Component to extract ID from

    Returns
    -------
    int | None
        Object ID or None
    """
    # Direct attribute
    if hasattr(component, "object_id") and component.object_id is not None:
        object_id: int = component.object_id
        return object_id

    # Check ext dict
    if hasattr(component, "ext") and isinstance(component.ext, dict):
        ext_id = component.ext.get("object_id")
        return int(ext_id) if ext_id is not None else None

    return None
