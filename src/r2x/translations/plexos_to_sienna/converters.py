"""Component converters using singledispatch pattern."""

from functools import singledispatch
from typing import Any

from loguru import logger
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSObject,
    PLEXOSRegion,
)
from r2x_sienna.models import (
    ACBus,
    Area,
    AreaInterchange,
    EnergyReservoirStorage,
    PowerLoad,
)
from r2x_sienna.models.enums import ACBusTypes, PrimeMoversType, StorageTechs, ThermalFuels
from r2x_sienna.models.named_tuples import FromTo_ToFrom, InputOutput, MinMax
from r2x_sienna.units import ureg  # type: ignore[import-untyped]

from r2x.common.config import PLEXOSToSiennaConfig
from r2x.common.time_series import copy_time_series
from r2x.common.utils import create_unit_value, get_object_id
from r2x_core import Err, Ok, Result, System

from .registry import get_registry
from .utils import (
    create_operational_cost,
    get_connected_node,
    get_plexos_property,
)


@singledispatch
def convert_component(
    component: PLEXOSObject,
    plexos_system: System,
    sienna_system: System,
    config: PLEXOSToSiennaConfig,
) -> Result[None, str]:
    """Convert PLEXOS component to Sienna component.

    Parameters
    ----------
    component : PLEXOSObject
        PLEXOS component to convert
    plexos_system : System
        Source PLEXOS system
    sienna_system : System
        Target Sienna system
    config : PLEXOSToSiennaConfig
        Translation configuration

    Returns
    -------
    Result[None, str]
        Ok(None) on success, Err(message) on failure
    """
    return Err(f"No converter implemented for {type(component).__name__}")


@convert_component.register
def _(
    component: PLEXOSRegion,
    plexos_system: System,
    sienna_system: System,
    config: PLEXOSToSiennaConfig,
) -> Result[None, str]:
    """Convert PLEXOSRegion to Area."""
    try:
        # Create Area
        area = Area(
            uuid=component.uuid,
            name=component.name,
            ext={"object_id": get_object_id(component)},
        )
        sienna_system.add_component(area)

        logger.debug("Converted PLEXOSRegion '{}' to Area", component.name)
        return Ok(None)

    except Exception as e:
        return Err(f"Failed to convert PLEXOSRegion '{component.name}': {e}")


@convert_component.register
def _(
    component: PLEXOSNode,
    plexos_system: System,
    sienna_system: System,
    config: PLEXOSToSiennaConfig,
) -> Result[None, str]:
    """Convert PLEXOSNode to ACBus."""
    try:
        # Check if already processed
        if sienna_system.list_components_by_name(ACBus, component.name):
            logger.trace("ACBus '{}' already exists, skipping", component.name)
            return Ok(None)

        object_id = get_object_id(component)
        if not object_id:
            return Err(f"PLEXOSNode '{component.name}' missing object_id")

        # Create bus with default voltage
        default_voltage = config.default_voltage_kv * ureg.kV
        bus = ACBus(
            name=component.name,
            number=object_id,
            base_voltage=default_voltage,
            bustype=ACBusTypes.PV,
        )
        sienna_system.add_component(bus)

        # Check for load
        load_value = get_plexos_property(plexos_system, component, "load")
        reactive_value = get_plexos_property(plexos_system, component, "ac_reactive_power")

        if load_value != 0:
            # Build PowerLoad parameters - omit zero/None values
            load_params = {
                "name": f"{component.name}_load",
                "bus": bus,
                "max_active_power": load_value / config.system_base_power,
            }

            # Only add reactive power if non-zero
            if reactive_value > 0:
                load_params["max_reactive_power"] = reactive_value / config.system_base_power

            load = PowerLoad(**load_params)
            sienna_system.add_component(load)

            # Copy load time series
            copy_time_series(
                component,
                load,
                plexos_system,
                sienna_system,
                name_mapping={"load": "max_active_power"},
            )

        logger.debug("Converted PLEXOSNode '{}' to ACBus", component.name)
        return Ok(None)

    except Exception as e:
        return Err(f"Failed to convert PLEXOSNode '{component.name}': {e}")


