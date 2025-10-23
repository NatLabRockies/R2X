"""PLEXOS to Sienna specific utilities."""

from functools import singledispatch
from typing import Any

from infrasys.cost_curves import CostCurve, FuelCurve, UnitSystem
from infrasys.function_data import LinearFunctionData, PiecewiseStepData
from infrasys.value_curves import IncrementalCurve, LinearCurve
from loguru import logger
from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSObject
from r2x_plexos.models.battery import PLEXOSBattery
from r2x_plexos.models.generator import PLEXOSGenerator
from r2x_sienna.models import (
    EnergyReservoirStorage,
    HydroDispatch,
    RenewableDispatch,
    RenewableNonDispatch,
    ThermalStandard,
)
from r2x_sienna.models.base import SiennaComponent
from r2x_sienna.models.costs import (
    HydroGenerationCost,
    RenewableGenerationCost,
    StorageCost,
    ThermalGenerationCost,
)
from r2x_sienna.models.named_tuples import MinMax

from r2x.common.config import PLEXOSToSiennaConfig
from r2x.common.utils import create_unit_value, get_component_property
from r2x_core import System


def configure_plexos_context(config: PLEXOSToSiennaConfig) -> None:
    """Configure PLEXOS context resolution.

    Sets scenario priority and horizon for property value resolution.

    Parameters
    ----------
    config : PLEXOSToSiennaConfig
        Translation configuration
    """
    # Scenario and horizon configuration removed - use PLEXOS context defaults


def get_plexos_property(
    system: System,
    component: PLEXOSObject,
    property_name: str,
) -> float:
    """Get PLEXOS property value.

    Uses PLEXOS context resolution (scenario/horizon priority) automatically.
    The PLEXOSObject.__getattribute__ handles this via PLEXOSPropertyValue.get_value()

    Parameters
    ----------
    system : System
        PLEXOS system
    component : PLEXOSObject
        PLEXOS component
    property_name : str
        Property name

    Returns
    -------
    float
        Property value (resolved via context) or max from time series
    """
    return get_component_property(system, component, property_name, use_max_from_timeseries=True)


def get_plexos_property_with_unit(
    system: System,
    component: PLEXOSObject,
    property_name: str,
    unit: str,
) -> dict[str, Any]:
    """Get PLEXOS property value with unit for Sienna.

    Returns value in Sienna-compatible format for automatic per-unit conversion.

    Parameters
    ----------
    system : System
        PLEXOS system
    component : PLEXOSObject
        PLEXOS component
    property_name : str
        Property name
    unit : str
        Unit string (e.g., "MW", "kV")

    Returns
    -------
    dict[str, Any]
        {"value": X, "unit": "MW"} format for Sienna

    Examples
    --------
    >>> get_plexos_property_with_unit(sys, gen, "max_capacity", "MW")
    {"value": 100.0, "unit": "MW"}
    """
    value = get_plexos_property(system, component, property_name)
    return create_unit_value(value, unit)


def get_connected_node(
    system: System,
    component: PLEXOSObject,
) -> PLEXOSNode | None:
    """Find node connected to PLEXOS device.

    Parameters
    ----------
    system : System
        PLEXOS system
    component : PLEXOSObject
        PLEXOS device

    Returns
    -------
    PLEXOSNode | None
        Connected node or None
    """
    # Get PLEXOSMembership supplemental attributes attached to this component
    memberships = list(
        system.get_supplemental_attributes(
            PLEXOSMembership,
            filter_func=lambda comp: comp.parent_object == component
            and isinstance(comp.child_object, PLEXOSNode),
        )
    )

    if not memberships:
        logger.warning("Could not find node connected to {}", component.label)
        return None

    if len(memberships) > 1:
        logger.warning("Multiple nodes connected to the same generator", component.label)
        return None

    # The membership's parent_object should be the node that contains this component
    membership = memberships[0]
    if isinstance(membership.child_object, PLEXOSNode):
        return membership.child_object

    logger.warning("Could not find node connected to {}", component.label)
    return None


