"""Utility helpers for PLEXOS-to-Sienna translation."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from importlib.resources import files
from typing import Any, TypeVar

import numpy as np
from infrasys import Component, SingleTimeSeries
from infrasys.exceptions import ISNotStored, ISOperationNotAllowed
from infrasys.normalization import NormalizationByValue
from loguru import logger
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSPurchaser,
    PLEXOSRegion,
    PLEXOSReserve,
    PLEXOSStorage,
    PLEXOSTransformer,
)
from r2x_sienna.exporter import set_time_series_scaling_factor_multiplier
from r2x_sienna.models import (
    HydroDispatch,
    HydroReservoir,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    VariableReserve,
)
from r2x_sienna.models.enums import (
    PrimeMoversType,
    ThermalFuels,
)
from r2x_sienna.models.named_tuples import (
    MinMax,
)
from r2x_sienna.units import ActivePower, get_magnitude

from r2x_core import PluginContext, System, replace_single_time_series

from .constants import (
    _FUEL_KEYWORDS,
    _GENERATOR_FAMILY_BY_SLUG,
    _GENERATOR_FAMILY_KEYWORDS,
    _PLEXOS_TO_SIENNA_TARGET_TYPES,
    _PRIME_MOVER_KEYWORDS,
    P2S_NODE_NUMBER_CACHE_KEY,
    P2S_TS_PENDING_CACHE_KEY,
    PLEXOS_NUMBER_BASE,
)

TComponent = TypeVar("TComponent", bound=Component)
_LOAD_PROFILE_NAMES = {"max_active_power", "load", "fixed_load"}


def _first_numeric(value: Any) -> float:
    """Extract a scalar float, using the first PLEXOS band for mappings."""
    if isinstance(value, Mapping):
        value = value.get(1, next(iter(value.values()), 0.0))
        return float(value)

    values = getattr(value, "values", None)
    if values is not None:
        values_any: Any = values() if callable(values) else values
        try:
            return float(values_any[0])
        except (IndexError, KeyError, TypeError):
            pass
    return float(value)


def _get_pending_ts_cache(context: PluginContext) -> dict[str, Any]:
    cache = context.metadata.setdefault(P2S_TS_PENDING_CACHE_KEY, {})
    return cache


def _pending_key_for_source(component: Any) -> str:
    name = getattr(component, "name", "") or ""
    cls_name = type(component).__name__
    return f"{cls_name}:{name}"


def _get_target_types_for_source(component: Any) -> list[type[Component]]:
    for source_type, target_types in _PLEXOS_TO_SIENNA_TARGET_TYPES.items():
        if isinstance(component, source_type):
            return list(target_types)
    return []


def _get_target_components_by_name(
    target_system: System, component_type: type[TComponent], name: str
) -> list[TComponent]:
    try:
        return [target_system.get_component(component_type, name)]
    except ISNotStored:
        return []
    except ISOperationNotAllowed:
        return [
            component
            for component in target_system.get_components(component_type)
            if getattr(component, "name", None) == name
        ]


def _get_target_component_by_name(
    target_system: System, component_type: type[TComponent], name: str
) -> TComponent | None:
    components = _get_target_components_by_name(target_system, component_type, name)
    return components[0] if components else None


def _get_region_node_names(source_system: System, region: PLEXOSRegion) -> set[str]:
    return {
        membership.parent_object.name
        for membership in source_system.get_supplemental_attributes_with_component(region)
        if getattr(membership, "collection", None) == CollectionEnum.Region
        and isinstance(getattr(membership, "parent_object", None), PLEXOSNode)
    }


def _has_load_profile(source_system: System, component: Any) -> bool:
    return any(
        metadata.name in _LOAD_PROFILE_NAMES
        for metadata in source_system.list_time_series_metadata(component)
    )


def _has_node_load(source_system: System, node: PLEXOSNode) -> bool:
    return bool(_first_numeric(node.load)) or _has_load_profile(source_system, node)


def _region_has_node_load(source_system: System, region: PLEXOSRegion) -> bool:
    node_names = _get_region_node_names(source_system, region)
    return any(
        node.name in node_names and _has_node_load(source_system, node)
        for node in source_system.get_components(PLEXOSNode)
    )


def _get_targets_by_name(context: PluginContext, source_component: Any) -> list[Any]:
    if context.target_system is None:
        return []

    if isinstance(source_component, PLEXOSNode):
        return _get_target_components_by_name(context.target_system, PowerLoad, source_component.name)

    if (
        isinstance(source_component, PLEXOSRegion)
        and context.source_system is not None
        and (
            len(_get_region_node_names(context.source_system, source_component)) != 1
            or _region_has_node_load(context.source_system, source_component)
        )
    ):
        return []

    name = getattr(source_component, "name", None)
    if not name:
        return []
    targets: list[Any] = []
    for target_type in _get_target_types_for_source(source_component):
        targets.extend(_get_target_components_by_name(context.target_system, target_type, name))
    return targets


def _get_hydro_budget_values(ts: SingleTimeSeries, capacity: float) -> np.ndarray:
    """Distribute period energy limits in GWh over represented hours as capacity factors."""
    if ts.resolution != timedelta(hours=1):
        raise ValueError("PLEXOS hydro energy limits must be expanded to hourly time series")
    if capacity <= 0:
        raise ValueError("Hydro budget conversion requires a positive generator capacity")

    if ts.name not in {
        "max_energy_day",
        "max_energy_week",
        "max_energy_month",
        "max_energy_year",
    }:
        raise ValueError(f"Hydro budget conversion is not supported for {ts.name}")
    timestamps = (ts.initial_timestamp + index * ts.resolution for index in range(len(ts.data)))
    if ts.name == "max_energy_day":
        periods = [time.date() for time in timestamps]
    elif ts.name == "max_energy_month":
        periods = [(time.year, time.month) for time in timestamps]
    elif ts.name == "max_energy_week":
        # PLEXOS weeks are consecutive horizon intervals, not ISO calendar weeks.
        periods = [index // (7 * 24) for index in range(len(ts.data))]
    else:
        periods = [time.year for time in timestamps]

    # Divide by represented hours so partial periods at either horizon edge preserve their budgets.
    counts = Counter(periods)
    hours = np.array([counts[period] for period in periods])

    return np.asarray(ts.data) * 1000.0 / (capacity * hours)


def _attach_source_time_series_if_target_exists(source_component: Any, context: PluginContext) -> bool:
    if context.source_system is None or context.target_system is None:
        return True
    if isinstance(source_component, PLEXOSRegion):
        if len(_get_region_node_names(context.source_system, source_component)) != 1 or _region_has_node_load(
            context.source_system, source_component
        ):
            return True
        if not bool(_first_numeric(source_component.load)) and not _has_load_profile(
            context.source_system, source_component
        ):
            return True
    if not context.source_system.time_series.has_time_series(source_component):
        return True

    metadata_list = list(context.source_system.time_series.list_time_series_metadata(source_component))
    if not metadata_list:
        return True

    targets = _get_targets_by_name(context, source_component)
    if not targets:
        return False

    for metadata in metadata_list:
        features = getattr(metadata, "features", {}) or {}
        ts_list = context.source_system.list_time_series(source_component, name=metadata.name, **features)
        if not ts_list:
            continue

        source_ts = ts_list[0]
        if not isinstance(source_ts, SingleTimeSeries):
            continue
        for target_component in targets:
            load = (
                isinstance(source_component, (PLEXOSRegion, PLEXOSNode, PLEXOSPurchaser))
                and isinstance(target_component, PowerLoad)
                and source_ts.name in {"max_active_power", "load", "fixed_load"}
            )
            reserve_requirement = (
                isinstance(source_component, PLEXOSReserve)
                and isinstance(target_component, VariableReserve)
                and str(source_ts.name).strip().lower().replace("-", "_").replace(" ", "_")
                in {"requirement", "min_provision"}
            )
            hydro_reservoir = isinstance(source_component, PLEXOSStorage) and isinstance(
                target_component, HydroReservoir
            )
            target_name = source_ts.name
            if load:
                target_name = "max_active_power"
            elif reserve_requirement:
                target_name = "requirement"
            elif hydro_reservoir and source_ts.name == "natural_inflow":
                target_name = "inflow"
                if context.target_system.has_time_series(
                    target_component,
                    name=source_ts.name,
                    time_series_type=SingleTimeSeries,
                    **features,
                ):
                    context.target_system.remove_time_series(
                        target_component,
                        name=source_ts.name,
                        time_series_type=SingleTimeSeries,
                        **features,
                    )
            data = source_ts.data
            normalization = None
            if load:
                capacity = get_magnitude(target_component.max_active_power) * get_magnitude(
                    target_component.base_power
                )
                if capacity <= 0 and np.any(data):
                    profile_peak = float(np.max(data))
                    base_power = get_magnitude(target_component.base_power)
                    if profile_peak <= 0 or base_power <= 0:
                        raise ValueError(
                            f"Load profile requires a positive maximum for {target_component.name}"
                        )
                    target_component.max_active_power = ActivePower(profile_peak / base_power, "MW")
                    capacity = profile_peak
                normalization = NormalizationByValue(value=capacity or 1.0)
            hydro = isinstance(source_component, PLEXOSGenerator) and (
                isinstance(target_component, HydroDispatch)
                or (
                    isinstance(target_component, RenewableNonDispatch)
                    and target_component.prime_mover_type == PrimeMoversType.HY
                )
            )
            if hydro:
                capacity = _first_numeric(source_component.max_capacity)
                budget_names = {
                    "max_energy_day",
                    "max_energy_week",
                    "max_energy_month",
                    "max_energy_year",
                }
                if isinstance(target_component, HydroDispatch) and source_ts.name in budget_names:
                    periods = {
                        item.name
                        for item in metadata_list
                        if item.name in budget_names and (getattr(item, "features", {}) or {}) == features
                    }
                    if len(periods) > 1:
                        raise ValueError(
                            f"Multiple hydro budget periods are not supported for {source_component.name}"
                        )
                    data = _get_hydro_budget_values(source_ts, capacity)
                    target_name = "hydro_budget"
                elif source_ts.name in {"max_active_power", "max_energy_hour", "fixed_load"}:
                    if capacity <= 0:
                        raise ValueError("Hydro power normalization requires a positive generator capacity")
                    target_name = "max_active_power"
                    normalization = NormalizationByValue(value=capacity)
            if context.target_system.has_time_series(
                target_component,
                name=target_name,
                time_series_type=SingleTimeSeries,
                **features,
            ):
                continue
            target_ts = SingleTimeSeries.from_array(
                data=data,
                name=target_name,
                initial_timestamp=source_ts.initial_timestamp,
                resolution=source_ts.resolution,
                normalization=normalization,
            )
            try:
                context.target_system.add_time_series(target_ts, target_component, **features)
            except Exception:
                logger.debug(
                    "Failed attaching time series '{}' to '{}'",
                    source_ts.name,
                    getattr(target_component, "name", "<unknown>"),
                )
                continue
            if (hydro or load) and target_name == "max_active_power":
                set_time_series_scaling_factor_multiplier(
                    context.target_system, target_component, target_name, "get_max_active_power"
                )
    return True


def normalize_renewable_max_active_power_time_series(context: PluginContext) -> None:
    """Normalize renewable MW profiles for PowerSystems scaling."""
    source_system = context.source_system
    target_system = context.target_system
    if source_system is None or target_system is None:
        return

    renewable_targets_by_name: dict[str, list[RenewableDispatch | RenewableNonDispatch]] = {}
    for target_type in (RenewableDispatch, RenewableNonDispatch):
        for target_generator in target_system.get_components(target_type):
            renewable_targets_by_name.setdefault(target_generator.name, []).append(target_generator)

    for source_generator in source_system.get_components(PLEXOSGenerator):
        for target_generator in renewable_targets_by_name.get(source_generator.name, []):
            if (
                isinstance(target_generator, RenewableNonDispatch)
                and target_generator.prime_mover_type == PrimeMoversType.HY
            ):
                continue

            metadata_records = target_system.list_time_series_metadata(
                target_generator,
                name="max_active_power",
                time_series_type=SingleTimeSeries,
            )
            if not metadata_records:
                continue

            capacity = _first_numeric(source_generator.max_capacity)
            if capacity <= 0.0:
                has_nonzero_values = any(
                    np.any(
                        target_system.get_time_series(
                            target_generator,
                            name="max_active_power",
                            time_series_type=SingleTimeSeries,
                            **metadata.features,
                        ).data_array
                    )
                    for metadata in metadata_records
                )
                if has_nonzero_values:
                    raise ValueError(
                        f"Renewable power normalization requires a positive capacity for "
                        f"{target_generator.name}"
                    )
                capacity = 1.0

            for metadata in metadata_records:
                profile = target_system.get_time_series(
                    target_generator,
                    name="max_active_power",
                    time_series_type=SingleTimeSeries,
                    **metadata.features,
                )
                normalized_profile = SingleTimeSeries.from_array(
                    data=profile.data_array,
                    name=profile.name,
                    initial_timestamp=profile.initial_timestamp,
                    resolution=profile.resolution,
                    normalization=NormalizationByValue(value=capacity),
                )
                replace_single_time_series(
                    target_system,
                    target_generator,
                    normalized_profile,
                    **metadata.features,
                )

            set_time_series_scaling_factor_multiplier(
                target_system,
                target_generator,
                "max_active_power",
                "get_max_active_power",
            )


def normalize_reserve_requirement_time_series(context: PluginContext) -> None:
    """Normalize reserve MW profiles and their static requirement for PowerSystems scaling."""
    system = context.target_system
    if system is None:
        return

    for reserve in system.get_components(VariableReserve):
        metadata_records = system.list_time_series_metadata(
            reserve,
            name="requirement",
            time_series_type=SingleTimeSeries,
        )
        if not metadata_records:
            continue

        profiles = [
            (
                system.get_time_series(
                    reserve,
                    name="requirement",
                    time_series_type=SingleTimeSeries,
                    **metadata.features,
                ),
                metadata.features,
            )
            for metadata in metadata_records
        ]
        peak_requirement = max(float(np.max(profile.data_array)) for profile, _ in profiles)
        if peak_requirement <= 0.0:
            reserve.requirement = 0.0
            logger.warning(
                "Cannot normalize requirement time series for {} without a positive MW basis",
                reserve.name,
            )
            continue

        system_base = system.base_power
        if system_base is None or system_base <= 0.0:
            raise ValueError("Reserve normalization requires a positive system base power")
        reserve.requirement = peak_requirement / system_base

        for profile, features in profiles:
            normalized_profile = SingleTimeSeries.from_array(
                data=profile.data_array,
                name=profile.name,
                initial_timestamp=profile.initial_timestamp,
                resolution=profile.resolution,
                normalization=NormalizationByValue(value=peak_requirement),
            )
            replace_single_time_series(system, reserve, normalized_profile, **features)

        set_time_series_scaling_factor_multiplier(system, reserve, "requirement", "get_requirement")


def attach_constant_load_time_series(context: PluginContext) -> None:
    """Represent scalar source demand on existing load timelines."""
    system = context.target_system
    if context.source_system is None or system is None:
        return
    scalar_loads = {}
    profiled_loads = set()
    for source in context.source_system.iter_all_components():
        if not isinstance(source, (PLEXOSRegion, PLEXOSNode, PLEXOSPurchaser)):
            continue
        targets = _get_targets_by_name(context, source)
        if isinstance(source, (PLEXOSRegion, PLEXOSNode, PLEXOSPurchaser)):
            scalar_loads.update((load.name, load) for load in targets)
        if any(
            metadata.name in _LOAD_PROFILE_NAMES
            for metadata in context.source_system.list_time_series_metadata(source)
        ):
            profiled_loads.update(load.name for load in targets)
    loads = [load for name, load in scalar_loads.items() if name not in profiled_loads]
    if not loads:
        return
    timelines = {}
    for load in system.get_components(PowerLoad):
        for metadata in system.list_time_series_metadata(load, name="max_active_power"):
            features = dict(metadata.features)
            key = tuple(sorted((name, repr(value)) for name, value in features.items()))
            if key not in timelines:
                reference = system.get_time_series(load, name="max_active_power", **features)
                timelines[key] = (reference, features)

    for reference, features in timelines.values():
        for load in loads:
            if system.has_time_series(load, name="max_active_power", **features):
                continue
            maximum = get_magnitude(load.max_active_power)
            demand = get_magnitude(load.active_power)
            profile = SingleTimeSeries.from_array(
                data=np.full(len(reference.data), demand),
                name="max_active_power",
                initial_timestamp=reference.initial_timestamp,
                resolution=reference.resolution,
                normalization=NormalizationByValue(value=maximum or 1.0),
            )
            system.add_time_series(profile, load, **features)
            set_time_series_scaling_factor_multiplier(
                system, load, "max_active_power", "get_max_active_power"
            )


def prune_region_loads(context: PluginContext) -> None:
    """Keep region loads only when they have demand and map unambiguously to one bus."""
    source_system = context.source_system
    target_system = context.target_system
    if source_system is None or target_system is None:
        return

    for region in source_system.get_components(PLEXOSRegion):
        node_names = _get_region_node_names(source_system, region)
        has_region_demand = bool(_first_numeric(region.load)) or _has_load_profile(source_system, region)
        has_node_demand = _region_has_node_load(source_system, region)
        if len(node_names) == 1 and not has_node_demand and has_region_demand:
            continue

        if has_region_demand:
            if has_node_demand:
                logger.warning(
                    "Skipping PLEXOS region load '{}' because node-level demand is present; "
                    "using node loads to avoid duplicate demand",
                    region.name,
                )
            else:
                logger.warning(
                    "Skipping PLEXOS region load '{}' because it maps to {} nodes; "
                    "translate demand on an individual node instead",
                    region.name,
                    len(node_names),
                )
        load = _get_target_component_by_name(target_system, PowerLoad, region.name)
        if load is not None:
            target_system.remove_component(load, cascade_down=False)


def remove_unused_node_loads(context: PluginContext) -> None:
    """Remove node-load targets that have no scalar demand or load profile."""
    source_system = context.source_system
    target_system = context.target_system
    if source_system is None or target_system is None:
        return

    for node in source_system.get_components(PLEXOSNode):
        load = _get_target_component_by_name(target_system, PowerLoad, node.name)
        if load is None:
            continue

        if not _has_node_load(source_system, node):
            target_system.remove_component(load, cascade_down=False)


def _sync_time_series_for_source(source_component: Any, context: PluginContext) -> None:
    pending = _get_pending_ts_cache(context)

    # Try flushing pending entries first so previous components can be attached as soon as targets exist.
    for key, pending_source in list(pending.items()):
        if _attach_source_time_series_if_target_exists(pending_source, context):
            pending.pop(key, None)

    if not _attach_source_time_series_if_target_exists(source_component, context):
        pending[_pending_key_for_source(source_component)] = source_component


@dataclass
class _NodeNumberState:
    counter: int = PLEXOS_NUMBER_BASE
    names: dict[str, int] = field(default_factory=dict)
    used: set[int] = field(default_factory=set)


def _reserve_plexos_number(value: Any, state: _NodeNumberState) -> int | None:
    try:
        candidate = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if candidate <= 0 or candidate in state.used:
        return None

    state.used.add(candidate)
    return candidate


def _next_plexos_number(state: _NodeNumberState) -> int:
    while True:
        state.counter += 1
        candidate = _reserve_plexos_number(state.counter, state)
        if candidate is not None:
            return candidate


def extract_number_from_name(name: str, context: PluginContext) -> int:
    """Return an assigned number or allocate one unique within the translation context."""
    state = _get_node_number_state(context)
    if name in state.names:
        return state.names[name]

    for match in re.finditer(r"(\d+)", name):
        candidate = _reserve_plexos_number(match.group(1), state)
        if candidate is not None:
            state.names[name] = candidate
            return candidate

    candidate = _next_plexos_number(state)
    state.names[name] = candidate
    return candidate


def _get_node_number_state(context: PluginContext) -> _NodeNumberState:
    state = context.metadata.get(P2S_NODE_NUMBER_CACHE_KEY)
    if state is None:
        state = _NodeNumberState()
        context.metadata[P2S_NODE_NUMBER_CACHE_KEY] = state
    return state


def get_plexos_node_number(component: Any, context: PluginContext) -> int:
    """Assign a unique positive number using the component number, name, or counter."""
    state = _get_node_number_state(context)
    name = getattr(component, "name", None)
    name = str(name) if name else None
    if name is not None and name in state.names:
        return state.names[name]

    number = _reserve_plexos_number(getattr(component, "number", None), state)
    if number is not None:
        if name is not None:
            state.names[name] = number
        return number

    if name is not None:
        return extract_number_from_name(name, context)

    return _next_plexos_number(state)


def _classify_generator_category(category: str | None) -> str:
    """Return the Sienna generator technology family for a PLEXOS category.

    Resolves canonical slugs exactly, then falls back to substring keyword
    matching on descriptive names. Unmatched categories default to ``thermal``.
    """
    return _classify_generator_category_with_fallback(category)[0]


def _classify_generator_category_with_fallback(category: str | None) -> tuple[str, bool]:
    key = (category or "").strip().casefold()
    if not key:
        return "thermal", True
    if key in _GENERATOR_FAMILY_BY_SLUG:
        return _GENERATOR_FAMILY_BY_SLUG[key], False
    for keyword, family in _GENERATOR_FAMILY_KEYWORDS:
        if keyword in key:
            return family, False
    return "thermal", True


def _get_prime_mover_type(category: str) -> PrimeMoversType:
    defaults_path = files("r2x_plexos_to_sienna.config") / "defaults.json"
    with defaults_path.open() as f:
        defaults = json.load(f)
    mapping = defaults.get("prime_mover_types", {})
    key = (category or "").strip().casefold()
    if key in mapping:
        return getattr(PrimeMoversType, mapping[key], PrimeMoversType.OT)
    for keyword, code in _PRIME_MOVER_KEYWORDS:
        if keyword in key:
            return getattr(PrimeMoversType, code, PrimeMoversType.OT)
    return PrimeMoversType.OT


def _get_fuel_type(category: str) -> ThermalFuels:
    """Map a generator category to a ThermalFuels enum value via defaults.json."""
    defaults_path = files("r2x_plexos_to_sienna.config") / "defaults.json"
    with defaults_path.open() as f:
        defaults = json.load(f)
    mapping = defaults.get("fuel_types", {})
    key = (category or "").strip().casefold()
    if key in mapping:
        return getattr(ThermalFuels, mapping[key], ThermalFuels.NATURAL_GAS)
    for keyword, name in _FUEL_KEYWORDS:
        if keyword in key:
            return getattr(ThermalFuels, name, ThermalFuels.NATURAL_GAS)
    return ThermalFuels.NATURAL_GAS


def _get_target_system_base_power(context: PluginContext) -> float:
    target_system = getattr(context, "target_system", None)
    value = getattr(target_system, "base_power", None)
    try:
        base_power = float(value) if value is not None else 100.0
    except (TypeError, ValueError, OverflowError):
        return 100.0
    return base_power if math.isfinite(base_power) and base_power > 0.0 else 100.0


def _to_per_unit_power(value: Any, base_power: float, default: float = 0.0) -> float:
    """Convert a scalar or PLEXOS banded power value from MW/Mvar to per-unit."""
    value = default if value is None else value
    return _first_numeric(value) / base_power


def _get_hvdc_active_power_limits(component: PLEXOSLine, context: PluginContext) -> MinMax:
    base_power = _get_target_system_base_power(context)
    min_flow_value = getattr(component, "min_flow", None)
    max_flow_value = getattr(component, "max_flow", None)
    min_flow = _first_numeric(min_flow_value) if min_flow_value is not None else 0.0
    max_flow = _first_numeric(max_flow_value) if max_flow_value is not None else 0.0
    return MinMax(min=min_flow / base_power, max=max_flow / base_power)


def _get_trf_phase_angle_radians(component: PLEXOSTransformer) -> float:
    angle_degrees = float(getattr(component, "ac_fixed_shift_angle", 0.0) or 0.0)
    return math.radians(angle_degrees)


def _get_transformer_base_power(component: PLEXOSTransformer) -> float:
    value = getattr(component, "base_power", None)
    try:
        base_power = float(value) if value is not None else 100.0
    except (TypeError, ValueError, OverflowError):
        return 100.0
    return base_power if math.isfinite(base_power) and base_power > 0.0 else 100.0