@convert_component.register
def _(
    component: PLEXOSLine,
    plexos_system: System,
    sienna_system: System,
    config: PLEXOSToSiennaConfig,
) -> Result[None, str]:
    """Convert PLEXOSLine to AreaInterchange."""
    try:
        memberships = plexos_system.get_supplemental_attributes_with_component(component, PLEXOSMembership)

        from_membership = next(
            (m for m in memberships if m.collection == CollectionEnum.NodeFrom),
            None,
        )

        to_membership = next(
            (m for m in memberships if m.collection == CollectionEnum.NodeTo),
            None,
        )

        if not from_membership or not to_membership:
            return Err(f"PLEXOSLine '{component.name}' missing from/to nodes")

        # The parent_object in membership points to the connected node
        from_node = from_membership.parent_object
        to_node = to_membership.parent_object

        # Get corresponding areas
        from_area = sienna_system.get_component(Area, from_node.name)
        to_area = sienna_system.get_component(Area, to_node.name)

        # Check if reverse direction already exists
        existing = list(
            sienna_system.get_components(
                AreaInterchange,
                filter_func=lambda ai: ai.from_area == to_area and ai.to_area == from_area,
            )
        )
        if existing:
            logger.trace("Reverse AreaInterchange already exists for '{}'", component.name)
            return Ok(None)

        # Get flow limits
        max_flow = get_plexos_property(plexos_system, component, "max_flow")
        min_flow = get_plexos_property(plexos_system, component, "min_flow")
        to_from_flow = abs(min_flow) if min_flow != 0 else 0

        # Look for opposite direction line
        opposite_line = next(
            (
                line
                for line in plexos_system.get_components(PLEXOSLine)
                if line != component
                and any(
                    m.parent_object is line
                    and m.collection == CollectionEnum.NodeFrom
                    and m.child_object.name == to_area.name
                    for m in plexos_system.get_components(PLEXOSMembership)  # type: ignore[type-var]
                )
                and any(
                    m.parent_object is line
                    and m.collection == CollectionEnum.NodeTo
                    and m.child_object.name == from_area.name
                    for m in plexos_system.get_components(PLEXOSMembership)  # type: ignore[type-var]
                )
            ),
            None,
        )

        if opposite_line:
            to_from_flow = max(to_from_flow, get_plexos_property(plexos_system, opposite_line, "max_flow"))

        # Create interchange
        interchange = AreaInterchange(
            name=component.name,
            active_power_flow=0,
            from_area=from_area,
            to_area=to_area,
            flow_limits=FromTo_ToFrom(from_to=max_flow, to_from=to_from_flow),
        )
        sienna_system.add_component(interchange)

        # Copy time series
        if plexos_system.has_time_series(component, "max_flow"):
            copy_time_series(
                component,
                interchange,
                plexos_system,
                sienna_system,
                name_mapping={"max_flow": "max_active_power"},
            )

        logger.debug("Converted PLEXOSLine '{}' to AreaInterchange", component.name)
        return Ok(None)

    except Exception as e:
        return Err(f"Failed to convert PLEXOSLine '{component.name}': {e}")