def create_sienna_minmax(
    min_value: float,
    max_value: float,
    unit: str = "MW",
) -> MinMax:
    """Create MinMax with unit values for Sienna.

    Sienna will automatically convert to per-device units.

    Parameters
    ----------
    min_value : float
        Minimum value
    max_value : float
        Maximum value
    unit : str
        Unit string

    Returns
    -------
    MinMax
        MinMax with float values
    """
    return MinMax(
        min=min_value,
        max=max_value,
    )


def extract_bands(
    property_value: Any,
    scenario: str | None = None,
    timeslice: str | None = None,
) -> dict[int, float]:
    """Extract band values from a PLEXOSPropertyValue for the given scenario and timeslice.

    Parameters
    ----------
    property_value : PLEXOSPropertyValue
        The property containing band values (can also be a dict if auto-resolved)
    scenario : str, optional
        The scenario to filter by
    timeslice : str, optional
        The timeslice to filter by

    Returns
    -------
    dict[int, float]
        Dictionary mapping band numbers to values
    """
    # Handle auto-resolved dict (from PLEXOSObject.__getattribute__)
    if isinstance(property_value, dict):
        return {int(k): float(v) for k, v in property_value.items()}

    if not hasattr(property_value, "entries") or not hasattr(property_value, "get_bands"):
        # Not a PLEXOSPropertyValue, return empty
        return {}

    band_values = {}

    # Get all bands in this property
    bands = property_value.get_bands()

    for band in bands:
        # Get value for this specific band/scenario/timeslice combination
        value = property_value.get_value_for(
            scenario=scenario,
            band=band,
            timeslice=timeslice,
        )
        if value is not None:
            band_values[band] = float(value)

    return band_values


def create_flat_cost_curve(cost: float) -> CostCurve:
    """Create a flat cost curve with constant cost.

    Parameters
    ----------
    cost : float
        The constant cost value

    Returns
    -------
    CostCurve
        The flat cost curve
    """
    return CostCurve(
        power_units=UnitSystem.NATURAL_UNITS,
        value_curve=IncrementalCurve(
            function_data=LinearFunctionData(constant_term=cost, proportional_term=0.0),
            initial_input=0.0,
        ),
    )


def create_curve_from_markup_points(
    markup_bands: dict[int, float],
    markup_points: dict[int, float],
    base_cost: float,
    max_capacity: float,
) -> CostCurve:
    """Create cost curve using markup points to define breakpoints.

    Parameters
    ----------
    markup_bands : dict[int, float]
        The markup values by band
    markup_points : dict[int, float]
        The points at which markups apply
    base_cost : float
        The base cost value
    max_capacity : float
        The maximum capacity

    Returns
    -------
    CostCurve
        The cost curve with breakpoints
    """
    breakpoints = []

    # Create breakpoints from markup points and bands
    for band in sorted(markup_bands.keys()):
        if band in markup_points:
            point = markup_points[band]
            if point <= max_capacity:
                markup = markup_bands[band]
                breakpoints.append((point, base_cost + markup))

    # Sort breakpoints by x-value
    breakpoints.sort(key=lambda x: x[0])

    # Handle edge cases
    if not breakpoints:
        return create_flat_cost_curve(base_cost)

    if len({bp[0] for bp in breakpoints}) <= 1:
        # All breakpoints have the same x value
        return create_flat_cost_curve(base_cost + breakpoints[0][1])

    # Remove duplicate x values
    unique_breakpoints = []
    seen_x = set()
    for x, y in breakpoints:
        if x not in seen_x:
            unique_breakpoints.append((x, y))
            seen_x.add(x)

    # Create piecewise step data
    # x_coords defines the breakpoints: [0, 40, 70, 100]
    # y_coords defines the cost in each segment: [cost for 0-40, cost for 40-70, cost for 70-100]
    x_coords = [0.0] + [bp[0] for bp in unique_breakpoints]
    y_coords = [bp[1] for bp in unique_breakpoints]

    # Validate lengths: y_coords should have length = len(x_coords) - 1
    if len(y_coords) != len(x_coords) - 1:
        return create_flat_cost_curve(base_cost)

    return CostCurve(
        power_units=UnitSystem.NATURAL_UNITS,
        value_curve=IncrementalCurve(
            function_data=PiecewiseStepData(x_coords=x_coords, y_coords=y_coords),
            initial_input=0.0,
        ),
    )


