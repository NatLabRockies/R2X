"""Utility functions for getter operations, particularly multiband conversions.

This module provides utility functions for converting piecewise linear data
into PLEXOS multiband properties. These are used by getter functions to
transform Sienna cost curves into PLEXOS property values with band support.
"""

from __future__ import annotations

from typing import Any

from infrasys.cost_curves import CostCurve, FuelCurve
from infrasys.function_data import LinearFunctionData, PiecewiseLinearData, QuadraticFunctionData, XYCoords
from infrasys.value_curves import AverageRateCurve, IncrementalCurve, InputOutputCurve
from r2x_plexos.models import PLEXOSPropertyValue
from r2x_sienna.units import get_magnitude

InputOutputCurveValue = InputOutputCurve[LinearFunctionData | QuadraticFunctionData | PiecewiseLinearData]


def normalize_value_curve(curve: Any) -> InputOutputCurveValue | None:
    """Normalize value curve to InputOutputCurve format.

    Converts IncrementalCurve and AverageRateCurve to InputOutputCurve.
    Returns None if conversion fails or curve is not a compatible type.

    Parameters
    ----------
    curve : Any
        A value curve object to normalize

    Returns
    -------
    InputOutputCurve | None
        Normalized curve, or None if normalization fails
    """
    if isinstance(curve, InputOutputCurve):
        return curve
    if isinstance(curve, IncrementalCurve | AverageRateCurve):
        try:
            return curve.to_input_output()
        except Exception:
            return None
    return None


def extract_piecewise_segments(points: list[XYCoords]) -> tuple[list[float], list[float]]:
    """Extract load points and slopes from piecewise linear points.

    Converts a list of XYCoords points into load points (x-coordinates) and
    slopes (y-differences divided by x-differences).

    Parameters
    ----------
    points : list[XYCoords]
        List of XYCoords points defining segments of a piecewise linear curve

    Returns
    -------
    tuple[list[float], list[float]]
        Tuple of (load_points, slopes) where:
        - load_points: x-coordinates where slope changes
        - slopes: incremental slopes for each segment
    """
    load_points: list[float] = []
    slopes: list[float] = []

    if not points:
        return load_points, slopes

    previous = points[0]
    for current in points[1:]:
        dx = current.x - previous.x
        if dx <= 0:
            previous = current
            continue
        slope = (current.y - previous.y) / dx
        slopes.append(float(slope))
        load_points.append(float(current.x))
        previous = current

    return load_points, slopes


def resolve_base_power(component: Any) -> float:
    """Resolve base power from component.

    Attempts to extract base power from component's base_power or _system_base
    attributes. Returns 1.0 if neither is available.

    Parameters
    ----------
    component : Any
        Component object with potential base_power or _system_base attribute

    Returns
    -------
    float
        Base power value, defaults to 1.0
    """
    base = get_magnitude(getattr(component, "base_power", None))
    if base is None:
        base = get_magnitude(getattr(component, "_system_base", None))
    if base is None:
        base = 1.0
    return float(base)


def compute_heat_rate_data(component: Any) -> dict[str, Any]:
    """Compute heat rate data from component operation cost.

    Extracts heat rate information from a component's operation cost and
    converts it to a dictionary with heat_rate, heat_rate_base, load_point,
    and heat_rate_incr keys depending on the cost curve type.

    Parameters
    ----------
    component : Any
        Component with operation_cost attribute

    Returns
    -------
    dict[str, Any]
        Dictionary with heat rate data, may contain:
        - heat_rate: Linear heat rate
        - heat_rate_base: Constant term for quadratic curve
        - heat_rate_incr: Quadratic coefficient or multiband values
        - load_point: Load points for multiband curves
    """
    cost = getattr(component, "operation_cost", None)
    variable = getattr(cost, "variable", None) if cost else None

    if not isinstance(variable, FuelCurve):
        return {}

    curve = normalize_value_curve(variable.value_curve)
    if curve is None or curve.function_data is None:
        return {}

    data: dict[str, Any] = {}
    fd = curve.function_data

    if isinstance(fd, LinearFunctionData):
        data["heat_rate"] = float(fd.proportional_term)
        data["heat_rate_base"] = float(fd.constant_term)
        return data

    if isinstance(fd, QuadraticFunctionData):
        data["heat_rate_base"] = float(fd.constant_term)
        data["heat_rate"] = float(fd.proportional_term)
        data["heat_rate_incr"] = float(fd.quadratic_term)
        return data

    if isinstance(fd, PiecewiseLinearData):
        load_points, slopes = extract_piecewise_segments(fd.points)
        if load_points and slopes:
            load_prop, heat_prop = create_multiband_heat_rate(load_points, slopes)
            data["load_point"] = load_prop
            data["heat_rate_incr"] = heat_prop
        return data

    return {}


