"""Getters for ReEDS to Plexos translation."""

from __future__ import annotations

import json
from importlib.resources import files
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
        ReEDSRegion,
        ReEDSReserve,
        ReEDSStorage,
        ReEDSThermalGenerator,
        ReEDSTransmissionLine,
        ReEDSVariableGenerator,
    )

    from r2x_core import PluginContext


def _float_or_zero(value: Any | None) -> float:
    """Normalize optional numeric values."""
    if value is None:
        return 0.0
    return float(value)


def _get_defaults(technology: str, key: str) -> float:
    if technology.lower().startswith("battery"):
        technology = "battery"
    defaults_path = files("r2x_reeds_to_plexos.config") / "defaults.json"
    with defaults_path.open() as f:
        defaults = json.load(f)
    value = defaults.get("pcm_defaults", {}).get(technology, {}).get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _lookup_target_node(context: PluginContext, region_name: str) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node for a given region name."""
    from r2x_plexos.models import PLEXOSNode

    for node in context.target_system.get_components(PLEXOSNode):
        if node.name == region_name:
            return Ok(node)
    return Err(ValueError(f"No PLEXOSNode found for region '{region_name}'"))


def _lookup_source_generator(context: PluginContext, name: str) -> Any | None:
    """Find a ReEDS generator-like component by name."""
    from r2x_reeds.models import ReEDSConsumingTechnology, ReEDSGenerator

    for gen in context.source_system.get_components(ReEDSGenerator):
        if gen.name == name:
            return gen

    for consuming_tech in context.source_system.get_components(ReEDSConsumingTechnology):
        if consuming_tech.name == name:
            return consuming_tech

    return None


@getter
def get_component_units(component: object, context: PluginContext) -> Result[str, ValueError]:
    """Return the units/availability for a given component."""
    return Ok(1)


@getter
def region_load(component: ReEDSRegion, context: PluginContext) -> Result[float | int, ValueError]:
    """Return the load for a region as a PLEXOSPropertyValue with units MW."""

    value = _float_or_zero(getattr(component, "load", 0.0))
    return Ok(value)


@getter
def region_ext(component: ReEDSRegion, context: PluginContext) -> Result[dict, ValueError]:
    """Return the PLEXOS region ext dict for a ReEDSRegion, including transmission_region."""
    ext = getattr(component, "ext", {}) or {}
    transmission_region = getattr(component, "transmission_region", None)
    if transmission_region:
        ext = dict(ext)
        ext["transmission_region"] = transmission_region
    return Ok(ext)


@getter
def hydro_max_energy_per_day(
    component: ReEDSHydroGenerator, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return the maximum energy per day for a hydro generator as a PLEXOSPropertyValue with units MW."""
    value = _float_or_zero(getattr(component, "max_energy_per_day", 0.0))
    return Ok(value)


@getter
def rating(component: ReEDSGenerator, context: PluginContext) -> Result[float | int, ValueError]:
    """Return the rating as a PLEXOSPropertyValue with units MW."""
    value = _float_or_zero(getattr(component, "capacity", 0.0))
    return Ok(value)


@getter
def load_subtracter(component: ReEDSGenerator, context: PluginContext) -> Result[float | int, ValueError]:
    """Return the load subtracter as a PLEXOSPropertyValue with units MW."""
    value = _float_or_zero(getattr(component, "load_subtracter", 0.0))
    return Ok(value)


@getter
def add_head_suffix(component: ReEDSStorage, context: PluginContext) -> Result[str, ValueError]:
    """Add '_head' suffix to the storage name."""
    name = getattr(component, "name", "")
    return Ok(f"{name}_head")


@getter
def add_tail_suffix(component: ReEDSStorage, context: PluginContext) -> Result[str, ValueError]:
    """Add '_tail' suffix to the storage name."""
    name = getattr(component, "name", "")
    return Ok(f"{name}_tail")


@getter
def storage_max_volume(component: ReEDSStorage, context: PluginContext) -> Result[float, ValueError]:
    """Return the maximum volume for storage."""
    capacity = getattr(component, "capacity", 0.0)
    duration = getattr(component, "storage_duration", 0.0)
    max_volume = round(float(capacity) * float(duration), 1)
    return Ok(float(max_volume))