def create_curve_from_load_points(
    markup_bands: dict[int, float],
    load_points: dict[int, float],
    base_cost: float,
    max_capacity: float,
) -> CostCurve:
    """Create cost curve matching markup bands to load points.

    Parameters
    ----------
    markup_bands : dict[int, float]
        The markup values by band
    load_points : dict[int, float]
        The load points defining capacity breakpoints
    base_cost : float
        The base cost value
    max_capacity : float
        The maximum capacity

    Returns
    -------
    CostCurve
        The cost curve with breakpoints
    """
    breakpoints = []

    # Match markup bands to load points
    for band in sorted(markup_bands.keys()):
        if band in load_points:
            point = load_points[band]
            if point <= max_capacity:
                markup = markup_bands[band]
                breakpoints.append((point, base_cost + markup))

    # Sort breakpoints by x-value
    breakpoints.sort(key=lambda x: x[0])

    # Handle edge cases
    if not breakpoints:
        return create_flat_cost_curve(base_cost)

    if len({bp[0] for bp in breakpoints}) <= 1:
        # All breakpoints have the same x value
        return create_flat_cost_curve(base_cost + breakpoints[0][1])

    # Remove duplicate x values
    unique_breakpoints = []
    seen_x = set()
    for x, y in breakpoints:
        if x not in seen_x:
            unique_breakpoints.append((x, y))
            seen_x.add(x)

    # Create piecewise step data
    # x_coords defines the breakpoints: [0, 40, 70, 100]
    # y_coords defines the cost in each segment
    x_coords = [0.0] + [bp[0] for bp in unique_breakpoints]
    y_coords = [bp[1] for bp in unique_breakpoints]

    # Validate lengths: y_coords should have length = len(x_coords) - 1
    if len(y_coords) != len(x_coords) - 1:
        return create_flat_cost_curve(base_cost)

    return CostCurve(
        power_units=UnitSystem.NATURAL_UNITS,
        value_curve=IncrementalCurve(
            function_data=PiecewiseStepData(x_coords=x_coords, y_coords=y_coords),
            initial_input=0.0,
        ),
    )


def create_curve_from_heat_rate_bands(
    heat_rate_bands: dict[int, float],
    load_points: dict[int, float],
    fuel_price: float,
    max_capacity: float,
) -> CostCurve:
    """Create cost curve from heat rate bands and load points.

    This creates a piecewise linear cost curve where:
    - Load points define the power levels (MW) at each band
    - Heat rate bands define the efficiency at each power level
    - Cost = heat_rate * fuel_price at each power level

    Parameters
    ----------
    heat_rate_bands : dict[int, float]
        The heat rate values by band (e.g., {1: 10.0, 2: 9.5, 3: 9.0})
    load_points : dict[int, float]
        The load points defining power levels (e.g., {1: 30, 2: 60, 3: 100})
    fuel_price : float
        The fuel price ($/MMBtu)
    max_capacity : float
        The maximum capacity (MW)

    Returns
    -------
    CostCurve
        The cost curve with piecewise linear segments

    Notes
    -----
    This function creates a piecewise linear cost curve from heat rate bands.
    The heat rate typically decreases as power increases (better efficiency).
    Each band represents a segment of the cost curve.
    """
    breakpoints = []

    # Match heat rate bands to load points
    for band in sorted(heat_rate_bands.keys()):
        if band in load_points:
            power = load_points[band]
            if power <= max_capacity:
                heat_rate = heat_rate_bands[band]
                cost = heat_rate * fuel_price if fuel_price > 0 else heat_rate
                breakpoints.append((power, cost))

    # Sort breakpoints by power level
    breakpoints.sort(key=lambda x: x[0])

    # Handle edge cases
    if not breakpoints:
        base_cost = (
            next(iter(heat_rate_bands.values())) * fuel_price if heat_rate_bands and fuel_price > 0 else 0.0
        )
        return create_flat_cost_curve(base_cost)

    if len({bp[0] for bp in breakpoints}) <= 1:
        # All breakpoints have the same power level
        return create_flat_cost_curve(breakpoints[0][1])

    # Remove duplicate x values, keeping the first occurrence
    unique_breakpoints = []
    seen_x = set()
    for x, y in breakpoints:
        if x not in seen_x:
            unique_breakpoints.append((x, y))
            seen_x.add(x)

    # Create piecewise step data
    # x_coords defines the power breakpoints: [0, 30, 60, 100]
    # y_coords defines the cost in each segment
    x_coords = [0.0] + [bp[0] for bp in unique_breakpoints]
    y_coords = [bp[1] for bp in unique_breakpoints]

    # Validate lengths: y_coords should have length = len(x_coords) - 1
    if len(y_coords) != len(x_coords) - 1:
        return create_flat_cost_curve(y_coords[0] if y_coords else 0.0)

    return CostCurve(
        power_units=UnitSystem.NATURAL_UNITS,
        value_curve=IncrementalCurve(
            function_data=PiecewiseStepData(x_coords=x_coords, y_coords=y_coords),
            initial_input=0.0,
        ),
    )