@convert_component.register
def _(
    component: PLEXOSGenerator,
    plexos_system: System,
    sienna_system: System,
    config: PLEXOSToSiennaConfig,
) -> Result[None, str]:
    """Convert PLEXOSGenerator to appropriate Sienna generator type."""
    logger.info("Proccesing {}", component.label)
    if not component.category:
        return Err(f"PLEXOSGenerator '{component.name}' missing category")

    # Get mapping from registry
    registry = get_registry()
    mapping_result = registry.get(component.category)
    if mapping_result.is_err():
        return Err(f"No mapping for generator category '{component.category}'")

    mapping = mapping_result.unwrap()
    sienna_type = mapping["sienna_type"]
    prime_mover = mapping["prime_mover"]
    fuel_type = mapping.get("fuel_type")

    # Find connected bus
    node = get_connected_node(plexos_system, component)
    if not node:
        return Err(f"PLEXOSGenerator '{component.name}' not connected to any node")

    bus = sienna_system.get_component(ACBus, node.name)

    # Get capacity with units - Sienna will handle per-unit conversion
    capacity = get_plexos_property(plexos_system, component, "max_capacity")
    rating_factor = get_plexos_property(plexos_system, component, "rating_factor")

    if capacity == 0.0:
        logger.warning("PLEXOSGenerator '{}' has zero capacity, skipping", component.name)
        return Ok(None)

    # Default rating factor to 1.0 if not set
    if rating_factor == 0.0:
        rating_factor = 1.0

    base_power_mw = capacity * rating_factor

    # Create a default operation cost to initialize the generator
    from infrasys.cost_curves import FuelCurve, UnitSystem
    from infrasys.value_curves import LinearCurve
    from r2x_sienna.models.costs import ThermalGenerationCost

    default_operation_cost = ThermalGenerationCost(
        fixed=0.0,
        shut_down=0.0,
        start_up=0.0,
        variable=FuelCurve(value_curve=LinearCurve(0.0), power_units=UnitSystem.NATURAL_UNITS),
    )

    # Build kwargs dictionary with only fields that the sienna_type accepts
    # Check model_fields to avoid passing unsupported fields
    model_fields = sienna_type.model_fields

    # Start with common fields that all generator types have
    kwargs = {
        "uuid": component.uuid,
        "name": component.name,
        "bus": bus,
        "prime_mover_type": prime_mover,
        "base_power": base_power_mw,
        "active_power": 0.0,
        "reactive_power": 0.0,
        "rating": base_power_mw,
        "operation_cost": default_operation_cost,
    }

    # Add optional fields only if the model supports them
    if "active_power_limits" in model_fields:
        kwargs["active_power_limits"] = {"min": 0.0, "max": base_power_mw}

    if "must_run" in model_fields:
        kwargs["must_run"] = False

    if "status" in model_fields:
        kwargs["status"] = True

    if "time_at_status" in model_fields:
        kwargs["time_at_status"] = 0.0

    if "fuel" in model_fields:
        kwargs["fuel"] = fuel_type if fuel_type else ThermalFuels.OTHER

    # Create generator with appropriate fields for its type
    generator = sienna_type.model_construct(**kwargs)

    # Now create the proper operation cost with the generator instance
    # This triggers the correct singledispatch based on generator type
    operation_cost = create_operational_cost(generator, component, plexos_system)
    generator.operation_cost = operation_cost

    generator = sienna_type.model_validate(generator)

    sienna_system.add_component(generator)

    copy_time_series(
        component,
        generator,
        plexos_system,
        sienna_system,
        name_mapping={"max_capacity": "max_active_power", "rating": "max_active_power"},
    )

    logger.debug(
        "Converted PLEXOSGenerator '{}' to {} (base_power={} MW)",
        component.name,
        sienna_type.__name__,
        base_power_mw,
    )
    return Ok(None)


