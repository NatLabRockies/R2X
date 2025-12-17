"""Getters for ReEDS to Plexos translation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

from loguru import logger
from plexosdb import CollectionEnum

from r2x_core import Err, Ok, Result
from r2x_core.getters import getter

if TYPE_CHECKING:
    from r2x_plexos.models import PLEXOSLine, PLEXOSNode
    from r2x_reeds.models import (
        ReEDSConsumingTechnology,
        ReEDSGenerator,
        ReEDSHydroGenerator,
        ReEDSReserve,
        ReEDSStorage,
        ReEDSThermalGenerator,
        ReEDSTransmissionLine,
        ReEDSVariableGenerator,
    )

from r2x_core.context import TranslationContext

T = TypeVar("T")


def _ok(value: T) -> Result[T, ValueError]:
    """Wrap `Ok` with a typed ValueError error type."""
    return cast(Result[T, ValueError], Ok(value))


def _float_or_zero(value: Any | None) -> float:
    """Normalize optional numeric values."""
    if value is None:
        return 0.0
    return float(value)


def _attach_region_load_time_series(
    context: TranslationContext,
    region_name: str,
    node: PLEXOSNode,
    region_component: Any | None,
) -> None:
    """Attach demand load and time series from ReEDSDemand to the translated node/region."""
    from r2x_reeds.models.components import ReEDSDemand

    demand = next(
        (
            d
            for d in context.source_system.get_components(ReEDSDemand)
            if getattr(getattr(d, "region", None), "name", None) == region_name
        ),
        None,
    )
    if demand is None:
        return

    load_value = getattr(demand, "max_active_power", None)
    if load_value is not None:
        try:
            node.load = float(load_value)
        except Exception as exc:
            logger.debug("Could not set node.load for {}: {}", node.name, exc)
        if region_component is not None:
            try:
                region_component.fixed_load = float(load_value)
            except Exception as exc:
                logger.debug("Could not set fixed_load for region {}: {}", region_name, exc)

    for metadata in context.source_system.time_series.list_time_series_metadata(demand):
        ts_list = context.source_system.list_time_series(demand, name=metadata.name, **metadata.features)
        if not ts_list:
            logger.warning("Missing demand time series {} for {}", metadata.name, demand.name)
            continue

        ts = ts_list[0]
        ts_type = ts.__class__
        if not context.target_system.has_time_series(
            node, name=metadata.name, time_series_type=ts_type, **metadata.features
        ):
            context.target_system.add_time_series(ts, node, **metadata.features)
            logger.debug("Attached demand time series {} to node {}", metadata.name, node.name)

        if region_component is not None and not context.target_system.has_time_series(
            region_component, name=metadata.name, time_series_type=ts_type, **metadata.features
        ):
            context.target_system.add_time_series(ts, region_component, **metadata.features)
            logger.debug("Attached demand time series {} to region {}", metadata.name, region_name)


@getter
def forced_outage_rate_percent(_: TranslationContext, component: ReEDSGenerator) -> Result[float, ValueError]:
    """Convert forced outage fraction (0-1) to percent expected by PLEXOS."""
    rate = getattr(component, "forced_outage_rate", None)
    return _ok(_float_or_zero(rate) * 100.0)


@getter
def min_capacity_factor_percent(
    _: TranslationContext, component: ReEDSGenerator
) -> Result[float, ValueError]:
    """Convert minimum capacity factor (0-1) to percent."""
    factor = getattr(component, "min_capacity_factor", None)
    return _ok(_float_or_zero(factor) * 100.0)


def line_max_flow(_: TranslationContext, component: ReEDSTransmissionLine) -> Result[float, ValueError]:
    """Return the larger of the forward/backward flow limits."""
    limits = getattr(component, "max_active_power", None)
    if limits is None:
        return _ok(0.0)
    return _ok(float(max(limits.from_to, limits.to_from)))


@getter
def line_min_flow(_: TranslationContext, component: ReEDSTransmissionLine) -> Result[float, ValueError]:
    """Return the negative of the maximum absolute flow for min_flow."""
    limits = getattr(component, "max_active_power", None)
    if limits is None:
        return _ok(0.0)
    max_abs = max(abs(limits.from_to), abs(limits.to_from))
    return _ok(-float(max_abs))


@getter
def reserve_timeframe(_: TranslationContext, component: ReEDSReserve) -> Result[float, ValueError]:
    """Return the reserve timeframe in seconds."""
    return _ok(_float_or_zero(getattr(component, "time_frame", None)))


@getter
def reserve_duration(_: TranslationContext, component: ReEDSReserve) -> Result[float, ValueError]:
    """Return the reserve duration in seconds."""
    return _ok(_float_or_zero(getattr(component, "duration", None)))


@getter
def reserve_requirement(_: TranslationContext, component: ReEDSReserve) -> Result[float, ValueError]:
    """Return the reserve requirement in MW."""
    return _ok(_float_or_zero(getattr(component, "max_requirement", None)))


@getter
def ramp_rate_mw_per_hour(
    _: TranslationContext, component: ReEDSThermalGenerator
) -> Result[float, ValueError]:
    """Convert ramp rate from MW/min to MW/hour for PLEXOS."""
    ramp_rate = getattr(component, "ramp_rate", None)
    if ramp_rate is None:
        return _ok(0.0)
    return _ok(float(ramp_rate) * 60.0)


@getter
def min_stable_level_mw(_: TranslationContext, component: ReEDSThermalGenerator) -> Result[float, ValueError]:
    """Convert min stable level from fraction to MW."""
    min_level_fraction = getattr(component, "min_stable_level", None)
    capacity = getattr(component, "capacity", 0.0)

    if min_level_fraction is None:
        return _ok(0.0)

    return _ok(float(min_level_fraction) * float(capacity))


@getter
def min_up_time_hours(_: TranslationContext, component: ReEDSThermalGenerator) -> Result[float, ValueError]:
    """Return min up time in hours."""
    min_up = getattr(component, "min_up_time", None)
    return _ok(_float_or_zero(min_up))


@getter
def min_down_time_hours(_: TranslationContext, component: ReEDSThermalGenerator) -> Result[float, ValueError]:
    """Return min down time in hours."""
    min_down = getattr(component, "min_down_time", None)
    return _ok(_float_or_zero(min_down))


@getter
def vre_category_with_resource_class(
    _: TranslationContext, component: ReEDSVariableGenerator
) -> Result[str, ValueError]:
    """Combine technology and resource_class for VRE category."""
    technology = getattr(component, "technology", "")
    resource_class = getattr(component, "resource_class", None)

    if resource_class is None:
        return _ok(technology)

    return _ok(f"{technology}-{resource_class}")


@getter
def supply_curve_cost_getter(
    _: TranslationContext, component: ReEDSVariableGenerator
) -> Result[float, ValueError]:
    """Return supply curve cost as build cost."""
    cost = getattr(component, "supply_curve_cost", None)
    return _ok(_float_or_zero(cost))


@getter
def storage_energy_from_duration_or_explicit(
    _: TranslationContext, component: ReEDSStorage
) -> Result[float, ValueError]:
    """Calculate energy capacity from explicit value or duration * power."""
    # First check if explicit energy_capacity is provided
    energy_capacity = getattr(component, "energy_capacity", None)
    if energy_capacity is not None:
        return _ok(float(energy_capacity))

    # Otherwise calculate from duration and power
    capacity = getattr(component, "capacity", 0.0)
    duration = getattr(component, "storage_duration", 0.0)

    return _ok(float(capacity) * float(duration))


@getter
def storage_capital_cost_power(_: TranslationContext, component: ReEDSStorage) -> Result[float, ValueError]:
    """Return power-based capital cost."""
    cost = getattr(component, "capital_cost", None)
    return _ok(_float_or_zero(cost))


@getter
def storage_fom_cost_power(_: TranslationContext, component: ReEDSStorage) -> Result[float, ValueError]:
    """Return power-based FOM cost."""
    cost = getattr(component, "fom_cost", None)
    return _ok(_float_or_zero(cost))


@getter
def hydro_min_flow(_: TranslationContext, component: ReEDSHydroGenerator) -> Result[float, ValueError]:
    """Extract minimum flow from flow_range tuple."""
    flow_range = getattr(component, "flow_range", None)
    if flow_range is None:
        return _ok(0.0)

    # flow_range is MinMax(min=..., max=...)
    return _ok(float(flow_range.min))


@getter
def hydro_ramp_rate_mw_per_hour(
    _: TranslationContext, component: ReEDSHydroGenerator
) -> Result[float, ValueError]:
    """Convert hydro ramp rate from MW/min to MW/hour."""
    ramp_rate = getattr(component, "ramp_rate", None)
    if ramp_rate is None:
        return _ok(0.0)
    return _ok(float(ramp_rate) * 60.0)


@getter
def hydro_must_run_flag(_: TranslationContext, component: ReEDSHydroGenerator) -> Result[int, ValueError]:
    """Return must_run flag for non-dispatchable hydro."""
    is_dispatchable = getattr(component, "is_dispatchable", True)

    # If not dispatchable, set must_run to 1
    if not is_dispatchable:
        return _ok(1)

    return _ok(0)


@getter
def consuming_tech_load_mw(
    _: TranslationContext, component: ReEDSConsumingTechnology
) -> Result[float, ValueError]:
    """Return consumption capacity as load."""
    capacity = getattr(component, "capacity", None)
    return _ok(_float_or_zero(capacity))


@getter
def consuming_tech_efficiency_to_heat_rate(
    _: TranslationContext, component: ReEDSConsumingTechnology
) -> Result[float, ValueError]:
    """Convert electricity efficiency to heat rate equivalent."""
    efficiency = getattr(component, "electricity_efficiency", None)
    if efficiency is None or efficiency == 0:
        return _ok(0.0)

    # Heat rate is inverse of efficiency (roughly)
    # This is a simplification; actual conversion depends on units
    return _ok(1.0 / float(efficiency))


def _lookup_target_node(context: TranslationContext, region_name: str) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node for a given region name."""
    from r2x_plexos.models import PLEXOSNode

    for node in context.target_system.get_components(PLEXOSNode):
        if node.name == region_name:
            return _ok(node)
    return Err(ValueError(f"No PLEXOSNode found for region '{region_name}'"))


