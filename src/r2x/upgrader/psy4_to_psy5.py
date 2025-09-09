"""Upgrade a system that was build with PSY4 into PSY5 compatible."""

from collections.abc import Callable
from typing import Any, NamedTuple

from loguru import logger

from r2x.enums import ReservoirDataType
from r2x.models.costs import HydroReservoirCost


class UpgradeStep(NamedTuple):
    """Constraints upgrades for given min max versions."""

    func: Callable
    min_version: str | None = None
    max_version: str | None = None


# List of registered steps for this upgrader
_UPGRADE_STEPS: list[UpgradeStep] = []


def register_upgrade_step(
    min_version: str | None = None, max_version: str | None = None
) -> Callable[[Callable], Callable]:
    """Register a version-aware upgrade step."""

    def decorator(func: Callable):
        _UPGRADE_STEPS.append(UpgradeStep(func, min_version, max_version))
        return func

    return decorator


def psy4_to_psy5_upgrader(system_data: dict[str, Any], old_version: str | None, new_version: str):
    """Run all version-aware upgrades in order."""
    for step in _UPGRADE_STEPS:
        if step.min_version and old_version and old_version < step.min_version:
            continue
        if step.max_version and old_version and old_version > step.max_version:
            continue
        step.func(system_data)


@register_upgrade_step(min_version="0.1.0", max_version="5.999")
def upgrade_handler_for_hydro_reservoirs(system_data: dict[str, Any]) -> None:
    """Upgrade HydroEnergyReservoir components into HydroReservoir and HydroTurbine components.

    This mutates system_data in place by replacing each HydroEnergyReservoir entry with
    a pair of new components: one HydroReservoir and one HydroTurbine.
    """
    if "components" not in system_data:
        return

    new_components: list[dict[str, Any]] = []

    for comp in system_data["components"]:
        if comp.get("type") != "HydroEnergyReservoir":
            new_components.append(comp)
            continue

        logger.debug("Upgrading component = {} to PSY5.", comp["name"])

        ext = comp.get("ext", {})

        reservoir = {
            "type": "HydroReservoir",
            "name": f"{comp['name']}_Reservoir",
            "available": comp.get("available", True),
            "storage_level_limits": {
                "min": comp.get("min_storage_capacity", 0.0),
                "max": comp.get("storage_capacity", 0.0),
            },
            "initial_level": comp.get("initial_energy", 0.0),
            "spillage_limits": None,
            "inflow": comp.get("inflow", 0.0),
            "outflow": 0.0,
            "level_targets": comp.get("storage_target"),
            "travel_time": None,
            "intake_elevation": ext.get("intake_elevation", 0.0),
            "head_to_volume_factor": ext.get("head_to_volume_factor", {"points": []}),
            "operation_cost": HydroReservoirCost().model_dump(round_trip=True),
            "level_data_type": str(ReservoirDataType.USABLE_VOLUME),  # NOTE: Is this a good default?
            "ext": ext,
        }

        turbine = {
            "type": "HydroTurbine",
            "name": f"{comp['name']}_Turbine",
            "available": comp.get("available", True),
            "bus": comp.get("bus"),
            "active_power": 0.0,
            "reactive_power": 0.0,
            "rating": comp.get("rating", 0.0),
            "active_power_limits": comp.get(
                "active_power_limits", {"min": 0.0, "max": ext.get("rating", 0.0)}
            ),
            "reactive_power_limits": None,
            "outflow_limits": None,
            "powerhouse_elevation": ext.get("powerhouse_elevation", 0.0),
            "ramp_limits": comp.get("ramp_limits"),
            "time_limits": comp.get("time_limits"),
            "base_power": comp.get("base_power", 0.0),
            "operation_cost": comp.get("operation_cost"),
            "efficiency": ext.get("efficiency", 1.0),
            "turbine_type": ext.get("turbine_type"),
            "conversion_factor": ext.get("conversion_factor", 1.0),
            "reservoirs": [f"{comp['name']}_Reservoir"],
            "services": ext.get("services", []),
            "dynamic_injector": ext.get("dynamic_injector"),
            "ext": ext,
        }

        new_components.extend([reservoir, turbine])

    system_data["components"] = new_components