@getter
def storage_initial_volume(component: ReEDSStorage, context: PluginContext) -> Result[float, ValueError]:
    """Return the initial volume for storage (assumed 50% if not specified)."""
    initial_volume = _float_or_zero(getattr(component, "energy_capacity", 0.0))
    return Ok(float(initial_volume))


@getter
def storage_natural_inflow(component: ReEDSStorage, context: PluginContext) -> Result[float, ValueError]:
    """Return the natural inflow for storage as a PLEXOSPropertyValue with units MW."""
    value = _float_or_zero(getattr(component, "natural_inflow", 0.0))
    return Ok(value)


@getter
def get_generator_pump_efficiency_percent(
    component: ReEDSGenerator, context: PluginContext
) -> Result[float, ValueError]:
    """Convert pumped hydro efficiency (0-1) to percent for PLEXOS."""
    from r2x_reeds.models import (
        ReEDSConsumingTechnology,
        ReEDSHydroGenerator,
        ReEDSStorage,
        ReEDSThermalGenerator,
        ReEDSVariableGenerator,
    )

    if isinstance(
        component,
        ReEDSConsumingTechnology | ReEDSThermalGenerator | ReEDSVariableGenerator | ReEDSHydroGenerator,
    ):
        return Ok(0.0)
    elif isinstance(component, ReEDSStorage):
        efficiency = getattr(component, "pump_efficiency", None)
        if efficiency is not None:
            return Ok(_float_or_zero(efficiency) * 100.0)

        charge_efficiency = getattr(component, "charge_efficiency", None)
        if charge_efficiency is not None:
            return Ok(_float_or_zero(charge_efficiency) * 100.0)

        round_trip_efficiency = getattr(component, "round_trip_efficiency", None)
        if round_trip_efficiency is not None:
            return Ok(_float_or_zero(round_trip_efficiency) * 100.0)
    else:
        return Ok(0.0)


@getter
def get_generator_pump_load_mw(
    component: ReEDSGenerator, context: PluginContext
) -> Result[float, ValueError]:
    """Return the pumped hydro load in MW."""
    from r2x_reeds.models import (
        ReEDSConsumingTechnology,
        ReEDSHydroGenerator,
        ReEDSStorage,
        ReEDSThermalGenerator,
        ReEDSVariableGenerator,
    )

    if isinstance(
        component,
        ReEDSConsumingTechnology | ReEDSThermalGenerator | ReEDSVariableGenerator | ReEDSHydroGenerator,
    ):
        return Ok(0.0)
    elif isinstance(component, ReEDSStorage):
        load = getattr(component, "pump_load", None)
        if load is not None:
            return Ok(_float_or_zero(load))

        capacity = getattr(component, "capacity", 0.0)
        return Ok(float(capacity))
    else:
        return Ok(0.0)


@getter
def reserve_type(component: ReEDSReserve, context: PluginContext) -> Result[int, ValueError]:
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
def reserve_ext(component: ReEDSReserve, context: PluginContext) -> Result[dict, ValueError]:
    """Return the PLEXOS reserve ext dict for a ReEDSReserve, including the associated region's transmission_region."""
    ext = getattr(component, "ext", {}) or {}
    region_obj = getattr(component, "region", None)
    transmission_region = getattr(region_obj, "name", None) if region_obj else None

    if region_obj:
        ext = dict(ext)
        ext["transmission_region"] = transmission_region
    return Ok(ext)


@getter
def forced_outage_rate_percent(component: object, context: PluginContext) -> Result[float, ValueError]:
    """Convert forced outage fraction (0-1) to percent expected by PLEXOS, using defaults if missing."""
    gen_technology = getattr(component, "technology", "")
    rate = getattr(component, "forced_outage_rate", None)

    if rate is not None:
        return Ok(_float_or_zero(rate) * 100.0)

    default_rate = _get_defaults(gen_technology, "forced_outage_rate")
    return Ok(float(default_rate) * 100.0)