def create_curve_from_even_bands(
    markup_bands: dict[int, float], base_cost: float, max_capacity: float
) -> CostCurve:
    """Create cost curve with evenly distributed bands across generation range.

    Parameters
    ----------
    markup_bands : dict[int, float]
        The markup values by band
    base_cost : float
        The base cost value
    max_capacity : float
        The maximum capacity

    Returns
    -------
    CostCurve
        The cost curve with evenly distributed breakpoints
    """
    bands = sorted(markup_bands.keys())

    # Handle edge cases
    if not bands or max_capacity <= 0:
        return create_flat_cost_curve(base_cost)

    band_size = max_capacity / len(bands)
    if band_size <= 0:
        return create_flat_cost_curve(base_cost + markup_bands[bands[0]])

    breakpoints = []
    for i, band in enumerate(bands):
        point = min((i + 1) * band_size, max_capacity)
        markup = markup_bands[band]
        breakpoints.append((point, base_cost + markup))

    # Remove duplicate x values
    unique_breakpoints = []
    seen_x = set()
    for x, y in breakpoints:
        if x not in seen_x:
            unique_breakpoints.append((x, y))
            seen_x.add(x)

    # Create piecewise step data
    # x_coords defines the breakpoints
    # y_coords defines the cost in each segment
    x_coords = [0.0] + [bp[0] for bp in unique_breakpoints]
    y_coords = [bp[1] for bp in unique_breakpoints]

    # Validate lengths: y_coords should have length = len(x_coords) - 1
    if len(y_coords) != len(x_coords) - 1:
        return create_flat_cost_curve(base_cost)

    return CostCurve(
        power_units=UnitSystem.NATURAL_UNITS,
        value_curve=IncrementalCurve(
            function_data=PiecewiseStepData(x_coords=x_coords, y_coords=y_coords),
            initial_input=0.0,
        ),
    )


def create_cost_curve_from_markup(
    component: PLEXOSGenerator,
    system: System | None = None,
    scenario: str | None = None,
    timeslice: str | None = None,
) -> CostCurve:
    """Create a cost curve using mark-up values or heat rate bands.

    Priority order:
    1. Heat rate bands + load points (piecewise linear)
    2. Markup bands + markup points
    3. Markup bands + load points
    4. Markup bands evenly distributed

    Parameters
    ----------
    component : PLEXOSGenerator
        The generator component
    system : System, optional
        The system containing the component
    scenario : str, optional
        The scenario to use
    timeslice : str, optional
        The timeslice to use

    Returns
    -------
    CostCurve
        The cost curve based on available data
    """
    assert system is not None, "system parameter is required for create_cost_curve_from_markup"

    # Get maximum capacity
    max_capacity = get_plexos_property(system, component, "max_capacity")

    # Get fuel price
    fuel_price = get_plexos_property(system, component, "fuel_price")

    # Case 0: Check for heat rate bands + load points (highest priority for piecewise curves)
    heat_rate_bands = {}
    if hasattr(component, "heat_rate"):
        heat_rate_bands = extract_bands(component.heat_rate, scenario, timeslice)

    if heat_rate_bands and hasattr(component, "load_point"):
        load_points = extract_bands(component.load_point, scenario, timeslice)
        # Use heat rate bands with load points if both are available
        if load_points:
            logger.debug("Creating cost curve from heat rate bands and load points for '{}'", component.name)
            return create_curve_from_heat_rate_bands(heat_rate_bands, load_points, fuel_price, max_capacity)

    # Calculate base cost from single heat_rate value if no bands
    base_cost = 0.0
    if not heat_rate_bands:
        heat_rate = get_plexos_property(system, component, "heat_rate")
        if heat_rate > 0 and fuel_price > 0:
            base_cost = heat_rate * fuel_price

    # Get markup bands
    markup_bands = {}
    if hasattr(component, "mark_up"):
        markup_bands = extract_bands(component.mark_up, scenario, timeslice)

    # If no markup bands, return flat cost curve
    if not markup_bands:
        return create_flat_cost_curve(base_cost)

    # Case 1: Use markup points if available
    if hasattr(component, "mark_up_point"):
        markup_points = extract_bands(component.mark_up_point, scenario, timeslice)
        if markup_points:
            return create_curve_from_markup_points(markup_bands, markup_points, base_cost, max_capacity)

    # Case 2: Use load points if available (relax exact matching requirement)
    if hasattr(component, "load_point"):
        load_points = extract_bands(component.load_point, scenario, timeslice)
        if load_points:
            # Use load points even if number doesn't exactly match markup_bands
            # This handles cases where some bands might be missing
            return create_curve_from_load_points(markup_bands, load_points, base_cost, max_capacity)

    # Case 3: Create evenly distributed bands
    return create_curve_from_even_bands(markup_bands, base_cost, max_capacity)


