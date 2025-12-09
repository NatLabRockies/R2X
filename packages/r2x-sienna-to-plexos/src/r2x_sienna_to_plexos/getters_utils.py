"""Utility functions for getter operations, particularly multiband conversions.

This module provides utility functions for converting piecewise linear data
into PLEXOS multiband properties. These are used by getter functions to
transform Sienna cost curves into PLEXOS property values with band support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from infrasys.cost_curves import CostCurve, FuelCurve
from infrasys.function_data import LinearFunctionData, PiecewiseLinearData, QuadraticFunctionData, XYCoords
from infrasys.value_curves import AverageRateCurve, IncrementalCurve, InputOutputCurve
from loguru import logger
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSPropertyValue,
    PLEXOSRegion,
)
from r2x_sienna.models import (
    ACBus,
    Area,
    EnergyReservoirStorage,
    HydroDispatch,
    HydroEnergyReservoir,
    HydroPumpedStorage,
    RenewableDispatch,
    RenewableNonDispatch,
    SynchronousCondenser,
    ThermalMultiStart,
    ThermalStandard,
)
from r2x_sienna.units import get_magnitude  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from r2x_core import TranslationContext

InputOutputCurveValue = InputOutputCurve[LinearFunctionData | QuadraticFunctionData | PiecewiseLinearData]


def _ensure_membership(
    context: TranslationContext,
    parent_object: Any,
    child_object: Any,
    collection: CollectionEnum,
) -> None:
    """Create and add a membership between parent and child objects.

    Parameters
    ----------
    context : TranslationContext
        The translation context containing the target system
    parent_object : Any
        The parent object in the membership relationship
    child_object : Any
        The child object in the membership relationship
    collection : CollectionEnum
        The collection type for the membership
    """
    membership = PLEXOSMembership(
        parent_object=parent_object,
        child_object=child_object,
        collection=collection,
    )
    context.target_system.add_supplemental_attribute(parent_object, membership)


def ensure_region_node_memberships(context: TranslationContext) -> None:
    """Create Region->Node memberships for all regions and their nodes."""
    logger.info("Starting region-node membership creation...")

    regions = list(context.target_system.get_components(PLEXOSRegion))
    all_nodes = list(context.target_system.get_components(PLEXOSNode))
    all_buses = list(context.source_system.get_components(ACBus))

    node_to_area = {}
    for node in all_nodes:
        for bus in all_buses:
            if bus.name == node.name and hasattr(bus, "area") and bus.area is not None:
                area_name = bus.area.name if isinstance(bus.area, Area) else str(bus.area)
                node_to_area[node.name] = area_name
                break

    total_memberships = 0
    for region in regions:
        region_name = region.name
        nodes_in_region = [node for node in all_nodes if node_to_area.get(node.name) == region_name]
        for node in nodes_in_region:
            _ensure_membership(context, node, region, CollectionEnum.Region)
            total_memberships += 1

    logger.info(f"Total {total_memberships} Region-Node memberships created.")


def ensure_generator_node_memberships(context: TranslationContext) -> None:
    """Ensure every translated generator has a node membership based on its source bus."""
    logger.info("Starting generator-node membership creation...")

    sienna_generator_types = [
        HydroDispatch,
        ThermalStandard,
        ThermalMultiStart,
        RenewableDispatch,
        RenewableNonDispatch,
        HydroEnergyReservoir,
        HydroPumpedStorage,
        SynchronousCondenser,
    ]

    source_generators: dict[str, Any] = {}
    for gen_type in sienna_generator_types:
        gen: Any
        for gen in context.source_system.get_components(gen_type):  # type: ignore[arg-type]
            source_generators[gen.name] = gen

    target_generators = {gen.name: gen for gen in context.target_system.get_components(PLEXOSGenerator)}
    nodes_by_name = {node.name: node for node in context.target_system.get_components(PLEXOSNode)}

    total_memberships = 0
    for name, source_gen in source_generators.items():
        target_gen = target_generators.get(name)
        if target_gen is None:
            continue

        bus = getattr(source_gen, "bus", None)
        if bus is None:
            continue

        node = nodes_by_name.get(bus.name)
        if node is not None:
            _ensure_membership(context, target_gen, node, CollectionEnum.Nodes)
            total_memberships += 1

    logger.info(f"Total {total_memberships} Generator-Node memberships created.")


def ensure_battery_node_memberships(context: TranslationContext) -> None:
    """Ensure every translated battery has a node membership based on its source bus."""
    logger.info("Starting battery-node membership creation...")

    source_batteries: dict[str, Any] = {}
    for battery in context.source_system.get_components(EnergyReservoirStorage):
        source_batteries[battery.name] = battery

    target_batteries = {bat.name: bat for bat in context.target_system.get_components(PLEXOSBattery)}
    nodes_by_name = {node.name: node for node in context.target_system.get_components(PLEXOSNode)}

    total_memberships = 0
    for name, source_battery in source_batteries.items():
        target_battery = target_batteries.get(name)
        if target_battery is None:
            continue

        bus = getattr(source_battery, "bus", None)
        if bus is None:
            continue

        node = nodes_by_name.get(bus.name)
        if node is not None:
            _ensure_membership(context, target_battery, node, CollectionEnum.Nodes)
            total_memberships += 1

    logger.info(f"Total {total_memberships} Battery-Node memberships created.")


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
