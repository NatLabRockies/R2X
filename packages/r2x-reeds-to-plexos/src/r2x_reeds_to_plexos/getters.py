"""Getters for ReEDS to Plexos translation."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

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
        ReEDSInterface,
        ReEDSReserve,
        ReEDSStorage,
        ReEDSThermalGenerator,
        ReEDSTransmissionLine,
        ReEDSVariableGenerator,
    )

    from r2x_core.context import TranslationContext


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
                region_component.load = float(load_value)
            except Exception as exc:
                logger.debug("Could not set load for region {}: {}", region_name, exc)

    for metadata in context.source_system.time_series.list_time_series_metadata(demand):
        ts_list = context.source_system.list_time_series(demand, name=metadata.name, **metadata.features)
        if not ts_list:
            logger.warning("Missing demand time series {} for {}", metadata.name, demand.name)
            continue

        ts = deepcopy(ts_list[0])
        ts_type = ts.__class__

        if ts.name.lower() == "max_active_power":
            ts.name = "load"

        if region_component is not None and not context.target_system.has_time_series(
            region_component, name=ts.name, time_series_type=ts_type, **metadata.features
        ):
            context.target_system.add_time_series(ts, region_component, **metadata.features)
            logger.debug("Attached demand time series {} to region {}", ts.name, region_name)


@getter
def fixed_load(_: TranslationContext, component: Any) -> Result[float, ValueError]:
    return Ok(getattr(component, "fixed_load", 0.0))


@getter
def rating(_: TranslationContext, component: Any) -> Result[float, ValueError]:
    return Ok(getattr(component, "capacity", 0.0))


@getter
def load_subtracter(_: TranslationContext, component: Any) -> Result[float, ValueError]:
    return Ok(getattr(component, "load_subtracter", 0.0))


@getter
def add_head_suffix(_: TranslationContext, component: Any) -> Result[str, ValueError]:
    """Add '_head' suffix to the storage name."""
    name = getattr(component, "name", "")
    return Ok(f"{name}_head")


@getter
def add_tail_suffix(_: TranslationContext, component: Any) -> Result[str, ValueError]:
    """Add '_tail' suffix to the storage name."""
    name = getattr(component, "name", "")
    return Ok(f"{name}_tail")


@getter
def reserve_type(_: TranslationContext, component: ReEDSReserve) -> Result[int, ValueError]:
    """Return the PLEXOS reserve type code for a ReEDSReserve."""
    mapping = {
        "REGULATION": 7,  # Regulation
        "SPINNING": 1,  # Raise
        "NON_SPINNING": 5,  # Replacement
        "FLEXIBILITY": 6,  # Operational
        "CONTINGENCY": 3,  # Regulation Raise
        "COMBO": 6,  # Operational (best fit)
    }
    res_type = getattr(component, "reserve_type", None)
    if res_type is None:
        return Ok(1)
    res_type = res_type.value
    return Ok(mapping.get(res_type, 1))


@getter
def forced_outage_rate_percent(_: TranslationContext, component: ReEDSGenerator) -> Result[float, ValueError]:
    """Convert forced outage fraction (0-1) to percent expected by PLEXOS."""
    rate = getattr(component, "forced_outage_rate", None)
    return Ok(_float_or_zero(rate) * 100.0)


@getter
def interface_min_flow(_: TranslationContext, component: ReEDSInterface) -> Result[float, ValueError]:
    """Return the minimum flow for an interface (negative of max absolute flow)."""
    return Ok(0.0)


@getter
def interface_max_flow(_: TranslationContext, component: ReEDSInterface) -> Result[float, ValueError]:
    """Return the maximum flow for an interface."""
    return Ok(0.0)


@getter
def min_capacity_factor_percent(
    _: TranslationContext, component: ReEDSGenerator
) -> Result[float, ValueError]:
    """Convert minimum capacity factor (0-1) to percent."""
    factor = getattr(component, "min_capacity_factor", None)
    return Ok(_float_or_zero(factor) * 100.0)


def line_max_flow(_: TranslationContext, component: ReEDSTransmissionLine) -> Result[float, ValueError]:
    """Return the larger of the forward/backward flow limits."""
    limits = getattr(component, "max_active_power", None)
    if limits is None:
        return Ok(0.0)
    return Ok(float(max(limits.from_to, limits.to_from)))


@getter
def line_min_flow(_: TranslationContext, component: ReEDSTransmissionLine) -> Result[float, ValueError]:
    """Return the negative of the maximum absolute flow for min_flow."""
    limits = getattr(component, "max_active_power", None)
    if limits is None:
        return Ok(0.0)
    max_abs = max(abs(limits.from_to), abs(limits.to_from))
    return Ok(-float(max_abs))


@getter
def reserve_timeframe(_: TranslationContext, component: ReEDSReserve) -> Result[float, ValueError]:
    """Return the reserve timeframe in seconds."""
    return Ok(_float_or_zero(getattr(component, "time_frame", None)))


@getter
def reserve_duration(_: TranslationContext, component: ReEDSReserve) -> Result[float, ValueError]:
    """Return the reserve duration in seconds."""
    return Ok(_float_or_zero(getattr(component, "duration", None)))


@getter
def reserve_requirement(_: TranslationContext, component: ReEDSReserve) -> Result[float | int, ValueError]:
    """Return the reserve requirement as a PLEXOSPropertyValue with units MW."""
    value = getattr(component, "requirement", None)
    value = float(value) if value is not None else 0.0
    return Ok(value)


@getter
def ramp_rate_mw_per_hour(
    _: TranslationContext, component: ReEDSThermalGenerator
) -> Result[float, ValueError]:
    """Convert ramp rate from MW/min to MW/hour for PLEXOS."""
    ramp_rate = getattr(component, "ramp_rate", None)
    if ramp_rate is None:
        return Ok(0.0)
    return Ok(float(ramp_rate) * 60.0)


@getter
def min_stable_level_mw(_: TranslationContext, component: ReEDSThermalGenerator) -> Result[float, ValueError]:
    """Convert min stable level from fraction to MW."""
    min_level_fraction = getattr(component, "min_stable_level", None)
    capacity = getattr(component, "capacity", 0.0)

    if min_level_fraction is None:
        return Ok(0.0)

    return Ok(float(min_level_fraction) * float(capacity))


@getter
def min_up_time_hours(_: TranslationContext, component: ReEDSThermalGenerator) -> Result[float, ValueError]:
    """Return min up time in hours."""
    min_up = getattr(component, "min_up_time", None)
    return Ok(_float_or_zero(min_up))


@getter
def min_down_time_hours(_: TranslationContext, component: ReEDSThermalGenerator) -> Result[float, ValueError]:
    """Return min down time in hours."""
    min_down = getattr(component, "min_down_time", None)
    return Ok(_float_or_zero(min_down))


@getter
def vre_category_with_resource_class(
    _: TranslationContext, component: ReEDSVariableGenerator
) -> Result[str, ValueError]:
    """Combine technology and resource_class for VRE category."""
    technology = getattr(component, "technology", "")
    resource_class = getattr(component, "resource_class", None)

    if resource_class is None:
        return Ok(technology)

    return Ok(f"{technology}-{resource_class}")


@getter
def supply_curve_cost_getter(
    _: TranslationContext, component: ReEDSVariableGenerator
) -> Result[float, ValueError]:
    """Return supply curve cost as build cost."""
    cost = getattr(component, "supply_curve_cost", None)
    return Ok(_float_or_zero(cost))


@getter
def storage_energy_from_duration_or_explicit(
    _: TranslationContext, component: ReEDSStorage
) -> Result[float, ValueError]:
    """Calculate energy capacity from explicit value or duration * power."""
    # First check if explicit energy_capacity is provided
    energy_capacity = getattr(component, "energy_capacity", None)
    if energy_capacity is not None:
        return Ok(float(energy_capacity))

    # Otherwise calculate from duration and power
    capacity = getattr(component, "capacity", 0.0)
    duration = getattr(component, "storage_duration", 0.0)

    return Ok(float(capacity) * float(duration))


@getter
def storage_capital_cost_power(_: TranslationContext, component: ReEDSStorage) -> Result[float, ValueError]:
    """Return power-based capital cost."""
    cost = getattr(component, "capital_cost", None)
    return Ok(_float_or_zero(cost))


@getter
def storage_fom_cost_power(_: TranslationContext, component: ReEDSStorage) -> Result[float, ValueError]:
    """Return power-based FOM cost."""
    cost = getattr(component, "fom_cost", None)
    return Ok(_float_or_zero(cost))


@getter
def hydro_min_flow(_: TranslationContext, component: ReEDSHydroGenerator) -> Result[float, ValueError]:
    """Extract minimum flow from flow_range tuple."""
    flow_range = getattr(component, "flow_range", None)
    if flow_range is None:
        return Ok(0.0)

    # flow_range is MinMax(min=..., max=...)
    return Ok(float(flow_range.min))


@getter
def hydro_ramp_rate_mw_per_hour(
    _: TranslationContext, component: ReEDSHydroGenerator
) -> Result[float, ValueError]:
    """Convert hydro ramp rate from MW/min to MW/hour."""
    ramp_rate = getattr(component, "ramp_rate", None)
    if ramp_rate is None:
        return Ok(0.0)
    return Ok(float(ramp_rate) * 60.0)


@getter
def hydro_must_run_flag(_: TranslationContext, component: ReEDSHydroGenerator) -> Result[int, ValueError]:
    """Return must_run flag for non-dispatchable hydro."""
    is_dispatchable = getattr(component, "is_dispatchable", True)

    # If not dispatchable, set must_run to 1
    if not is_dispatchable:
        return Ok(1)

    return Ok(0)


@getter
def consuming_tech_load_mw(
    _: TranslationContext, component: ReEDSConsumingTechnology
) -> Result[float, ValueError]:
    """Return consumption capacity as load."""
    capacity = getattr(component, "capacity", None)
    return Ok(_float_or_zero(capacity))


@getter
def consuming_tech_efficiency_to_heat_rate(
    _: TranslationContext, component: ReEDSConsumingTechnology
) -> Result[float, ValueError]:
    """Convert electricity efficiency to heat rate equivalent."""
    efficiency = getattr(component, "electricity_efficiency", None)
    if efficiency is None or efficiency == 0:
        return Ok(0.0)

    # Heat rate is inverse of efficiency (roughly)
    # This is a simplification; actual conversion depends on units
    return Ok(1.0 / float(efficiency))


def _lookup_target_node(context: TranslationContext, region_name: str) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node for a given region name."""
    from r2x_plexos.models import PLEXOSNode

    for node in context.target_system.get_components(PLEXOSNode):
        if node.name == region_name:
            return Ok(node)
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
    return Ok(component)