def compute_markup_data(component: Any) -> dict[str, Any]:
    """Compute markup data from component operation cost.

    Extracts markup/VOM cost information from a component's operation cost and
    converts it to a dictionary with mark_up, mark_up_point keys depending on
    the cost curve type.

    Parameters
    ----------
    component : Any
        Component with operation_cost attribute

    Returns
    -------
    dict[str, Any]
        Dictionary with markup data, may contain:
        - mark_up: Linear markup value or multiband markup values
        - mark_up_point: Load points for multiband markup curves
    """
    cost = getattr(component, "operation_cost", None)
    variable = getattr(cost, "variable", None) if cost else None

    if not isinstance(variable, CostCurve):
        return {}

    curve = normalize_value_curve(variable.vom_cost)
    if curve is None or curve.function_data is None:
        return {}

    data: dict[str, Any] = {}
    fd = curve.function_data

    if isinstance(fd, LinearFunctionData):
        data["mark_up"] = float(fd.proportional_term)
        return data

    if isinstance(fd, QuadraticFunctionData):
        data["mark_up"] = float(fd.proportional_term)
        return data

    if isinstance(fd, PiecewiseLinearData):
        load_points, slopes = extract_piecewise_segments(fd.points)
        if load_points and slopes:
            point_prop, mark_prop = create_multiband_markup(load_points, slopes)
            data["mark_up_point"] = point_prop
            data["mark_up"] = mark_prop
        return data

    return {}


def coerce_value(value: Any, default: float = 0.0) -> Any:
    """Coerce value to appropriate type.

    Returns the value as-is if it's a PLEXOSPropertyValue, otherwise converts
    to float or returns the default.

    Parameters
    ----------
    value : Any
        Value to coerce
    default : float, optional
        Default value if value is None, by default 0.0

    Returns
    -------
    Any
        Coerced value
    """
    if value is None:
        return default
    if isinstance(value, PLEXOSPropertyValue):
        return value
    return float(value)


def create_multiband_heat_rate(
    load_points: list[float],
    slopes: list[float],
) -> tuple[PLEXOSPropertyValue, PLEXOSPropertyValue]:
    """Create multiband heat rate properties from piecewise linear segments.

    Converts piecewise linear fuel curve data into PLEXOS multiband format.
    Each segment becomes a band with its corresponding load point and heat rate slope.

    Parameters
    ----------
    load_points : list[float]
        List of load points (x-coordinates) where slope changes occur.
        Expected to be in ascending order and represent the upper limit of each band.
    slopes : list[float]
        List of slope values (incremental heat rates) for each band.
        Length should equal length of load_points.

    Returns
    -------
    tuple[PLEXOSPropertyValue, PLEXOSPropertyValue]
        A tuple of (load_point_property, heat_rate_property) where:
        - load_point_property: PLEXOSPropertyValue with band-indexed load points
        - heat_rate_property: PLEXOSPropertyValue with band-indexed heat rate slopes

    Examples
    --------
    For a piecewise linear fuel curve with 2 segments:
    - Segment 1: 0-60 MW at 12 MBTU/MWh
    - Segment 2: 60-120 MW at 13 MBTU/MWh

    >>> load_pts = [60.0, 120.0]
    >>> rates = [12.0, 13.0]
    >>> load_prop, heat_prop = create_multiband_heat_rate(load_pts, rates)
    >>> load_prop.get_bands()
    [1, 2]
    >>> heat_prop.get_bands()
    [1, 2]
    """
    load_point_property = PLEXOSPropertyValue()
    heat_rate_property = PLEXOSPropertyValue()

    for band_num, (load_point, slope) in enumerate(zip(load_points, slopes, strict=False), start=1):
        load_point_property.add_entry(value=float(load_point), band=band_num)
        heat_rate_property.add_entry(value=float(slope), band=band_num)

    return load_point_property, heat_rate_property


def create_multiband_markup(
    load_points: list[float],
    slopes: list[float],
) -> tuple[PLEXOSPropertyValue, PLEXOSPropertyValue]:
    """Create multiband markup properties from piecewise linear segments.

    Converts piecewise linear VOM cost curve data into PLEXOS multiband format.
    Each segment becomes a band with its corresponding load point and markup value.

    Parameters
    ----------
    load_points : list[float]
        List of load points (x-coordinates) where cost slope changes occur.
        Expected to be in ascending order and represent the upper limit of each band.
    slopes : list[float]
        List of slope values (incremental VOM costs) for each band.
        Length should equal length of load_points.

    Returns
    -------
    tuple[PLEXOSPropertyValue, PLEXOSPropertyValue]
        A tuple of (markup_point_property, markup_property) where:
        - markup_point_property: PLEXOSPropertyValue with band-indexed load points
        - markup_property: PLEXOSPropertyValue with band-indexed markup values

    Examples
    --------
    For a piecewise linear VOM cost curve with 2 segments:
    - Segment 1: 0-40 MW at $13/MWh
    - Segment 2: 40-80 MW at $16/MWh

    >>> load_pts = [40.0, 80.0]
    >>> costs = [13.0, 16.0]
    >>> point_prop, markup_prop = create_multiband_markup(load_pts, costs)
    >>> point_prop.get_bands()
    [1, 2]
    >>> markup_prop.get_bands()
    [1, 2]
    """
    markup_point_property = PLEXOSPropertyValue()
    markup_property = PLEXOSPropertyValue()

    for band_num, (load_point, slope) in enumerate(zip(load_points, slopes, strict=False), start=1):
        markup_point_property.add_entry(value=float(load_point), band=band_num)
        markup_property.add_entry(value=float(slope), band=band_num)

    return markup_point_property, markup_property