def create_cost_from_offers(
    component: PLEXOSGenerator,
    system: System | None = None,
    scenario: str | None = None,
    timeslice: str | None = None,
) -> CostCurve:
    """Create cost curve from generator offer price and quantity.

    Parameters
    ----------
    component : PLEXOSGenerator
        The generator component
    system : System, optional
        The system containing the component
    scenario : str, optional
        The scenario to use
    timeslice : str, optional
        The timeslice to use

    Returns
    -------
    CostCurve
        The cost curve based on offers
    """
    # Extract offer price and quantity bands
    price_bands = {}
    quantity_bands = {}

    if hasattr(component, "offer_price"):
        price_bands = extract_bands(component.offer_price, scenario, timeslice)

    if hasattr(component, "offer_quantity"):
        quantity_bands = extract_bands(component.offer_quantity, scenario, timeslice)

    # Fall back to markup if offers are empty
    if not price_bands or not quantity_bands:
        return create_cost_curve_from_markup(component, system, scenario, timeslice)

    # Create breakpoints from offer price and quantity
    breakpoints = []
    cumulative_quantity = 0.0

    # Find bands present in both price and quantity
    shared_bands = sorted(set(price_bands.keys()) & set(quantity_bands.keys()))

    for band in shared_bands:
        price = price_bands[band]
        quantity = quantity_bands[band]

        if quantity > 0:
            cumulative_quantity += quantity
            breakpoints.append((cumulative_quantity, price))

    # Fall back to markup if no valid breakpoints
    if not breakpoints:
        return create_cost_curve_from_markup(component, system, scenario, timeslice)

    # Create piecewise step function
    x_coords = [0.0] + [bp[0] for bp in breakpoints]
    y_coords = [breakpoints[0][1]] + [bp[1] for bp in breakpoints]

    return CostCurve(
        power_units=UnitSystem.NATURAL_UNITS,
        value_curve=IncrementalCurve(
            function_data=PiecewiseStepData(x_coords=x_coords, y_coords=y_coords),
            initial_input=0.0,
        ),
    )


@singledispatch
def create_operational_cost(
    component: SiennaComponent,
    plexos_component: Any = None,
    system: System | None = None,
    scenario: str | None = None,
    timeslice: str | None = None,
) -> ThermalGenerationCost | RenewableGenerationCost | HydroGenerationCost | StorageCost:
    """Create an appropriate operational cost model based on component type.

    Parameters
    ----------
    component : SiennaComponent
        The generator or storage component
    plexos_component : Any, optional
        The original PLEXOS component
    system : System, optional
        The system containing the component
    scenario : str, optional
        The scenario to use for extracting cost parameters
    timeslice : str, optional
        The timeslice to use for extracting cost parameters

    Returns
    -------
    ThermalGenerationCost | RenewableGenerationCost | HydroGenerationCost | StorageCost
        The appropriate operational cost model for the component type
    """
    # Default: zero cost thermal
    return ThermalGenerationCost(
        fixed=0.0,
        shut_down=0.0,
        start_up=0.0,
        variable=FuelCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS),
    )