@getter
def reeds_membership_collection_nodes(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Nodes collection enum."""
    return Ok(CollectionEnum.Nodes)


@getter
def reeds_membership_collection_node_from(
    _: TranslationContext, __: Any
) -> Result[CollectionEnum, ValueError]:
    """Return the NodeFrom collection enum."""
    return Ok(CollectionEnum.NodeFrom)


@getter
def reeds_membership_collection_node_to(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the NodeTo collection enum."""
    return Ok(CollectionEnum.NodeTo)


@getter
def reeds_membership_collection_region(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Region collection enum."""
    return Ok(CollectionEnum.Region)


@getter
def reeds_membership_collection_lines(_: TranslationContext, __: Any) -> Result[CollectionEnum, ValueError]:
    """Return the Lines collection enum."""
    return Ok(CollectionEnum.Lines)


@getter
def reeds_membership_collection_head_storage(
    _: TranslationContext, __: Any
) -> Result[CollectionEnum, ValueError]:
    """Return the HeadStorage collection enum."""
    return Ok(CollectionEnum.HeadStorage)


@getter
def reeds_membership_collection_tail_storage(
    _: TranslationContext, __: Any
) -> Result[CollectionEnum, ValueError]:
    """Return the TailStorage collection enum."""
    return Ok(CollectionEnum.TailStorage)


@getter
def reeds_membership_storage_generator_parent(
    _: TranslationContext, generator: Any
) -> Result[Any, ValueError]:
    """Return the generator itself as the parent object."""
    return Ok(generator)


@getter
def reeds_membership_region_parent_node(
    context: TranslationContext, region: Any
) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node for membership parent links."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node(context, region_name)
    match result:
        case Ok(node):
            return Ok(node)
        case Err(error):
            logger.error(f"Could not find parent node for region '{region_name}': {error}")
            return Err(ValueError(f"Missing parent node for region '{region_name}'"))
        case _:
            logger.error(f"Unexpected result type for region '{region_name}'")
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


@getter
def reeds_membership_line_parent_interface(context: TranslationContext, line: Any) -> Result[Any, ValueError]:
    """Return the parent interface for a translated line, matching either direction."""
    from r2x_plexos.models import PLEXOSInterface

    parts = getattr(line, "name", "").split("_")
    if len(parts) < 3:
        return Err(ValueError(f"Line name '{getattr(line, 'name', '')}' does not match expected format"))
    from_region, to_region, _ = parts[0], parts[1], parts[2]
    interface_names = [f"{from_region}||{to_region}", f"{to_region}||{from_region}"]
    for iface in context.target_system.get_components(PLEXOSInterface):
        if iface.name in interface_names:
            return Ok(iface)
    return Err(ValueError(f"No PLEXOSInterface found for '{interface_names[0]}' or '{interface_names[1]}'"))


@getter
def reeds_membership_line_child_line(_: TranslationContext, line: Any) -> Result[Any, ValueError]:
    """Return the line itself as the child object."""
    return Ok(line)


@getter
def reeds_membership_storage_child_head_storage(
    context: TranslationContext, generator: Any
) -> Result[Any, ValueError]:
    """Return the head storage (with _head suffix) for this generator."""
    from r2x_plexos.models import PLEXOSStorage

    base_name = getattr(generator, "name", "")
    storage_name = f"{base_name}_head"
    for storage in context.target_system.get_components(PLEXOSStorage):
        if storage.name == storage_name:
            return Ok(storage)
    return Err(ValueError(f"No head storage found for generator '{base_name}'"))


@getter
def reeds_membership_storage_child_tail_storage(
    context: TranslationContext, generator: Any
) -> Result[Any, ValueError]:
    """Return the tail storage (with _tail suffix) for this generator."""
    from r2x_plexos.models import PLEXOSStorage

    base_name = getattr(generator, "name", "")
    storage_name = f"{base_name}_tail"
    for storage in context.target_system.get_components(PLEXOSStorage):
        if storage.name == storage_name:
            return Ok(storage)
    return Err(ValueError(f"No tail storage found for generator '{base_name}'"))