@register_upgrade_step(min_version="0.1.0", max_version="5.999")
def upgrade_hydro_pumped_storage(system_data: dict[str, Any]) -> None:
    """
    Upgrade HydroPumpedStorage components into HydroPumpTurbine with head and tail HydroReservoirs.

    This mutates system_data in place by replacing each HydroPumpedStorage entry with
    a HydroPumpTurbine component and two HydroReservoir components.
    """
    if "components" not in system_data:
        return

    new_components: list[dict[str, Any]] = []

    for comp in system_data["components"]:
        if comp.get("type") != "HydroPumpedStorage":
            new_components.append(comp)
            continue

        ext = comp.get("ext", {})

        head_reservoir = {
            "type": "HydroReservoir",
            "name": f"{comp['name']}_HeadReservoir",
            "available": comp.get("available", True),
            "storage_level_limits": {
                "min": comp.get("storage_capacity", {}).get("down", 0.0),
                "max": comp.get("storage_capacity", {}).get("up", 0.0),
            },
            "initial_level": comp.get("initial_volume", 0.0),
            "inflow": comp.get("inflow", 0.0),
            "outflow": 0.0,
            "level_targets": comp.get("storage_target", {}).get("up"),
            "ext": ext,
        }

        tail_reservoir = {
            "type": "HydroReservoir",
            "name": f"{comp['name']}_TailReservoir",
            "available": comp.get("available", True),
            "storage_level_limits": {
                "min": 0.0,
                "max": comp.get("storage_capacity", {}).get("down", 0.0),
            },
            "initial_level": comp.get("initial_volume", 0.0),
            "inflow": 0.0,
            "outflow": comp.get("outflow", 0.0),
            "level_targets": comp.get("storage_target", {}).get("down"),
            "ext": ext,
        }

        pump_turbine = {
            "type": "HydroPumpTurbine",
            "name": f"{comp['name']}_PumpTurbine",
            "available": comp.get("available", True),
            "bus": comp.get("bus"),
            "active_power": comp.get("active_power", 0.0),
            "rating": comp.get("rating", 0.0),
            "rating_pump": comp.get("rating_pump", 0.0),
            "active_power_limits": comp.get("active_power_limits"),
            "active_power_limits_pump": comp.get("active_power_limits_pump"),
            "ramp_limits": comp.get("ramp_limits"),
            "ramp_limits_pump": comp.get("ramp_limits_pump"),
            "time_limits": comp.get("time_limits"),
            "time_limits_pump": comp.get("time_limits_pump"),
            "reactive_power_limits": comp.get("reactive_power_limits"),
            "reactive_power_limits_pump": comp.get("reactive_power_limits_pump"),
            "head_reservoir": head_reservoir["name"],
            "tail_reservoir": tail_reservoir["name"],
            "powerhouse_elevation": ext.get("powerhouse_elevation", 0.0),
            "base_power": comp.get("base_power"),
            "operation_cost": comp.get("operation_cost"),
            "active_power_pump": comp.get("pump_load", 0.0),
            "efficiency": {
                "turbine": ext.get("efficiency", 1.0),
                "pump": comp.get("pump_efficiency", 0.85),
            },
            "conversion_factor": comp.get("conversion_factor", 1.0),
            "storage_duration": comp.get("storage_duration"),
            "initial_storage": comp.get("initial_storage"),
            "must_run": ext.get("must_run", False),
            "prime_mover_type": comp.get("prime_mover_type"),
            "services": ext.get("services", []),
            "dynamic_injector": ext.get("dynamic_injector"),
            "ext": ext,
        }

        new_components.extend([head_reservoir, tail_reservoir, pump_turbine])

    system_data["components"] = new_components