@create_operational_cost.register
def _(
    component: ThermalStandard,
    plexos_component: Any = None,
    system: System | None = None,
    scenario: str | None = None,
    timeslice: str | None = None,
) -> ThermalGenerationCost:
    """Create thermal generation cost model for thermal generators."""
    # Initialize basic cost parameters
    fixed_cost = 0.0
    shut_down_cost = 0.0
    start_up_cost = 0.0
    variable: CostCurve | FuelCurve | None = None

    # Extract basic cost parameters from PLEXOS component if available
    if isinstance(plexos_component, PLEXOSGenerator):
        assert system is not None, "system parameter is required when plexos_component is provided"

        # Extract fixed cost
        if hasattr(plexos_component, "fixed_cost"):
            fixed_cost = get_plexos_property(system, plexos_component, "fixed_cost")

        # Extract shut down cost
        if hasattr(plexos_component, "shutdown_cost"):
            shut_down_cost = get_plexos_property(system, plexos_component, "shutdown_cost")

        # Extract start up cost
        if hasattr(plexos_component, "start_cost"):
            start_up_cost = get_plexos_property(system, plexos_component, "start_cost")

        # Create variable cost curve using sophisticated methods
        # Priority: 1) offer curves, 2) markup curves, 3) simple variable cost
        try:
            # Try creating from offers first (most detailed)
            if hasattr(plexos_component, "offer_price") and hasattr(plexos_component, "offer_quantity"):
                offer_price_bands = extract_bands(plexos_component.offer_price, scenario, timeslice)
                offer_qty_bands = extract_bands(plexos_component.offer_quantity, scenario, timeslice)

                if offer_price_bands and offer_qty_bands:
                    variable = create_cost_from_offers(plexos_component, system, scenario, timeslice)

            # Fall back to markup-based cost curve if offers not available
            if variable is None and (
                hasattr(plexos_component, "heat_rate") or hasattr(plexos_component, "mark_up")
            ):
                variable = create_cost_curve_from_markup(plexos_component, system, scenario, timeslice)

            # Final fallback to simple variable cost
            if variable is None and hasattr(plexos_component, "variable_cost"):
                value = get_plexos_property(system, plexos_component, "variable_cost")
                if value and value > 0:
                    variable = CostCurve(value_curve=LinearCurve(value), power_units=UnitSystem.NATURAL_UNITS)
        except Exception as e:
            logger.warning(
                "Failed to create sophisticated cost curve for {}: {}. Using simple cost.",
                plexos_component.name,
                str(e),
            )
            # Fall back to simple variable cost on any error
            if hasattr(plexos_component, "variable_cost"):
                value = get_plexos_property(system, plexos_component, "variable_cost")
                if value and value > 0:
                    variable = CostCurve(value_curve=LinearCurve(value), power_units=UnitSystem.NATURAL_UNITS)

    # Set default variable cost if not specified
    if variable is None:
        variable = FuelCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS)

    return ThermalGenerationCost(
        fixed=fixed_cost,
        shut_down=shut_down_cost,
        start_up=start_up_cost,
        variable=variable,
    )


@create_operational_cost.register(RenewableDispatch)
@create_operational_cost.register(RenewableNonDispatch)
def _(
    component: RenewableDispatch | RenewableNonDispatch,
    plexos_component: Any = None,
    system: System | None = None,
    scenario: str | None = None,
    timeslice: str | None = None,
) -> RenewableGenerationCost:
    """Create renewable generation cost model for renewable generators."""
    curtailment_cost = None
    variable = CostCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS)

    # Extract cost parameters from PLEXOS component if available
    if isinstance(plexos_component, PLEXOSGenerator):
        assert system is not None, "system parameter is required when plexos_component is provided"

        # Extract curtailment cost
        if hasattr(plexos_component, "curtailment_cost"):
            cost_value = get_plexos_property(system, plexos_component, "curtailment_cost")
            if cost_value and cost_value > 0:
                curtailment_cost = CostCurve(
                    value_curve=LinearCurve(cost_value),
                    power_units=UnitSystem.NATURAL_UNITS,
                )

        # Extract variable cost
        if hasattr(plexos_component, "variable_cost"):
            value = get_plexos_property(system, plexos_component, "variable_cost")
            if value and value > 0:
                variable = CostCurve(value_curve=LinearCurve(value), power_units=UnitSystem.NATURAL_UNITS)

    # Set default curtailment cost if not specified
    if curtailment_cost is None:
        curtailment_cost = CostCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS)

    return RenewableGenerationCost(curtailment_cost=curtailment_cost, variable=variable)