@convert_component.register
def _(
    component: PLEXOSBattery,
    plexos_system: System,
    sienna_system: System,
    config: PLEXOSToSiennaConfig,
) -> Result[None, str]:
    """Convert PLEXOSBattery to EnergyReservoirStorage."""
    try:
        # Find connected bus
        node = get_connected_node(plexos_system, component)
        if not node:
            return Err(f"PLEXOSBattery '{component.name}' not connected to any node")

        bus = sienna_system.get_component(ACBus, node.name)

        # Get properties
        base_power = get_plexos_property(plexos_system, component, "max_power")
        storage_capacity = get_plexos_property(plexos_system, component, "capacity")
        charge_efficiency = get_plexos_property(plexos_system, component, "charge_efficiency")
        discharge_efficiency = get_plexos_property(plexos_system, component, "discharge_efficiency")
        initial_soc = get_plexos_property(plexos_system, component, "initial_soc")

        # Create battery
        battery = EnergyReservoirStorage(
            uuid=component.uuid,
            name=component.name,
            bus=bus,
            base_power=create_unit_value(base_power, "MW"),
            initial_storage_capacity_level=initial_soc / 100.0,
            efficiency=InputOutput(
                input=charge_efficiency / 100.0,
                output=discharge_efficiency / 100.0,
            ),
            input_active_power_limits=MinMax(
                min=0.0,
                max=base_power,
            ),
            output_active_power_limits=MinMax(
                min=0.0,
                max=base_power,
            ),
            storage_capacity=create_unit_value(storage_capacity, "MWh"),
            storage_technology_type=StorageTechs.LIB,
            prime_mover_type=PrimeMoversType.BA,
            storage_level_limits=MinMax(min=0.0, max=storage_capacity),
            rating=base_power,
            active_power=0.0,
            reactive_power=0.0,
        )

        # Set operational cost (note: operation_cost might not exist on EnergyReservoirStorage in current version)
        # battery.operation_cost = create_operational_cost(battery, component, plexos_system)

        sienna_system.add_component(battery)

        # Copy time series
        copy_time_series(
            component,
            battery,
            plexos_system,
            sienna_system,
            name_mapping={"max_power": "max_active_power"},
        )

        logger.debug("Converted PLEXOSBattery '{}' to EnergyReservoirStorage", component.name)
        return Ok(None)

    except Exception as e:
        return Err(f"Failed to convert PLEXOSBattery '{component.name}': {e}")


@singledispatch
def post_process_component(
    component: Any,
    plexos_system: System,
    sienna_system: System,
    config: PLEXOSToSiennaConfig,
) -> Result[None, str]:
    """Post-process components (e.g., add loads for regions).

    This handles any additional Sienna components that need to be created
    based on PLEXOS components.

    Parameters
    ----------
    component : Any
        Component to post-process
    plexos_system : System
        Source PLEXOS system
    sienna_system : System
        Target Sienna system
    config : PLEXOSToSiennaConfig
        Translation configuration

    Returns
    -------
    Result[None, str]
        Ok(None) on success, Err(message) on failure
    """
    return Ok(None)  # Default: no post-processing


@post_process_component.register
def _(
    component: Area,
    plexos_system: System,
    sienna_system: System,
    config: PLEXOSToSiennaConfig,
) -> Result[None, str]:
    """Create bus and load for Area (from PLEXOSRegion)."""
    try:
        object_id = component.ext.get("object_id")
        if not object_id:
            return Ok(None)

        # Get original PLEXOS region
        plexos_region = plexos_system.get_component(PLEXOSRegion, component.name)

        # Check for load - only create bus if region has load
        load_value = get_plexos_property(plexos_system, plexos_region, "load")
        if load_value == 0:
            return Ok(None)  # No load, no bus needed

        # Check if bus already exists
        if sienna_system.list_components_by_name(ACBus, component.name):
            return Ok(None)

        # Create bus for region with load
        default_voltage = config.default_voltage_kv * ureg.kV
        bus = ACBus(
            name=component.name,
            number=object_id,
            base_voltage=default_voltage,
            bustype=ACBusTypes.PV,
        )
        sienna_system.add_component(bus)

        reactive_value = get_plexos_property(plexos_system, plexos_region, "ac_reactive_power")

        load = PowerLoad(
            name=f"{component.name}_load",
            bus=bus,
            base_power=config.system_base_power,
            active_power=0.0,
            reactive_power=0.0,
            max_active_power=load_value / config.system_base_power,
            max_reactive_power=reactive_value / config.system_base_power,
        )
        sienna_system.add_component(load)

        # Copy load time series
        copy_time_series(
            plexos_region,
            load,
            plexos_system,
            sienna_system,
            name_mapping={"load": "max_active_power"},
        )

        logger.debug("Created bus and load for Area '{}'", component.name)
        return Ok(None)

    except Exception as e:
        return Err(f"Failed to post-process Area '{component.name}': {e}")