@getter
def maintenance_rate_percent(component: object, context: PluginContext) -> Result[float, ValueError]:
    """Convert maintenance rate fraction (0-1) to percent expected by PLEXOS, using defaults if missing."""
    gen_technology = getattr(component, "technology", "")
    rate = getattr(component, "maintenance_rate", None)

    if rate is not None:
        return Ok(_float_or_zero(rate) * 100.0)

    default_rate = _get_defaults(gen_technology, "maintenance_rate")
    return Ok(float(default_rate) * 100.0)


@getter
def charge_efficiency_percent(
    component: ReEDSGenerator | ReEDSStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Convert charge efficiency (0-1) to percent for PLEXOS, using defaults if missing."""
    gen_technology = getattr(component, "technology", "")
    efficiency = getattr(component, "charge_efficiency", None)

    if efficiency is not None:
        return Ok(_float_or_zero(efficiency) * 100.0)

    default_efficiency = _get_defaults(gen_technology, "charge_efficiency")
    return Ok(float(default_efficiency) * 100.0)


@getter
def discharge_efficiency_percent(
    component: ReEDSGenerator | ReEDSStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Convert discharge efficiency (0-1) to percent for PLEXOS, using defaults if missing."""
    gen_technology = getattr(component, "technology", "")
    efficiency = getattr(component, "round_trip_efficiency", None)

    if efficiency is not None and efficiency != 0.0:
        return Ok(_float_or_zero(efficiency) * 100.0)

    default_efficiency = _get_defaults(gen_technology, "discharge_efficiency")
    return Ok(float(default_efficiency) * 100.0)


@getter
def mean_time_to_repair_hours(component: object, context: PluginContext) -> Result[float, ValueError]:
    """Return mean time to repair in hours, using defaults if missing."""
    gen_technology = getattr(component, "technology", "")
    mttr = getattr(component, "mean_time_to_repair", None)

    if mttr is not None:
        return Ok(_float_or_zero(mttr))

    default_mttr = _get_defaults(gen_technology, "mean_time_to_repair")
    if default_mttr is None:
        return Ok(24)
    return Ok(float(default_mttr))


@getter
def get_battery_max_soc(
    component: ReEDSGenerator | ReEDSStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Return maximum state of charge (percent)."""
    gen_technology = getattr(component, "technology", "")
    max_soc = getattr(component, "max_soc", None)

    if max_soc is not None:
        return Ok(_float_or_zero(max_soc))

    default_max_soc = _get_defaults(gen_technology, "max_soc")
    return Ok(float(default_max_soc))


@getter
def get_battery_initial_soc(
    component: ReEDSGenerator | ReEDSStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Return initial state of charge (percent)."""
    gen_technology = getattr(component, "technology", "")
    initial_soc = getattr(component, "initial_soc", None)

    if initial_soc is not None:
        return Ok(_float_or_zero(initial_soc))

    default_initial_soc = _get_defaults(gen_technology, "initial_soc")
    return Ok(float(default_initial_soc))


@getter
def get_battery_min_soc(
    component: ReEDSGenerator | ReEDSStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Return minimum state of charge (percent)."""
    gen_technology = getattr(component, "technology", "")
    min_soc = getattr(component, "min_soc", None)

    if min_soc is not None:
        return Ok(_float_or_zero(min_soc))

    default_min_soc = _get_defaults(gen_technology, "min_soc")
    return Ok(float(default_min_soc))


@getter
def interface_max_flow(component: ReEDSInterface, context: PluginContext) -> Result[float, ValueError]:
    """Return the maximum flow for an interface (sum of all lines' max flows)."""
    from r2x_reeds.models import ReEDSTransmissionLine

    interface_name = getattr(component, "name", "")
    total_max_flow = 0.0
    for line in context.source_system.get_components(ReEDSTransmissionLine):
        line_interface = getattr(line, "interface", None)
        if line_interface is None:
            continue

        line_interface_name = getattr(line_interface, "name", "")
        if line_interface_name == interface_name:
            limits = getattr(line, "max_active_power", None)
            if limits is not None:
                max_flow = max(limits.from_to, limits.to_from)
                total_max_flow += float(max_flow)

    return Ok(round(total_max_flow, 1))


@getter
def interface_min_flow(component: ReEDSInterface, context: PluginContext) -> Result[float, ValueError]:
    """Return the minimum flow for an interface (negative sum of all lines' max flows)."""
    from r2x_reeds.models import ReEDSTransmissionLine

    interface_name = getattr(component, "name", "")
    total_min_flow = 0.0
    for line in context.source_system.get_components(ReEDSTransmissionLine):
        line_interface = getattr(line, "interface", None)
        if line_interface is None:
            continue

        line_interface_name = getattr(line_interface, "name", "")
        if line_interface_name == interface_name:
            limits = getattr(line, "max_active_power", None)
            if limits is not None:
                min_flow = max(abs(limits.from_to), abs(limits.to_from))
                total_min_flow += float(min_flow)

    return Ok(-round(total_min_flow, 1))


@getter
def get_interface_name(component: ReEDSInterface, context: PluginContext) -> Result[str, ValueError]:
    """Return the name of the interface."""
    from_region = getattr(component, "from_region", None)
    to_region = getattr(component, "to_region", None)

    from_transmission_region = getattr(from_region, "transmission_region", "") if from_region else ""
    to_transmission_region = getattr(to_region, "transmission_region", "") if to_region else ""
    name = getattr(component, "name", "")

    interface_name = f"{from_transmission_region}_{to_transmission_region}-{name}"
    return Ok(interface_name)


@getter
def min_capacity_factor_percent(
    component: ReEDSGenerator, context: PluginContext
) -> Result[float, ValueError]:
    """Convert minimum capacity factor (0-1) to percent."""
    factor = getattr(component, "min_capacity_factor", None)
    return Ok(_float_or_zero(factor) * 100.0)


@getter
def line_max_flow(component: ReEDSTransmissionLine, context: PluginContext) -> Result[float, ValueError]:
    """Return the larger of the forward/backward flow limits."""
    limits = getattr(component, "max_active_power", None)
    if limits is None:
        return Ok(0.0)
    return Ok(float(max(limits.from_to, limits.to_from)))


@getter
def line_min_flow(component: ReEDSTransmissionLine, context: PluginContext) -> Result[float, ValueError]:
    """Return the negative of the maximum absolute flow for min_flow."""
    limits = getattr(component, "max_active_power", None)
    if limits is None:
        return Ok(0.0)
    max_abs = max(abs(limits.from_to), abs(limits.to_from))
    return Ok(-float(max_abs))


@getter
def lines_loss_incremental(
    component: ReEDSTransmissionLine, context: PluginContext
) -> Result[float, ValueError]:
    """Return the incremental loss factor for the line."""
    losses = getattr(component, "losses", None)
    if losses is None:
        return Ok(0.0)

    incremental_loss = _float_or_zero(losses.incremental)
    return Ok(incremental_loss)


@getter
def lines_wheeling_charge(line: Any, context: PluginContext) -> Result[float, ValueError]:
    """Return the wheeling charge for the forward direction (from_region to to_region)."""
    wc = getattr(line, "wheeling_charge", 0.001)
    return Ok(float(wc))


@getter
def lines_wheeling_charge_back(line: Any, context: PluginContext) -> Result[float, ValueError]:
    """Return the wheeling charge for the reverse direction (to_region to from_region)."""
    wc_back = getattr(line, "wheeling_charge_back", 0.001)
    return Ok(float(wc_back))


@getter
def storage_fom_cost_energy(component: ReEDSStorage, context: PluginContext) -> Result[float, ValueError]:
    """Return energy-based FOM cost."""
    fom_cost = getattr(component, "fom_cost", None)

    if fom_cost is None:
        return Ok(0.0)
    return Ok(_float_or_zero(fom_cost))


@getter
def storage_vom_cost_energy(component: ReEDSStorage, context: PluginContext) -> Result[float, ValueError]:
    """Return energy-based VOM cost."""
    vom_cost = getattr(component, "vom_cost", None)

    if vom_cost is None:
        return Ok(0.0)
    return Ok(_float_or_zero(vom_cost))


@getter
def reserve_vors_percent(component: ReEDSReserve, context: PluginContext) -> Result[float, ValueError]:
    """Get reserve VORS or -1.0 default value."""
    vors = getattr(component, "vors", None)
    vors = vors / 100.0 if vors is not None else -1
    return Ok(vors)


@getter
def reserve_timeframe(component: ReEDSReserve, context: PluginContext) -> Result[float, ValueError]:
    """Return the reserve timeframe in seconds."""
    return Ok(_float_or_zero(getattr(component, "time_frame", None)))


@getter
def reserve_duration(component: ReEDSReserve, context: PluginContext) -> Result[float, ValueError]:
    """Return the reserve duration in seconds."""
    return Ok(_float_or_zero(getattr(component, "duration", None)))


@getter
def reserve_requirement(component: ReEDSReserve, context: PluginContext) -> Result[float | int, ValueError]:
    """Return the reserve requirement as a PLEXOSPropertyValue with units MW."""
    value = _float_or_zero(getattr(component, "min_provision", None))
    return Ok(value)


@getter
def ramp_rate_up_mw_per_hour(
    component: ReEDSThermalGenerator, context: PluginContext
) -> Result[float, ValueError]:
    """Convert ramp rate from MW/min to MW/hour for PLEXOS."""
    ramp_rate = getattr(component, "ramp_rate", None)

    if ramp_rate is None:
        technology = getattr(component, "technology", "")
        default_ramp_up = _get_defaults(technology, "ramp_rate_up")
        if default_ramp_up > 0.0:
            return Ok(float(default_ramp_up))
        return Ok(0.0)

    return Ok(float(ramp_rate) * 60.0)


@getter
def ramp_rate_down_mw_per_hour(
    component: ReEDSThermalGenerator, context: PluginContext
) -> Result[float, ValueError]:
    """Convert ramp rate from MW/min to MW/hour for PLEXOS."""
    ramp_rate = getattr(component, "ramp_rate", None)

    if ramp_rate is None:
        technology = getattr(component, "technology", "")
        default_ramp_up = _get_defaults(technology, "ramp_rate_down")
        if default_ramp_up > 0.0:
            return Ok(float(default_ramp_up))
        return Ok(0.0)

    return Ok(float(ramp_rate) * 60.0)


@getter
def min_stable_level_mw(
    component: ReEDSThermalGenerator, context: PluginContext
) -> Result[float, ValueError]:
    """Convert min stable level from fraction to MW."""
    min_level_fraction = getattr(component, "min_stable_level", None)
    capacity = getattr(component, "capacity", 0.0)

    if min_level_fraction is None:
        return Ok(0.0)

    return Ok(float(min_level_fraction) * float(capacity))


@getter
def min_up_time_hours(component: ReEDSThermalGenerator, context: PluginContext) -> Result[float, ValueError]:
    """Return min up time in hours."""
    min_up = getattr(component, "min_up_time", None)
    return Ok(_float_or_zero(min_up))


@getter
def min_down_time_hours(
    component: ReEDSThermalGenerator, context: PluginContext
) -> Result[float, ValueError]:
    """Return min down time in hours."""
    min_down = getattr(component, "min_down_time", None)
    return Ok(_float_or_zero(min_down))


@getter
def vre_category_with_resource_class(
    component: ReEDSVariableGenerator, context: PluginContext
) -> Result[str, ValueError]:
    """Return the VRE category without resource class suffix."""
    technology = getattr(component, "technology", "")

    if not technology:
        return Err(ValueError(f"Component {component.name} has no technology"))

    # Remove resource class suffix (e.g., "_1", "_2", etc.)
    # Split by underscore and remove last part if it's a number
    parts = technology.rsplit("_", 1)
    base_technology = parts[0] if len(parts) == 2 and parts[1].isdigit() else technology

    return Ok(base_technology)


@getter
def supply_curve_cost_getter(
    component: ReEDSVariableGenerator, context: PluginContext
) -> Result[float, ValueError]:
    """Return supply curve cost as build cost."""
    cost = getattr(component, "supply_curve_cost", None)
    return Ok(_float_or_zero(cost))


@getter
def storage_energy_from_duration_or_explicit(
    component: ReEDSStorage, context: PluginContext
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
def storage_capital_cost_power(component: ReEDSStorage, context: PluginContext) -> Result[float, ValueError]:
    """Return power-based capital cost."""
    cost = getattr(component, "capital_cost", None)
    return Ok(_float_or_zero(cost))


@getter
def storage_fom_cost_power(component: ReEDSStorage, context: PluginContext) -> Result[float, ValueError]:
    """Return power-based FOM cost."""
    cost = getattr(component, "fom_cost", None)
    return Ok(_float_or_zero(cost))


@getter
def hydro_min_flow(component: ReEDSHydroGenerator, context: PluginContext) -> Result[float, ValueError]:
    """Extract minimum flow from flow_range tuple."""
    flow_range = getattr(component, "flow_range", None)
    if flow_range is None:
        return Ok(0.0)
    return Ok(float(flow_range.min))


@getter
def hydro_must_run_flag(component: ReEDSHydroGenerator, context: PluginContext) -> Result[int, ValueError]:
    """Return must_run flag for non-dispatchable hydro."""
    is_dispatchable = getattr(component, "is_dispatchable", True)
    if not is_dispatchable:
        return Ok(1)
    return Ok(0)


@getter
def consuming_tech_load_mw(
    component: ReEDSConsumingTechnology, context: PluginContext
) -> Result[float, ValueError]:
    """Return consumption capacity as load."""
    capacity = getattr(component, "capacity", None)
    return Ok(_float_or_zero(capacity))


@getter
def consuming_tech_efficiency_to_heat_rate(
    component: ReEDSConsumingTechnology, context: PluginContext
) -> Result[float, ValueError]:
    """Convert electricity efficiency to heat rate equivalent."""
    efficiency = getattr(component, "electricity_efficiency", None)
    if efficiency is None or efficiency == 0:
        return Ok(0.0)

    # Heat rate is inverse of efficiency (roughly)
    # This is a simplification; actual conversion depends on units
    return Ok(1.0 / float(efficiency))


@getter
def reeds_membership_parent_component(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the component itself for membership parent/child fields."""
    return Ok(component)


@getter
def reeds_membership_collection_nodes(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Nodes collection enum."""
    return Ok(CollectionEnum.Nodes)


@getter
def reeds_membership_collection_node_from(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the NodeFrom collection enum."""
    return Ok(CollectionEnum.NodeFrom)


@getter
def reeds_membership_collection_node_to(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the NodeTo collection enum."""
    return Ok(CollectionEnum.NodeTo)


@getter
def reeds_membership_collection_regions(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Region collection enum."""
    return Ok(CollectionEnum.Regions)


@getter
def reeds_membership_collection_region(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Region collection enum."""
    return Ok(CollectionEnum.Region)


@getter
def reeds_membership_collection_zone(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Zone collection enum."""
    return Ok(CollectionEnum.Zone)


@getter
def reeds_membership_collection_lines(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Lines collection enum."""
    return Ok(CollectionEnum.Lines)


@getter
def reeds_membership_collection_head_storage(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the HeadStorage collection enum."""
    return Ok(CollectionEnum.HeadStorage)


@getter
def reeds_membership_collection_tail_storage(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the TailStorage collection enum."""
    return Ok(CollectionEnum.TailStorage)


@getter
def reeds_membership_collection_batteries(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Batteries collection enum."""
    return Ok(CollectionEnum.Batteries)


@getter
def reeds_membership_collection_generators(
    component: Any, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Generators collection enum."""
    return Ok(CollectionEnum.Generators)


@getter
def reeds_membership_storage_generator_parent(
    component: Any, context: PluginContext
) -> Result[Any, ValueError]:
    """Return the generator itself as the parent object."""
    return Ok(component)


@getter
def reeds_membership_line_child_line(component: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the line itself as the child object."""
    return Ok(component)


@getter
def reeds_membership_region_parent_node(
    region: Any, context: PluginContext
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
    component: Any, context: PluginContext
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
def reeds_membership_node_parent_zone(node: PLEXOSNode, context: PluginContext) -> Result[Any, ValueError]:
    """Find the zone that this node belongs to based on transmission region."""
    from r2x_plexos.models import PLEXOSZone
    from r2x_reeds.models import ReEDSRegion

    node_name = getattr(node, "name", "")

    source_region = next(
        (r for r in context.source_system.get_components(ReEDSRegion) if r.name == node_name),
        None,
    )

    if source_region is None:
        return Err(ValueError(f"No source region found for node '{node_name}'"))

    transmission_region = getattr(source_region, "transmission_region", None)
    if transmission_region is None:
        return Err(ValueError(f"Source region '{node_name}' has no transmission region"))

    for zone in context.target_system.get_components(PLEXOSZone):
        if zone.name == transmission_region:
            return Ok(zone)

    return Err(ValueError(f"No PLEXOSZone found for transmission region '{transmission_region}'"))


@getter
def reeds_membership_line_from_parent_node(
    line: PLEXOSLine, context: PluginContext
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
    line: PLEXOSLine, context: PluginContext
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
def reeds_membership_storage_child_head_storage(
    generator: Any, context: PluginContext
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
    generator: Any, context: PluginContext
) -> Result[Any, ValueError]:
    """Return the tail storage (with _tail suffix) for this generator."""
    from r2x_plexos.models import PLEXOSStorage

    base_name = getattr(generator, "name", "")
    storage_name = f"{base_name}_tail"
    for storage in context.target_system.get_components(PLEXOSStorage):
        if storage.name == storage_name:
            return Ok(storage)
    return Err(ValueError(f"No tail storage found for generator '{base_name}'"))


@getter
def reeds_membership_battery_parent_spinning_reserve(
    battery: Any, context: PluginContext
) -> Result[Any, ValueError]:
    """Find SPINNING reserve for this battery."""
    return _find_battery_reserve_by_type(battery, context, "SPINNING")


@getter
def reeds_membership_battery_parent_flexibility_reserve(
    battery: Any, context: PluginContext
) -> Result[Any, ValueError]:
    """Find FLEXIBILITY reserve for this battery."""
    return _find_battery_reserve_by_type(battery, context, "FLEXIBILITY")


@getter
def reeds_membership_battery_parent_regulation_reserve(
    battery: Any, context: PluginContext
) -> Result[Any, ValueError]:
    """Find REGULATION reserve for this battery."""
    return _find_battery_reserve_by_type(battery, context, "REGULATION")


@getter
def _find_battery_reserve_by_type(
    battery: Any, context: PluginContext, reserve_type: str
) -> Result[Any, ValueError]:
    """Helper to find a specific reserve type for a battery."""
    from r2x_plexos.models import PLEXOSReserve
    from r2x_reeds.models import ReEDSStorage

    battery_name = getattr(battery, "name", "")
    source_storage = next(
        (s for s in context.source_system.get_components(ReEDSStorage) if s.name == battery_name),
        None,
    )

    if source_storage is None:
        logger.debug(f"No source storage found for battery '{battery_name}'")
        return Err(ValueError("Skip Generator with no source."))

    ext_data = getattr(source_storage, "ext", {})
    reserve_names = ext_data.get("reserves", [])

    if not reserve_names:
        logger.debug(f"Battery '{battery_name}' has no reserves in ext data")
        return Err(ValueError("Skip Generator with no source."))

    matching_reserve_name = None
    for res_name in reserve_names:
        if reserve_type in res_name:
            matching_reserve_name = res_name
            break

    if matching_reserve_name is None:
        logger.debug(f"Battery '{battery_name}' has no {reserve_type} reserve")
        return Err(ValueError("Skip Generator with no source."))

    all_reserves = list(context.target_system.get_components(PLEXOSReserve))

    for reserve in all_reserves:
        if reserve.name == matching_reserve_name:
            return Ok(reserve)

    logger.error(f"No PLEXOSReserve found for '{matching_reserve_name}'")
    return Err(ValueError(f"No PLEXOSReserve found for '{matching_reserve_name}'"))


@getter
def reeds_membership_generator_parent_spinning_reserve(
    generator: Any, context: PluginContext
) -> Result[Any, ValueError]:
    """Find SPINNING reserve for this generator."""
    return _find_generator_reserve_by_type(generator, context, "SPINNING")


@getter
def reeds_membership_generator_parent_flexibility_reserve(
    generator: Any, context: PluginContext
) -> Result[Any, ValueError]:
    """Find FLEXIBILITY reserve for this generator."""
    return _find_generator_reserve_by_type(generator, context, "FLEXIBILITY")


@getter
def reeds_membership_generator_parent_regulation_reserve(
    generator: Any, context: PluginContext
) -> Result[Any, ValueError]:
    """Find REGULATION reserve for this generator."""
    return _find_generator_reserve_by_type(generator, context, "REGULATION")


def _find_generator_reserve_by_type(
    generator: Any, context: PluginContext, reserve_type: str
) -> Result[Any, ValueError]:
    """Helper to find a specific reserve type for a generator."""
    from r2x_plexos.models import PLEXOSReserve
    from r2x_reeds.models import (
        ReEDSGenerator,
        ReEDSHydroGenerator,
        ReEDSThermalGenerator,
        ReEDSVariableGenerator,
    )

    generator_name = getattr(generator, "name", "")
    source_generator = None
    for generator_type in [
        ReEDSGenerator,
        ReEDSThermalGenerator,
        ReEDSVariableGenerator,
        ReEDSHydroGenerator,
    ]:
        source_generator = next(
            (g for g in context.source_system.get_components(generator_type) if g.name == generator_name),
            None,
        )
        if source_generator is not None:
            break

    if source_generator is None:
        return Err(ValueError("Skip Generator with no source."))

    ext_data = getattr(source_generator, "ext", {})
    reserve_names = ext_data.get("reserves", [])

    if not reserve_names:
        return Err(ValueError("Skip Generator with no source."))

    matching_reserve_name = None
    for res_name in reserve_names:
        if reserve_type in res_name:
            matching_reserve_name = res_name
            break

    if matching_reserve_name is None:
        return Err(ValueError("Skip Generator with no source."))

    all_reserves = list(context.target_system.get_components(PLEXOSReserve))

    for reserve in all_reserves:
        if reserve.name == matching_reserve_name:
            return Ok(reserve)

    return Err(ValueError(f"No PLEXOSReserve found for '{matching_reserve_name}'"))


@getter
def reeds_membership_region_child_reserve(region: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Find the reserve(s) for this region using ext['transmission_region']."""
    from r2x_plexos.models import PLEXOSReserve

    region_ext = getattr(region, "ext", {}) or {}
    transmission_region = region_ext.get("transmission_region", None)
    if not transmission_region:
        return Err(ValueError(f"No transmission_region in ext for region '{getattr(region, 'name', '')}'"))

    # You may want to return all reserves for this region, or just one
    for reserve in context.target_system.get_components(PLEXOSReserve):
        reserve_ext = getattr(reserve, "ext", {}) or {}
        if reserve_ext.get("transmission_region") == transmission_region:
            return Ok(reserve)
    return Err(ValueError(f"No PLEXOSReserve found for transmission_region '{transmission_region}'"))


@getter
def reeds_membership_line_parent_interface(line: Any, context: PluginContext) -> Result[Any, ValueError]:
    """Return the parent interface for a translated line, matching either direction by region names."""
    from r2x_plexos.models import PLEXOSInterface

    line_name = getattr(line, "name", "")
    parts = line_name.split("_")
    if len(parts) < 3:
        return Err(ValueError(f"Line name '{line_name}' does not match expected format"))

    from_region, to_region = parts[0], parts[1]

    for iface in context.target_system.get_components(PLEXOSInterface):
        iface_name = getattr(iface, "name", "")
        if f"{from_region}||{to_region}" in iface_name or f"{to_region}||{from_region}" in iface_name:
            return Ok(iface)

    return Err(
        ValueError(
            f"No PLEXOSInterface found containing '{from_region}||{to_region}' or '{to_region}||{from_region}' in its name"
        )
    )