@create_operational_cost.register
def _(
    component: HydroDispatch,
    plexos_component: Any = None,
    system: System | None = None,
    scenario: str | None = None,
    timeslice: str | None = None,
) -> HydroGenerationCost:
    """Create hydro generation cost model for hydro generators."""
    fixed_cost = 0.0
    variable = None

    if isinstance(plexos_component, PLEXOSGenerator):
        assert system is not None, "system parameter is required when plexos_component is provided"

        if hasattr(plexos_component, "fixed_cost"):
            fixed_cost = get_plexos_property(system, plexos_component, "fixed_cost")

        if hasattr(plexos_component, "variable_cost"):
            value = get_plexos_property(system, plexos_component, "variable_cost")
            if value and value > 0:
                variable = CostCurve(value_curve=LinearCurve(value), power_units=UnitSystem.NATURAL_UNITS)

    if variable is None:
        variable = CostCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS)

    return HydroGenerationCost(fixed=fixed_cost, variable=variable)


@create_operational_cost.register
def _(
    component: EnergyReservoirStorage,
    plexos_component: Any = None,
    system: System | None = None,
    scenario: str | None = None,
    timeslice: str | None = None,
) -> StorageCost:
    """Create storage cost model for energy storage systems."""
    fixed_cost = 0.0
    start_up_cost = 0.0
    shut_down_cost = 0.0
    energy_shortage_cost = 0.0
    energy_surplus_cost = 0.0
    charge_variable_cost = None
    discharge_variable_cost = None

    # Extract cost parameters from PLEXOS component if available
    if isinstance(plexos_component, PLEXOSBattery):
        assert system is not None, "system parameter is required when plexos_component is provided"

        # Extract fixed cost
        if hasattr(plexos_component, "fixed_cost"):
            fixed_cost = get_plexos_property(system, plexos_component, "fixed_cost")

        # Extract start up cost
        if hasattr(plexos_component, "start_cost"):
            start_up_cost = get_plexos_property(system, plexos_component, "start_cost")

        # Extract shut down cost
        if hasattr(plexos_component, "shutdown_cost"):
            shut_down_cost = get_plexos_property(system, plexos_component, "shutdown_cost")

        # Extract energy shortage cost
        if hasattr(plexos_component, "energy_shortage_cost"):
            energy_shortage_cost = get_plexos_property(system, plexos_component, "energy_shortage_cost")

        # Extract energy surplus cost
        if hasattr(plexos_component, "energy_surplus_cost"):
            energy_surplus_cost = get_plexos_property(system, plexos_component, "energy_surplus_cost")

        # Extract charge cost
        if hasattr(plexos_component, "charge_cost"):
            value = get_plexos_property(system, plexos_component, "charge_cost")
            if value and value > 0:
                charge_variable_cost = CostCurve(
                    value_curve=LinearCurve(value), power_units=UnitSystem.NATURAL_UNITS
                )

        # Extract discharge cost
        if hasattr(plexos_component, "discharge_cost"):
            value = get_plexos_property(system, plexos_component, "discharge_cost")
            if value and value > 0:
                discharge_variable_cost = CostCurve(
                    value_curve=LinearCurve(value), power_units=UnitSystem.NATURAL_UNITS
                )

    # Set default cost curves if not specified
    if charge_variable_cost is None:
        charge_variable_cost = CostCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS)

    if discharge_variable_cost is None:
        discharge_variable_cost = CostCurve(
            value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS
        )

    return StorageCost(
        fixed=fixed_cost,
        start_up=start_up_cost,
        shut_down=shut_down_cost,
        energy_shortage_cost=energy_shortage_cost,
        energy_surplus_cost=energy_surplus_cost,
        charge_variable_cost=charge_variable_cost,
        discharge_variable_cost=discharge_variable_cost,
    )