def _lookup_source_generator(context: TranslationContext, name: str) -> Any | None:
    """Find a ReEDS generator-like component by name."""
    from r2x_reeds.models import ReEDSGenerator

    for gen in context.source_system.get_components(ReEDSGenerator):
        if gen.name == name:
            return gen
    return None


@getter
def reeds_membership_parent_component(_: TranslationContext, component: Any) -> Result[Any, ValueError]:
    """Return the component itself for membership parent/child fields."""
    return _ok(component)


@getter
def reeds_membership_collection_nodes(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Nodes collection enum."""
    return _ok(CollectionEnum.Nodes)


@getter
def reeds_membership_collection_node_from(
    _: TranslationContext, __: Any
) -> Result[CollectionEnum, ValueError]:
    """Return the NodeFrom collection enum."""
    return _ok(CollectionEnum.NodeFrom)


@getter
def reeds_membership_collection_node_to(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the NodeTo collection enum."""
    return _ok(CollectionEnum.NodeTo)


@getter
def reeds_membership_collection_region(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Region collection enum."""
    return _ok(CollectionEnum.Region)


@getter
def reeds_membership_region_child_node(
    context: TranslationContext, region: Any
) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node that matches the region name."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node(context, region_name)
    match result:
        case Ok(node):
            try:
                _attach_region_load_time_series(context, region_name, node, region_component=region)
            except Exception as exc:
                logger.warning("Failed to attach load time series for region %s: %s", region_name, exc)
            return result
        case Err(error):
            return Err(ValueError(str(error)) if not isinstance(error, ValueError) else error)
        case _:
            return Err(ValueError(f"Unexpected result type for region '{region_name}'"))


@getter
def reeds_membership_region_parent_node(
    context: TranslationContext, region: Any
) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node for membership parent links."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node(context, region_name)
    match result:
        case Ok(node):
            try:
                _attach_region_load_time_series(context, region_name, node, region_component=region)
            except Exception as exc:
                logger.warning("Failed to attach load time series for region %s: %s", region_name, exc)
            return result
        case Err(error):
            return Err(ValueError(str(error)) if not isinstance(error, ValueError) else error)
        case _:
            return Err(ValueError(f"Unexpected result type for region '{region_name}'"))


@getter
def reeds_membership_component_child_node(
    context: TranslationContext, component: Any
) -> Result[PLEXOSNode, ValueError]:
    """Resolve a component's region to the translated node."""
    comp_name = getattr(component, "name", "")
    source_gen = _lookup_source_generator(context, comp_name)
    if source_gen is None:
        return Err(ValueError(f"No source generator found for '{comp_name}'"))

    region = getattr(source_gen, "region", None)
    if region is None or not getattr(region, "name", None):
        return Err(ValueError(f"Source generator '{source_gen.name}' is missing region data"))

    return _lookup_target_node(context, region.name)


@getter
def reeds_membership_line_from_parent_node(
    context: TranslationContext, line: PLEXOSLine
) -> Result[PLEXOSNode, ValueError]:
    """Return the from-node for a translated line."""
    from r2x_reeds.models.components import ReEDSTransmissionLine

    source_line = next(
        (ln for ln in context.source_system.get_components(ReEDSTransmissionLine) if ln.name == line.name),
        None,
    )
    if source_line is None or source_line.interface is None:
        return Err(ValueError(f"Source line '{line.name}' missing interface data"))

    return _lookup_target_node(context, source_line.interface.from_region.name)


@getter
def reeds_membership_line_to_parent_node(
    context: TranslationContext, line: PLEXOSLine
) -> Result[PLEXOSNode, ValueError]:
    """Return the to-node for a translated line."""
    from r2x_reeds.models.components import ReEDSTransmissionLine

    source_line = next(
        (ln for ln in context.source_system.get_components(ReEDSTransmissionLine) if ln.name == line.name),
        None,
    )
    if source_line is None or source_line.interface is None:
        return Err(ValueError(f"Source line '{line.name}' missing interface data"))

    return _lookup_target_node(context, source_line.interface.to_region.name)
