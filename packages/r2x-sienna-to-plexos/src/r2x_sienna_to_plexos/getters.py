"""Getter functions for rules."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping
from datetime import timedelta
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast

from infrasys.cost_curves import FuelCurve
from loguru import logger
from plexosdb.enums import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_sienna.models import (
    ACBus,
    Area,
    DiscreteControlledACBranch,
    EnergyReservoirStorage,
    HydroDispatch,
    HydroPumpedStorage,
    HydroPumpTurbine,
    HydroReservoir,
    HydroTurbine,
    Line,
    LoadZone,
    MonitoredLine,
    PhaseShiftingTransformer,
    PhaseShiftingTransformer3W,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    StandardLoad,
    TapTransformer,
    ThermalMultiStart,
    ThermalStandard,
    Transformer2W,
    Transformer3W,
    TransmissionInterface,
    TwoTerminalGenericHVDCLine,
    TwoTerminalLCCLine,
    TwoTerminalVSCLine,
    VariableReserve,
)
from r2x_sienna.models.enums import ReserveType
from r2x_sienna.models.getters import (
    get_max_active_power as sienna_get_max_active_power,
)
from r2x_sienna.units import get_magnitude

from r2x_core import Err, Ok, PluginContext, Result
from r2x_core.getters import getter
from r2x_sienna_to_plexos.getters_utils import (
    _attach_reservoir_time_series_to_storage,
    _resolve_iso_rto_for_buses,
    coerce_value,
    compute_heat_rate_data,
    compute_markup_data,
    resolve_base_power,
)

from .getters_mappings import (
    GEN_TYPE_STRING_MAP,
    REEDS_COMPONENT_SUBSTRINGS,
    SOURCE_GENERATOR_TYPES,
    SOURCE_LINE_TYPES,
)

FLOW_CLIP_MEMO_TEXT = "Setting fixed value of \u00b199999 to flows greater/less than \u00b1100000"
RAMPING_THRESHOLD = 0.1  # MW/min


def _source_system(context: PluginContext) -> Any:
    return cast(Any, context.source_system)


def _target_system(context: PluginContext) -> Any:
    return cast(Any, context.target_system)


def _get_defaults_data(context: PluginContext) -> dict[str, Any]:
    """Load defaults.json once per plugin context."""
    cached = context._cache.get("defaults_json")
    if cached is not None:
        return cast(dict[str, Any], cached)

    data = _load_defaults_json()
    context._cache["defaults_json"] = data
    return data


@lru_cache(maxsize=1)
def _load_defaults_json() -> dict[str, Any]:
    """Load defaults.json once per process for hot getter paths."""
    defaults_path = files("r2x_sienna_to_plexos.config") / "defaults.json"
    with defaults_path.open() as f:
        return cast(dict[str, Any], json.load(f))


def _get_reeds_thermal_category_from_fuel(source_component: Any, context: PluginContext) -> str | None:
    """Resolve thermal ReEDS category from Sienna fuel value using defaults mapping."""
    if not isinstance(source_component, ThermalStandard | ThermalMultiStart):
        return None

    fuel = getattr(source_component, "fuel", None)
    if fuel is None:
        return None

    fuel_str = fuel.name if hasattr(fuel, "name") else str(fuel)
    fuel_key = str(fuel_str).strip().replace("-", "_").replace(" ", "_").upper()
    if not fuel_key:
        return None

    defaults_data = _get_defaults_data(context)
    mapping = defaults_data.get("reeds_thermal_mapping", {})
    if not isinstance(mapping, dict):
        return None

    for category, fuel_values in mapping.items():
        if not isinstance(fuel_values, list):
            continue
        normalized_values = {
            str(value).strip().replace("-", "_").replace(" ", "_").upper() for value in fuel_values
        }
        if fuel_key in normalized_values:
            category_str = str(category).strip()
            if category_str in {"natural-gas", "natural_gas", "gas"}:
                return "natural-gas"
            return category_str

    return None


def _resolve_generator_category(source_component: Any, context: PluginContext) -> str | None:
    """Resolve category via prime mover, ReEDS name patterns, thermal fuel mapping, or ext gen_type_string."""
    ext = getattr(source_component, "ext", None)
    prime_mover = getattr(source_component, "prime_mover_type", None)

    # Prime mover type lookup (prime_mover_type is always a plain string, e.g. 'CC', 'PVe')
    if prime_mover is not None:
        defaults_data = _get_defaults_data(context)
        pm_types: dict[str, str] = defaults_data.get("prime_mover_types", {})
        tech = pm_types.get(prime_mover)
        if tech:
            return tech

    # ReEDS name patterns
    raw_name = getattr(source_component, "name", "") or ""
    name = raw_name.lower()
    if name.startswith("reeds"):
        for substr, tech in REEDS_COMPONENT_SUBSTRINGS:
            if substr in name:
                return tech

    if name.startswith("zonal2nodal_"):
        suffix = name[len("zonal2nodal_") :]
        _z2n_defaults = _get_defaults_data(context)
        reeds_cats = sorted(_z2n_defaults.get("reeds_defaults", {}).keys(), key=len, reverse=True)
        for cat in reeds_cats:
            cat_str = str(cat)
            if suffix == cat_str or suffix.startswith(cat_str + "_"):
                return cat_str

    # Thermal fuel mapping category
    thermal_category = _get_reeds_thermal_category_from_fuel(source_component, context)
    if thermal_category is not None:
        return thermal_category

    # Gen type string from ext dictionary
    if isinstance(ext, dict):
        gen_type = ext.get("gen_type_string", "").lower().strip()
        if gen_type and gen_type not in ("unknown", "other", "", "unidentified"):
            return GEN_TYPE_STRING_MAP.get(gen_type, gen_type)

    return None


def _build_target_storage_name_index(context: PluginContext) -> dict[str, Any]:
    """Build PLEXOSStorage names index, cached."""
    cached = context._cache.get("target_storage_name_index")
    if cached is not None:
        return cached
    if context.target_system is None:
        return {}
    result = {s.name.lower(): s for s in _target_system(context).get_components(PLEXOSStorage)}
    context._cache["target_storage_name_index"] = result
    return result


def _build_source_reserve_name_index(context: PluginContext) -> dict[str, Any]:
    """Build VariableReserve names index, cached."""
    cached = context._cache.get("source_reserve_name_index")
    if cached is not None:
        return cached
    if context.source_system is None:
        return {}
    result = {r.name: r for r in _source_system(context).get_components(VariableReserve)}
    context._cache["source_reserve_name_index"] = result
    return result


def _build_source_interface_name_index(context: PluginContext) -> dict[str, Any]:
    """Build TransmissionInterface names index, cached."""
    cached = context._cache.get("source_interface_name_index")
    if cached is not None:
        return cached
    if context.source_system is None:
        return {}
    result = {i.name: i for i in _source_system(context).get_components(TransmissionInterface)}
    context._cache["source_interface_name_index"] = result
    return result


def _build_target_line_name_index(context: PluginContext) -> dict[str, Any]:
    """Build PLEXOSLine names index, cached."""
    cached = context._cache.get("target_line_name_index")
    if cached is not None:
        return cached
    if context.target_system is None:
        return {}
    result = {ln.name: ln for ln in _target_system(context).get_components(PLEXOSLine)}
    context._cache["target_line_name_index"] = result
    return result


def _reservoir_base_name(name: str) -> str:
    """Helper to get base name of a reservoir by stripping _head/_tail suffix if present."""
    for suffix in ("_head", "_tail"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _build_generator_service_index(context: PluginContext) -> dict[str, list[Any]]:
    """Map reserve_name -> list of source generators that provide it."""
    cached = context._cache.get("generator_service_index")
    if cached is not None:
        return cached
    index: dict[str, list[Any]] = defaultdict(list)
    for gen_type in SOURCE_GENERATOR_TYPES:
        for gen in _source_system(context).get_components(gen_type):
            for service in getattr(gen, "services", None) or []:
                service_name = getattr(service, "name", None)
                if service_name:
                    index[service_name].append(gen)
    result = dict(index)
    context._cache["generator_service_index"] = result
    return result


def _build_battery_service_index(context: PluginContext) -> dict[str, list[Any]]:
    """Map reserve_name -> list of source batteries that provide it."""
    cached = context._cache.get("battery_service_index")
    if cached is not None:
        return cached
    index: dict[str, list[Any]] = defaultdict(list)
    for battery in _source_system(context).get_components(EnergyReservoirStorage):
        for service in getattr(battery, "services", None) or []:
            service_name = getattr(service, "name", None)
            if service_name:
                index[service_name].append(battery)
    result = dict(index)
    context._cache["battery_service_index"] = result
    return result


def _build_area_buses_index(context: PluginContext) -> dict[str, list[Any]]:
    """Map area_name -> list of ACBus components in that area."""
    cached = context._cache.get("area_buses_index")
    if cached is not None:
        return cached
    index: dict[str, list[Any]] = defaultdict(list)
    for bus in _source_system(context).get_components(ACBus):
        area = getattr(bus, "area", None)
        if area is None:
            continue
        area_name = getattr(area, "name", None)
        if area_name:
            index[area_name].append(bus)
        arname = (getattr(area, "ext", None) or {}).get("ARNAME")
        if arname and str(arname) != area_name:
            index[str(arname)].append(bus)
    result = dict(index)
    context._cache["area_buses_index"] = result
    return result


def _build_node_name_index(context: PluginContext) -> dict[str, Any]:
    """Build name->PLEXOSNode index once and cache it."""
    cached = context._cache.get("node_name_index")
    if cached is not None:
        return cached
    result = {node.name: node for node in _target_system(context).get_components(PLEXOSNode)}
    context._cache["node_name_index"] = result
    return result


def _build_bus_name_index(context: PluginContext) -> dict[str, Any]:
    """Build name->ACBus index once and cache it."""
    cached = context._cache.get("bus_name_index")
    if cached is not None:
        return cached
    result = {bus.name: bus for bus in _source_system(context).get_components(ACBus)}
    context._cache["bus_name_index"] = result
    return result


def _build_area_to_node_index(context: PluginContext) -> dict[str, PLEXOSNode]:
    """Build area_name->PLEXOSNode index once and cache it.

    Replaces _lookup_target_node_by_source_area which was O(nodes*buses) per call.
    """
    cached = context._cache.get("area_to_node_index")
    if cached is not None:
        return cached

    bus_name_index = _build_bus_name_index(context)
    node_name_index = _build_node_name_index(context)

    index: dict[str, PLEXOSNode] = {}
    for node_name, node in node_name_index.items():
        source_bus = bus_name_index.get(node_name)
        if source_bus is None:
            continue
        bus_area = getattr(source_bus, "area", None)
        if isinstance(bus_area, Area):
            index[bus_area.name] = node
            arname = (getattr(bus_area, "ext", None) or {}).get("ARNAME")
            if arname:
                index[str(arname)] = node
        elif isinstance(bus_area, str):
            index[bus_area] = node

    context._cache["area_to_node_index"] = index
    return index


def _lookup_target_node_by_name(context: PluginContext, node_name: str) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node with the given name."""
    index = _build_node_name_index(context)
    node = index.get(node_name)
    if node is None:
        return Err(ValueError(f"No PLEXOSNode found with name '{node_name}'"))
    return Ok(node)


def _lookup_target_node_by_source_area(
    context: PluginContext, area_name: str
) -> Result[PLEXOSNode, ValueError]:
    """Return the translated node whose source ACBus has matching area name."""
    index = _build_area_to_node_index(context)
    node = index.get(area_name)
    if node is None:
        return Err(ValueError(f"No PLEXOSNode found with source area '{area_name}'"))
    return Ok(node)


def _lookup_source_generator(context: PluginContext, gen_name: str) -> Any | None:
    """Find a source generator by name across all Sienna generator types."""
    cache_key = "source_generator_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        display_index = _build_generator_display_name_index(context)
        by_orig: dict[str, Any] = {}
        by_display: dict[str, Any] = {}
        for gen_type in SOURCE_GENERATOR_TYPES:
            for gen in _source_system(context).get_components(gen_type):
                by_orig[gen.name] = gen
                if isinstance(gen, HydroReservoir):
                    continue
                display_name = display_index.get(gen.name)
                if display_name:
                    by_display.setdefault(display_name, gen)
        index = {**by_orig, **by_display}
        context._cache[cache_key] = index
    return index.get(gen_name)


def _build_generator_display_name_index(context: PluginContext) -> dict[str, str]:
    """Map each source generator's original name -> final display name.

    Priority:
    1. ext["unit_name"] — used as-is, deduplicated when shared
    2. ext["plant_name"] — deduplicated with _1, _2, ... suffixes when shared
    3. original component name — same dedup logic as plant_name
    """
    cached = context._cache.get("generator_display_name_index")
    if cached is not None:
        return cached

    result: dict[str, str] = {}
    needs_dedup: list[tuple[str, str]] = []

    for gen_type in SOURCE_GENERATOR_TYPES:
        for gen in _source_system(context).get_components(gen_type):
            orig = gen.name
            ext = getattr(gen, "ext", None)
            ext_dict = ext if isinstance(ext, dict) else {}

            unit_name = ext_dict.get("unit_name")
            if unit_name:
                result[orig] = str(unit_name)
            else:
                plant_name = ext_dict.get("plant_name")
                display = str(plant_name) if plant_name else orig
                needs_dedup.append((orig, display))

    groups: dict[str, list[str]] = defaultdict(list)
    for orig, display in needs_dedup:
        groups[display].append(orig)

    for display, orig_names in groups.items():
        if len(orig_names) == 1:
            result[orig_names[0]] = display
        else:
            for i, orig in enumerate(sorted(orig_names), start=1):
                result[orig] = f"{display}_{i}"

    # Detect collision where different original names ended up with the same display name
    # Renumber those with suffixes to ensure uniqueness, and log a warning
    display_to_origs: dict[str, list[str]] = defaultdict(list)
    for orig, display in result.items():
        display_to_origs[display].append(orig)

    for display, orig_names in display_to_origs.items():
        if len(orig_names) > 1:
            logger.warning(
                "Display name collision '{}' shared by {} source generators; renumbering.",
                display,
                len(orig_names),
            )
            for i, orig in enumerate(sorted(orig_names), start=1):
                result[orig] = f"{display}_{i}"

    context._cache["generator_display_name_index"] = result
    return result


def _lookup_source_battery(context: PluginContext, battery_name: str) -> Any | None:
    """Find a source battery by name."""
    cache_key = "source_battery_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        index = {b.name: b for b in _source_system(context).get_components(EnergyReservoirStorage)}
        context._cache[cache_key] = index
    return index.get(battery_name)


def _find_source_line(context: PluginContext, line_name: str) -> Any | None:
    """Find a source line by name across Line, MonitoredLine, and TwoTerminalHVDCLine types."""
    cache_key = "source_line_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        index = {}
        for line_type in SOURCE_LINE_TYPES:
            for ln in _source_system(context).get_components(line_type):
                index[ln.name] = ln
        context._cache[cache_key] = index
    return index.get(line_name)


def _find_source_transformer(context: PluginContext, transformer_name: str) -> Any | None:
    """Find a source transformer by name."""
    cache_key = "source_transformer_name_index"
    index = context._cache.get(cache_key)
    if index is None:
        index = {}
        for tf_type in [Transformer2W, TapTransformer, PhaseShiftingTransformer]:
            for tf in _source_system(context).get_components(tf_type):
                index[tf.name] = tf
        context._cache[cache_key] = index
    return index.get(transformer_name)


def _get_time_limit(component: Any, attr: str, ext_key: str | None) -> float | None:
    """Extract time limit from time_limits attribute or ext dict."""
    time_limits = getattr(component, "time_limits", None)
    if isinstance(time_limits, dict):
        value = time_limits.get(attr)
    else:
        value = getattr(time_limits, attr, None) if time_limits else None

    if value is None:
        ext = getattr(component, "ext", None)
        if ext is not None and isinstance(ext, dict):
            value = ext.get(ext_key)

    return _convert_time_value(value)


def _ramp_value_to_float(source_component: object, raw_value: Any) -> float:
    """Convert ramp value to MW/min.

    In practice, source ramp limits can appear either as:
    - per-unit/min values (typically <= 1.0), or
    - already absolute MW/min values.

    Use a simple heuristic: scale moderate magnitudes (<= 10.0) by base power,
    otherwise treat the value as already in MW/min.
    """
    magnitude = get_magnitude(raw_value)
    if magnitude is None and isinstance(raw_value, int | float):
        magnitude = raw_value
    if magnitude is None:
        return 0.0

    value = float(magnitude)
    if abs(value) <= 10.0:
        return value * resolve_base_power(source_component)
    return value


def _get_ramp_limit_value(source_component: object, *, default: Any, direction: str) -> float:
    """Extract raw ramp limit value for a given direction.

    Handles both dict-style and attribute-style (e.g. UpDown) ramp_limits objects.
    """
    ramp_limits = getattr(source_component, "ramp_limits", default)
    if not ramp_limits:
        return 0.0
    if isinstance(ramp_limits, dict):
        raw_value = ramp_limits.get(direction, 0.0)
    else:
        raw_value = getattr(ramp_limits, direction, 0.0)
    return float(raw_value)


def _resolve_ramp_rates(
    source_component: object,
    context: PluginContext,
    *,
    initial_ramp_mw: float,
    defaults_key: str,
) -> float:
    """Apply defaults/fallback/capping logic and return final non-negative ramp.

    Logic (in order):
    1. If the raw ramp is below the usability threshold, replace it with
       ``gen_ramp_pct * max_mw`` from PCM defaults.
    2. If the raw ramp (or the defaults-derived value) *exceeds* max_mw, it is
       physically impossible → replace with ``gen_ramp_pct * max_mw`` from PCM
       defaults.  If that is still > max_mw, cap at max_mw.
    3. If the fallback is still below threshold after both passes (e.g. defaults
       capacity also missing), the value stays as-is (floor of 0.0 at the end).
    """
    ramp_mw = initial_ramp_mw
    category = _resolve_generator_category(source_component, context)
    gen_ramp_pct = _get_defaults(category, defaults_key)
    # When the primary percentage key is unset (0.0), fall back to ramp_rate.
    if math.isclose(gen_ramp_pct, 0.0, abs_tol=1e-9):
        gen_ramp_pct = _get_defaults(category, "ramp_rate")
    # Last resort: general default for categories with no ramp_rate entry.
    if math.isclose(gen_ramp_pct, 0.0, abs_tol=1e-9):
        gen_ramp_pct = _get_general_default("default_ramp_rate")
    max_pu = _get_minmax_value(getattr(source_component, "active_power_limits", None), "max") or 0.0
    max_mw = abs(max_pu) * resolve_base_power(source_component)
    # Ignore sentinel / placeholder max-capacity values (e.g. 1e30 in some data sources).
    if max_mw > 1e10:
        max_mw = 0.0
    if max_mw == 0.0:
        max_mw = _get_defaults(category, "capacity_MW")

    # --- Step 1: raw ramp below usability threshold → use PCM defaults ---
    if ramp_mw < RAMPING_THRESHOLD:
        ramp_mw = gen_ramp_pct * max_mw
        if ramp_mw < RAMPING_THRESHOLD:
            max_mw = _get_defaults(category, "capacity_MW")
            ramp_mw = gen_ramp_pct * max_mw

    # --- Step 2: ramp exceeds max capacity → physically impossible, use defaults ---
    if max_mw > 0.0 and ramp_mw > max_mw:
        default_ramp_mw = gen_ramp_pct * max_mw
        ramp_mw = min(default_ramp_mw, max_mw)

    return max(0.0, round(ramp_mw, 4))


def _convert_time_value(value: Any) -> float | None:
    """Convert a time value to float hours, handling different formats."""
    if value is None:
        return None
    magnitude = get_magnitude(value)
    return float(magnitude) if magnitude is not None else None


def _get_minmax_value(obj: Any, key: str) -> float | None:
    """Extract min or max value from a MinMax-like object or dict."""
    if obj is None:
        return None
    val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    if val is None:
        return None
    magnitude = get_magnitude(val)
    if magnitude is not None:
        return float(magnitude)
    return float(val) if isinstance(val, int | float) else None


def _get_defaults(category: str | None, key: str) -> float:
    """Extract a default value from defaults.json for the given category and key."""
    defaults = _load_defaults_json()
    value = defaults.get("reeds_defaults", {}).get(category, {}).get(key, 0.0) if category else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _attach_generator_time_series(
    context: PluginContext,
    generator_name: str,
    target_generator: Any,
) -> None:
    """Attach time series from source generator to translated PLEXOS generator."""
    source_gen = _lookup_source_generator(context, generator_name)
    if source_gen is None:
        logger.debug("No source generator found for '{}', skipping time series attachment.", generator_name)
        return

    if isinstance(source_gen, HydroReservoir):
        return

    if not _source_system(context).time_series.has_time_series(source_gen):
        return

    import numpy as np
    from infrasys import SingleTimeSeries

    for metadata in _source_system(context).time_series.list_time_series_metadata(source_gen):
        ts_list = _source_system(context).list_time_series(
            source_gen, name=metadata.name, **metadata.features
        )
        if not ts_list:
            logger.warning("Missing time series {} for generator {}", metadata.name, generator_name)
            continue

        ts = ts_list[0]
        if not _target_system(context).has_time_series(
            target_generator, name=ts.name, time_series_type=SingleTimeSeries, **metadata.features
        ):
            data = np.asarray(ts.data)
            output_resolution = ts.resolution

            if ts.name == "hydro_budget":
                # ts.data holds raw per-unit values; scale to actual MW (same logic as
                # max_active_power TS) so that weekly sums are in MWh, not dimensionless
                # units.  Without this, the weekly budget is ~max_active_power-factor too
                # large (e.g. 955 MWh instead of 76 MWh for an 0.08 MW generator).
                _max_mw = 0.0
                _limits = getattr(source_gen, "active_power_limits", None)
                if _limits is not None:
                    _max_val = (
                        _limits.get("max") if isinstance(_limits, dict) else getattr(_limits, "max", None)
                    )
                    if _max_val is not None:
                        _mag = get_magnitude(_max_val)
                        _raw = (
                            float(_mag)
                            if _mag is not None
                            else float(_max_val)
                            if isinstance(_max_val, int | float)
                            else None
                        )
                        if _raw is not None:
                            _max_mw = abs(_raw) * resolve_base_power(source_gen)
                if _max_mw > 0.0:
                    data = data * _max_mw

            if (
                ts.name == "hydro_budget"
                and isinstance(ts.resolution, timedelta)
                and ts.resolution < timedelta(days=7)
            ):
                seconds_per_step = ts.resolution.total_seconds()
                if seconds_per_step > 0:
                    points_per_week = max(int(round((7 * 86400) / seconds_per_step)), 1)
                    full_weeks = data.size // points_per_week
                    weekly_values: list[float] = []
                    if full_weeks:
                        weekly_values.extend(
                            data[: full_weeks * points_per_week]
                            .reshape(full_weeks, points_per_week)
                            .sum(axis=1)
                            .tolist()
                        )
                    remainder = data[full_weeks * points_per_week :]
                    if remainder.size:
                        weekly_values.append(float(remainder.sum()))

                    # SingleTimeSeries requires at least two points.
                    if len(weekly_values) >= 2:
                        data = np.asarray(weekly_values, dtype=float)
                        output_resolution = timedelta(days=7)

            if ts.name == "max_active_power":
                max_mw = 0.0
                limits = getattr(source_gen, "active_power_limits", None)
                if limits is not None:
                    max_val = limits.get("max") if isinstance(limits, dict) else getattr(limits, "max", None)
                    if max_val is not None:
                        mag = get_magnitude(max_val)
                        raw = (
                            float(mag)
                            if mag is not None
                            else float(max_val)
                            if isinstance(max_val, int | float)
                            else None
                        )
                        if raw is not None:
                            max_mw = abs(raw) * resolve_base_power(source_gen)
                else:
                    # active_power_limits absent (e.g. RenewableDispatch) — use rating
                    rating = getattr(source_gen, "rating", None)
                    if rating is not None:
                        mag = get_magnitude(rating)
                        raw = (
                            float(mag)
                            if mag is not None
                            else float(rating)
                            if isinstance(rating, int | float)
                            else None
                        )
                        if raw is not None:
                            max_mw = abs(raw) * resolve_base_power(source_gen)
                if max_mw > 0.0:
                    data = data * max_mw
            fresh_ts = SingleTimeSeries.from_array(
                data=data,
                name=ts.name,
                initial_timestamp=ts.initial_timestamp,
                resolution=output_resolution,
            )
            _target_system(context).add_time_series(fresh_ts, target_generator, **metadata.features)
            logger.debug("Attached time series {} to generator {}", ts.name, generator_name)


def _has_usable_generator_time_series(source_component: object, context: PluginContext) -> bool:
    """Return True when the source generator has at least one registered time series.

    Checks only metadata (no data reads) to keep this O(1) per generator on
    large nodal systems where reading Arrow data for every renewable unit was the
    dominant cost.
    """
    source_system = _source_system(context)
    try:
        if not source_system.time_series.has_time_series(source_component):
            return False
        metadata_items = source_system.time_series.list_time_series_metadata(source_component)
        return bool(metadata_items)
    except Exception:
        # If introspection fails, avoid accidentally deactivating the unit.
        return True


def _attach_region_node_load_time_series(
    context: PluginContext,
    region_name: str,
    node: PLEXOSNode,
    region_component: Any | None,
) -> None:
    """Aggregate load time series from all loads in the region and attach to the region's node in PLEXOS."""
    if region_component is None:
        return

    import numpy as np
    from infrasys import SingleTimeSeries

    target_system = cast(Any, context.target_system)
    # Early exit: this getter is invoked from both membership_region_parent_node and
    # membership_region_child_node, so it is called twice per region. Skip the entire
    # aggregation loop on the second call.
    if target_system.has_time_series(region_component, name="load", time_series_type=SingleTimeSeries):
        return

    source_system = cast(Any, context.source_system)
    area_buses_index = _build_area_buses_index(context)
    buses_in_region = area_buses_index.get(region_name, [])
    if not buses_in_region:
        logger.debug("No buses found in region {}", region_name)
        return

    bus_loads_index = _build_bus_to_loads_index(context)
    all_loads = [load for bus in buses_in_region for load in bus_loads_index.get(str(bus.uuid), [])]
    if not all_loads:
        logger.debug("No loads found for region {}", region_name)
        return

    aggregated_data: Any = None
    initial_ts: Any = None
    for load in all_loads:
        if source_system.time_series.has_time_series(load):
            for ts in source_system.list_time_series(load):
                if ts.name == "max_active_power":
                    load_mw = _get_load_mw(load)
                    data = np.asarray(ts.data, dtype=float)
                    if load_mw > 0.0:
                        data = data * load_mw
                    if aggregated_data is None:
                        aggregated_data = data.copy()
                        initial_ts = ts
                    else:
                        aggregated_data += data
                    break

    if aggregated_data is not None and initial_ts is not None:
        fresh_ts = SingleTimeSeries.from_array(
            data=aggregated_data,
            name="load",
            initial_timestamp=initial_ts.initial_timestamp,
            resolution=initial_ts.resolution,
        )
        target_system.add_time_series(fresh_ts, region_component)


def _build_bus_to_loads_index(context: PluginContext) -> dict[str, list[Any]]:
    """Build bus_uuid to list of all Load components (StandardLoad and PowerLoad) connected to that bus, cached."""
    cached = context._cache.get("bus_to_loads")
    if cached is not None:
        return cached

    source_system = cast(Any, context.source_system)
    index: dict[str, list[Any]] = defaultdict(list)
    for load in source_system.get_components(StandardLoad):
        bus = getattr(load, "bus", None)
        if bus is not None:
            index[str(bus.uuid)].append(load)
    for load in source_system.get_components(PowerLoad):
        bus = getattr(load, "bus", None)
        if bus is not None:
            index[str(bus.uuid)].append(load)

    result = dict(index)
    context._cache["bus_to_loads"] = result
    return result


def _build_bus_to_standard_loads_index(context: PluginContext) -> dict[str, list[Any]]:
    """Build bus_uuid to list of StandardLoad components connected to that bus, cached."""
    cached = context._cache.get("bus_to_standard_loads")
    if cached is not None:
        return cached

    source_system = cast(Any, context.source_system)
    index: dict[str, list[Any]] = defaultdict(list)
    for load in source_system.get_components(StandardLoad):
        bus = getattr(load, "bus", None)
        if bus is not None:
            index[str(bus.uuid)].append(load)

    result = dict(index)
    context._cache["bus_to_standard_loads"] = result
    return result


def _build_3w_transformer_name_index(context: PluginContext) -> dict[str, Any]:
    """Build Transformer3W / PhaseShiftingTransformer3W names index, cached."""
    cached = context._cache.get("source_3w_transformer_name_index")
    if cached is not None:
        return cached
    source_system = cast(Any, context.source_system)
    index: dict[str, Any] = {}
    for tf_type in [Transformer3W, PhaseShiftingTransformer3W]:
        for tf in source_system.get_components(tf_type):
            index[tf.name] = tf
    context._cache["source_3w_transformer_name_index"] = index
    return index


def _find_3w_source_transformer(context: PluginContext, arm_name: str) -> tuple[Any, str] | None:
    """Given an arm name like 'TRANSFORMER_primary', return (transformer3w, arm) or None."""
    for arm in ("primary", "secondary", "tertiary"):
        suffix = f"_{arm}"
        if arm_name.endswith(suffix):
            base_name = arm_name[: -len(suffix)]
            tf = _build_3w_transformer_name_index(context).get(base_name)
            if tf is not None:
                return tf, arm
    return None


def _coerce_scalar(value: Any) -> float | None:
    """Convert numeric-like values to float without forcing unit-stripped conversion."""
    if isinstance(value, int | float):
        return float(value)
    magnitude = getattr(value, "magnitude", None)
    if isinstance(magnitude, int | float):
        return float(magnitude)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _power_quantity_to_mw(value: Any) -> float | None:
    """Convert unit-bearing power quantity to MW when possible."""
    if value is None or not hasattr(value, "to"):
        return None

    conversion_targets: tuple[tuple[str, float], ...] = (
        ("megawatt", 1.0),
        ("MW", 1.0),
        ("megavolt_ampere", 1.0),
        ("MVA", 1.0),
        ("watt", 1e-6),
        ("volt_ampere", 1e-6),
        ("VA", 1e-6),
    )
    for unit_name, scale in conversion_targets:
        try:
            converted = value.to(unit_name)
        except Exception:
            continue

        converted_magnitude = _coerce_scalar(getattr(converted, "magnitude", converted))
        if converted_magnitude is not None:
            return float(converted_magnitude) * scale

    return None


def _get_load_base_power(load: Any) -> float:
    """Resolve load base power as scalar MW/MVA-like value with robust defaults."""
    base_power = getattr(load, "base_power", None)
    if base_power is None:
        return 100.0

    base_power_from_quantity = _power_quantity_to_mw(base_power)
    if base_power_from_quantity is not None:
        return base_power_from_quantity

    coerced = _coerce_scalar(base_power)
    return coerced if coerced is not None else 100.0


def _get_load_mw(load: Any) -> float:
    """Extract MW value from a StandardLoad or PowerLoad for LPF computation."""
    raw_max_active_power = getattr(load, "max_active_power", None)
    base_power = _get_load_base_power(load)

    direct_power_mw = _power_quantity_to_mw(raw_max_active_power)
    if direct_power_mw is not None:
        return direct_power_mw

    magnitude = get_magnitude(raw_max_active_power)

    magnitude_power_mw = _power_quantity_to_mw(magnitude)
    if magnitude_power_mw is not None:
        return magnitude_power_mw

    magnitude_value = _coerce_scalar(magnitude)
    if magnitude_value is not None:
        return float(magnitude_value) * float(base_power)

    for attr in ("max_constant_active_power", "constant_active_power"):
        val = getattr(load, attr, None)
        direct_attr_power_mw = _power_quantity_to_mw(val)
        if direct_attr_power_mw is not None:
            return direct_attr_power_mw

        val_scalar = _coerce_scalar(val)
        if val_scalar is not None and val_scalar > 0:
            return float(val_scalar) * float(base_power)
    return 0.0


def _compute_total_system_load(context: PluginContext) -> float:
    """Compute total system load in MW by summing max_active_power of all StandardLoad and PowerLoad components."""
    cached = context._cache.get("total_system_load")
    if cached is not None:
        return cached
    source_system = cast(Any, context.source_system)
    total = 0.0
    for load_type in [StandardLoad, PowerLoad]:
        for load in source_system.get_components(load_type):
            total += _get_load_mw(load)
    context._cache["total_system_load"] = total
    return total


def _build_area_total_load_index(context: PluginContext) -> dict[str, float]:
    """Map area_name (ARNAME or area.name) -> total load MW for all buses in that area."""
    cached = context._cache.get("area_total_load_index")
    if cached is not None:
        return cached
    area_buses = _build_area_buses_index(context)
    loads_index = _build_bus_to_loads_index(context)
    result: dict[str, float] = {}
    for area_name, buses in area_buses.items():
        total = sum(_get_load_mw(load) for bus in buses for load in loads_index.get(str(bus.uuid), []))
        result[area_name] = total
    context._cache["area_total_load_index"] = result
    return result


def _get_system_base_power(context: PluginContext) -> float:
    """Extract system base power from source_system.base_power or default to 100 MVA."""
    value = getattr(getattr(context, "source_system", None), "base_power", None)
    try:
        return float(value) if value is not None else 100.0
    except (TypeError, ValueError):
        return 100.0


def _get_general_default(key: str) -> float:
    """Extract a general default value from defaults.json for the given key."""
    defaults = _load_defaults_json()
    value = defaults.get("general_defaults", {}).get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@getter
def get_component_ext(source_component: object, context: PluginContext) -> Result[dict, ValueError]:
    """Store the Sienna source type name in ext for downstream use (e.g. time series file naming).

    Also stores ``description`` (prime_mover + fuel) in ext so the r2x_plexos
    exporter can write it to the ``t_object.description`` column in the output XML.
    """
    ext: dict[str, Any] = {"sienna_type": type(source_component).__name__}

    desc_getter = cast(Any, get_generator_description)
    desc_result = desc_getter(source_component, context)
    if hasattr(desc_result, "unwrap"):
        try:
            desc = desc_result.unwrap()
            if desc is not None:
                ext["description"] = desc
        except Exception:
            pass

    # Fallback: if no prime_mover/fuel description, use the resolved category (e.g. "biopower",
    # "natural-gas") so that t_object.description is never left empty for generators.
    if "description" not in ext:
        category = _resolve_generator_category(source_component, context)
        if category is not None:
            ext["description"] = category

    return Ok(ext)


@getter
def get_region_ext(source_component: Area, context: PluginContext) -> Result[dict, ValueError]:
    """Return ext with sienna_type and ISO/RTO description for the region."""
    area_name = getattr(source_component, "name", "")
    ext_dict = getattr(source_component, "ext", None)
    if isinstance(ext_dict, dict):
        arname = ext_dict.get("ARNAME")
        if arname:
            area_name = str(arname)

    area_buses_index = _build_area_buses_index(context)
    bus_loads_index = _build_bus_to_loads_index(context)

    sienna_type = "StandardLoad"
    for bus in area_buses_index.get(area_name, []):
        for load in bus_loads_index.get(str(bus.uuid), []):
            sienna_type = type(load).__name__
            break
        if sienna_type != "StandardLoad":
            break
    else:
        source_system = cast(Any, context.source_system)
        for _ in source_system.get_components(StandardLoad):
            sienna_type = "StandardLoad"
            break
        else:
            for _ in source_system.get_components(PowerLoad):
                sienna_type = "PowerLoad"
                break

    region_buses = area_buses_index.get(area_name, [])
    iso_rto = _resolve_iso_rto_for_buses(region_buses, context)

    result: dict[str, Any] = {"sienna_type": sienna_type}
    if iso_rto:
        result["description"] = iso_rto
    return Ok(result)


@getter
def get_availability(source_component: ACBus, context: PluginContext) -> Result[int, ValueError]:
    """Populate available field with units count from ACBus.

    Extracts the units attribute from ACBus and converts to int.
    Returns 1 if units attribute is not present.
    """
    units = getattr(source_component, "units", None)
    if units is None:
        return Ok(1)
    return Ok(int(units))


@getter
def get_voltage_kv(source_component: ACBus, context: PluginContext) -> Result[float, ValueError]:
    """Extract AC voltage magnitude from base_voltage Quantity."""
    value = get_magnitude(source_component.base_voltage)
    return Ok(round(float(value), 1) if value is not None else 0.0)


@getter
def get_node_category(source_component: ACBus, context: PluginContext) -> Result[str, ValueError]:
    """Return the Area name for the bus, since Area maps to PLEXOSRegion."""
    area = getattr(source_component, "area", None)
    if area is not None:
        ext = getattr(area, "ext", None)
        arname = (ext or {}).get("ARNAME") if isinstance(ext, dict) else None
        area_name = str(arname) if arname else str(area.name) if isinstance(area, Area) else str(area)
        if area_name:
            return Ok(area_name)
    return Err(ValueError(f"No area found for ACBus '{source_component.name}'"))


@getter
def get_load_participation_factor(
    source_component: ACBus,
    context: PluginContext,
) -> Result[float, ValueError]:
    """Extract load participation factor from StandardLoads connected to the bus.

    Priority:
    1. ext["MMWG_LPF"] or ext["ReEDS_LPF"] on connected StandardLoads
    2. Computed as node_load_MW / total_system_load_MW
    """

    # format LPF with scientific notation if very small, otherwise round to 4 decimals
    def format_lpf(val: float) -> float:
        """Format the LPF value with scientific notation if it's very small, otherwise round to 4 decimal places."""
        if abs(val) < 1e-4 and val != 0.0:
            return float(f"{val:.4e}")
        return round(val, 4)

    bus_uuid_str = str(source_component.uuid)
    index = _build_bus_to_standard_loads_index(context)
    node_lpf_total = 0.0
    for load in index.get(bus_uuid_str, []):
        if hasattr(load, "ext") and isinstance(load.ext, dict):
            lpf = load.ext.get("MMWG_LPF") or load.ext.get("ReEDS_LPF", 0)
            if isinstance(lpf, int | float):
                node_lpf_total += float(lpf)

    if node_lpf_total > 0.0:
        return Ok(format_lpf(node_lpf_total))

    # compute LPF as node_load_MW / region_total_load_MW (nodes in each region must sum to 1.0)
    area = getattr(source_component, "area", None)
    area_key: str | None = None
    if area is not None:
        ext = getattr(area, "ext", None)
        arname = (ext or {}).get("ARNAME") if isinstance(ext, dict) else None
        area_key = str(arname) if arname else str(area.name)

    all_loads_index = _build_bus_to_loads_index(context)
    node_load = sum(_get_load_mw(load) for load in all_loads_index.get(bus_uuid_str, []))
    area_total_load_index = _build_area_total_load_index(context)
    region_load = area_total_load_index.get(area_key, 0.0) if area_key else 0.0
    if region_load > 0.0:
        return Ok(format_lpf(node_load / region_load))

    return Ok(0.0)


@getter
def is_slack_bus(source_component: ACBus, context: PluginContext) -> Result[int, ValueError]:
    """Populate bustype field based on slack bus status."""

    from r2x_sienna.models.enums import ACBusTypes

    value = 1 if source_component.bustype == ACBusTypes.SLACK else 0
    return Ok(value)


@getter
def get_area_units(source_component: Area, context: PluginContext) -> Result[float, ValueError]:
    """Return region units (1 active, 0 inactive) based on regional LPF viability.

    Regions are deactivated when the sum of node load participation factors is zero,
    which also covers regions with no effective load.
    """
    ext = getattr(source_component, "ext", None)
    arname = (ext or {}).get("ARNAME") if isinstance(ext, dict) else None
    area_name = str(arname) if arname else str(getattr(source_component, "name", ""))

    buses = _build_area_buses_index(context).get(area_name, [])
    if not buses:
        return Ok(0.0)

    lpf_sum = 0.0
    load_participation_getter = cast(Any, get_load_participation_factor)
    for bus in buses:
        result = load_participation_getter(bus, context)
        match result:
            case Ok(value):
                lpf_sum += float(value)
            case Err(_):
                continue

    return Ok(0.0 if math.isclose(lpf_sum, 0.0, rel_tol=0.0, abs_tol=1e-9) else 1.0)


@getter
def get_area_load(source_component: Area, context: PluginContext) -> Result[float, ValueError]:
    """
    This is zero by default, because it is a time series field (datafile).
    Supports both StandardLoad and PowerLoad.
    """
    return Ok(0.0)


@getter
def get_area_name(source_component: Area, context: PluginContext) -> Result[str, ValueError]:
    """Return ARNAME from ext if available, otherwise fall back to the component name."""
    ext = getattr(source_component, "ext", None)
    if isinstance(ext, dict):
        arname = ext.get("ARNAME")
        if arname:
            return Ok(str(arname))
    return Ok(getattr(source_component, "name", ""))


@getter
def get_zone_units(source_component: LoadZone, context: PluginContext) -> Result[float, ValueError]:
    """Return active status for translated zones."""
    return Ok(1.0)


def _build_zone_buses_index(context: PluginContext) -> dict[str, list[Any]]:
    """Map load_zone name -> list of ACBus components in that zone (cached)."""
    cached = context._cache.get("zone_buses_index")
    if cached is not None:
        return cached
    index: dict[str, list[Any]] = defaultdict(list)
    for bus in _source_system(context).get_components(ACBus):
        lz = getattr(bus, "load_zone", None)
        if lz is None:
            continue
        if isinstance(lz, LoadZone):
            lz_name = lz.name
        elif hasattr(lz, "name") and lz.name:
            lz_name = str(lz.name)
        else:
            lz_name = str(lz)
        index[lz_name].append(bus)
    result = dict(index)
    context._cache["zone_buses_index"] = result
    return result


@getter
def get_zone_category(source_component: LoadZone, context: PluginContext) -> Result[str, ValueError]:
    """Resolve the ISO/RTO region for a LoadZone and return it as the PLEXOSZone category.

    Uses geographic coordinates from each bus's supplemental GeographicInfo attribute
    to perform a point-in-polygon lookup against stored ISO/RTO boundary multipolygons.
    Falls back to 'zones' when no geographic data is available.
    """
    zone_name = getattr(source_component, "name", "")
    buses = _build_zone_buses_index(context).get(zone_name, [])
    iso_rto = _resolve_iso_rto_for_buses(buses, context)
    return Ok(iso_rto if iso_rto else "zones")


@getter
def get_line_min_flow(
    source_component: Line
    | MonitoredLine
    | DiscreteControlledACBranch
    | TwoTerminalGenericHVDCLine
    | TwoTerminalLCCLine
    | TwoTerminalVSCLine,
    context: PluginContext,
) -> Result[float | dict, ValueError]:
    """Extract line min flow as float from source component negative rating."""
    base_power = _get_system_base_power(context)
    min_flow = getattr(source_component, "rating", None)
    if min_flow is not None:
        magnitude = get_magnitude(min_flow)
        value = (
            float(magnitude)
            if magnitude is not None
            else float(min_flow)
            if isinstance(min_flow, int | float)
            else None
        )
        if value is not None:
            flow = float(-abs(value)) * base_power
            if abs(flow) > 99999.0:
                return Ok({"value": -99999.0, "memo": FLOW_CLIP_MEMO_TEXT})
            return Ok(flow)

    val = _get_minmax_value(getattr(source_component, "active_power_limits_to", None), "min")
    if val is not None:
        flow = float(val) * base_power
        if abs(flow) > 99999.0:
            return Ok({"value": -99999.0, "memo": FLOW_CLIP_MEMO_TEXT})
        return Ok(flow)

    return Ok({"value": -99999.0, "memo": FLOW_CLIP_MEMO_TEXT})


@getter
def get_line_max_flow(
    source_component: Line
    | MonitoredLine
    | DiscreteControlledACBranch
    | TwoTerminalGenericHVDCLine
    | TwoTerminalLCCLine
    | TwoTerminalVSCLine,
    context: PluginContext,
) -> Result[float | dict, ValueError]:
    """Extract line max flow as float from source component rating."""
    base_power = _get_system_base_power(context)
    max_flow = getattr(source_component, "rating", None)
    if max_flow is not None:
        magnitude = get_magnitude(max_flow)
        value = (
            float(magnitude)
            if magnitude is not None
            else float(max_flow)
            if isinstance(max_flow, int | float)
            else None
        )
        if value is not None:
            flow = float(abs(value)) * base_power
            if abs(flow) > 99999.0:
                return Ok({"value": 99999.0, "memo": FLOW_CLIP_MEMO_TEXT})
            return Ok(flow)

    val = _get_minmax_value(getattr(source_component, "active_power_limits_from", None), "max")
    if val is not None:
        flow = float(abs(val)) * base_power
        if abs(flow) > 99999.0:
            return Ok({"value": 99999.0, "memo": FLOW_CLIP_MEMO_TEXT})
        return Ok(flow)

    return Ok({"value": 99999.0, "memo": FLOW_CLIP_MEMO_TEXT})


@getter
def lines_loss_incremental(
    component: Line | MonitoredLine | TwoTerminalGenericHVDCLine | TwoTerminalLCCLine | TwoTerminalVSCLine,
    context: PluginContext,
) -> Result[float, ValueError]:
    """Return the incremental loss factor for the line. If not specified, return a default value."""
    losses = getattr(component, "loss", None)
    match losses:
        case None:
            return Ok(_get_general_default("ac_line_losses"))
        case int() | float() as val:
            return Ok(float(val))
        case _:
            # InputOutputCurve: extract proportional_term as incremental loss
            function_data = getattr(getattr(losses, "function_data", None), "proportional_term", None)
            return Ok(
                float(function_data) if function_data is not None else _get_general_default("ac_line_losses")
            )


@getter
def lines_wheeling_charge(line: Line | MonitoredLine, context: PluginContext) -> Result[float, ValueError]:
    """Return the wheeling charge for the forward direction (from_region to to_region).
    If not specified on the line, return a default value.
    """
    wc = getattr(line, "wheeling_charge", None)
    if wc is None:
        return Ok(_get_general_default("wheeling_charge"))
    return Ok(float(wc))


@getter
def lines_wheeling_charge_back(
    line: Line | MonitoredLine, context: PluginContext
) -> Result[float, ValueError]:
    """Return the wheeling charge for the reverse direction (to_region to from_region).
    If not specified on the line, return a default value.
    """
    wc_back = getattr(line, "wheeling_charge_back", None)
    if wc_back is None:
        return Ok(_get_general_default("wheeling_charge_back"))
    return Ok(float(wc_back))


@getter
def get_vsc_line_resistance(
    source_component: TwoTerminalVSCLine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract line resistance (1/g) from TwoTerminalVSCLine conductance."""
    g = getattr(source_component, "g", None)
    if g is None:
        return Ok(0.0)
    magnitude = get_magnitude(g)
    g_val = float(magnitude) if magnitude is not None else float(g) if isinstance(g, int | float) else None
    if g_val is None or g_val == 0.0:
        return Ok(0.0)
    return Ok(float(1.0 / g_val))


@getter
def get_transformer_susceptance(
    source_component: Transformer2W | TapTransformer | PhaseShiftingTransformer, context: PluginContext
) -> Result[float, ValueError]:
    """Extract susceptance (imaginary part) from transformer component's primary_shunt."""
    match source_component.primary_shunt:
        case None:
            return Err(ValueError("Transformer primary_shunt is None"))
        case complex() as val:
            return Ok(float(val.imag))
        case int() | float() as val:
            return Ok(float(val))
        case val:
            match get_magnitude(val):
                case complex() as mag:
                    return Ok(float(mag.imag))
                case dict() as mag:
                    imag_part = mag.get("imag")
                    if isinstance(imag_part, int | float):
                        return Ok(float(imag_part))
                    return Err(ValueError(f"Cannot extract imag from primary_shunt magnitude dict: {mag}"))
                case int() | float() as mag:
                    return Ok(float(mag))
                case mag:
                    imag_part = getattr(mag, "imag", None)
                    if imag_part is not None:
                        return Ok(float(imag_part))
                    return Err(ValueError(f"Cannot convert primary_shunt to float: {val}"))


@getter
def get_transformer_rating(
    source_component: Transformer2W | TapTransformer | PhaseShiftingTransformer, context: PluginContext
) -> Result[float, ValueError]:
    """Extract transformer rating as float from source component."""
    rating = getattr(source_component, "rating", None)
    if rating is None:
        return Ok(0.0)
    value = float(rating) if isinstance(rating, int | float) else None
    return Ok(round(float(value) * _get_system_base_power(context), 2) if value is not None else 0.0)


@getter
def get_3w_transformer_susceptance(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[float, ValueError]:
    """Read shunt susceptance from the global 'b' attribute of a 3W transformer."""
    b = getattr(source_component, "b", None)
    if b is None:
        return Ok(0.0)
    return Ok(float(b))


@getter
def get_3w_transformer_primary_name(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Return a name for the primary winding based on the source component's name."""
    return Ok(f"{source_component.name}_primary")


@getter
def get_3w_transformer_primary_uuid(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the primary winding based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_primary")))


@getter
def get_3w_transformer_primary_rating(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[float, ValueError]:
    """Extract primary winding rating (MVA) from ext['RATA1'], then rating_primary."""
    ext = getattr(source_component, "ext", None) or {}
    rata = ext.get("RATA1")
    if isinstance(rata, int | float) and rata > 0.0:
        return Ok(round(float(rata), 2))
    rating = getattr(source_component, "rating_primary", None)
    if rating is None:
        return Ok(99999.0)
    val = float(rating)
    return Ok(99999.0 if val >= 1e6 else round(abs(val), 2))


@getter
def get_3w_transformer_secondary_name(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Return a name for the secondary winding based on the source component's name."""
    return Ok(f"{source_component.name}_secondary")


@getter
def get_3w_transformer_secondary_uuid(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the secondary winding based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_secondary")))


@getter
def get_3w_transformer_secondary_rating(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[float, ValueError]:
    """Extract secondary winding rating (MVA) from ext['RATA2'], then rating_secondary."""
    ext = getattr(source_component, "ext", None) or {}
    rata = ext.get("RATA2")
    if isinstance(rata, int | float) and rata > 0.0:
        return Ok(round(float(rata), 2))
    rating = getattr(source_component, "rating_secondary", None)
    if rating is None:
        return Ok(0.0)
    val = float(rating)
    return Ok(99999.0 if val >= 1e6 else round(abs(val), 2))


@getter
def get_3w_transformer_tertiary_name(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Return a name for the tertiary winding based on the source component's name."""
    return Ok(f"{source_component.name}_tertiary")


@getter
def get_3w_transformer_tertiary_uuid(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the tertiary winding based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_tertiary")))


@getter
def get_3w_transformer_tertiary_rating(
    source_component: Transformer3W | PhaseShiftingTransformer3W, context: PluginContext
) -> Result[float, ValueError]:
    """Extract tertiary winding rating (MVA) from ext['RATA3'], then rating_tertiary."""
    ext = getattr(source_component, "ext", None) or {}
    rata = ext.get("RATA3")
    if isinstance(rata, int | float) and rata > 0.0:
        return Ok(round(float(rata), 2))
    rating = getattr(source_component, "rating_tertiary", None)
    if rating is None:
        return Ok(0.0)
    val = float(rating)
    return Ok(99999.0 if val >= 1e6 else round(abs(val), 2))


@getter
def get_generator_category(source_component: object, context: PluginContext) -> Result[str, ValueError]:
    """Determine generator category using ReEDS tech names, gen_type_string, and fuel/prime-mover mapping.

    Priority:
    1. ext["gen_type_string"] mapped through _GEN_TYPE_STRING_MAP
    2. ReEDS component name patterns (hydend, hyded, distpv, wind-ofs, etc.)
    3. ThermalStandard/ThermalMultiStart fuel via defaults.json reeds_thermal_mapping
    4. prime_mover + fuel via context.config.prime_mover_mapping (non-thermal fallback)
    5. prime_mover abbreviation via defaults.json prime_mover_types (non-thermal fallback)
    6. Err -> rule default applies
    """
    category = _resolve_generator_category(source_component, context)
    if category is not None:
        return Ok(category)
    return Err(ValueError("Cannot resolve generator category; rule default will apply"))


@getter
def get_generator_description(
    source_component: object, context: PluginContext
) -> Result[str | None, ValueError]:
    """Build a description string for any generator.

    Priority:
    1. prime_mover_type + fuel → "prime_mover: CC, fuel_type: NATURAL_GAS"
    2. Resolved category → "biopower", "hydro", "upv", etc.
    3. None when neither is available (non-generator components).
    """
    parts = []
    prime_mover = getattr(source_component, "prime_mover_type", None)
    if prime_mover is not None:
        pm_str = prime_mover.name if hasattr(prime_mover, "name") else str(prime_mover)
        parts.append(f"prime_mover: {pm_str}")
    fuel = getattr(source_component, "fuel", None)
    if fuel is not None:
        fuel_str = fuel.name if hasattr(fuel, "name") else str(fuel)
        parts.append(f"fuel_type: {fuel_str}")
    if parts:
        return Ok(", ".join(parts))
    # Fallback: use resolved category so every generator gets a non-empty description.
    category = _resolve_generator_category(source_component, context)
    if category is not None:
        return Ok(category)
    return Ok(None)


@getter
def get_pumped_hydro_category(
    source_component: HydroTurbine | HydroPumpTurbine, context: PluginContext
) -> Result[str, ValueError]:
    """Resolve category for hydro turbines, demoting zero-pump-load units to ``hydro``.

    Sienna ``HydroTurbine``/``HydroPumpTurbine`` components default to a pumped
    category, but units whose pump-load (derived from ``rating``) resolves to
    zero are not actually pumped storage and should land in the regular
    ``hydro`` category. When the pump load is non-zero we defer to the standard
    category resolution chain so explicit overrides (e.g. ``gen_type_string``)
    still apply, and otherwise let the rule default apply via ``Err``.
    """
    rating = getattr(source_component, "rating", None)
    pump_load_mw = 0.0
    if rating is not None:
        magnitude = get_magnitude(rating)
        if magnitude is not None:
            pump_load_mw = abs(float(magnitude) * resolve_base_power(source_component))

    if math.isclose(pump_load_mw, 0.0, abs_tol=1e-9):
        return Ok("hydro")

    category = _resolve_generator_category(source_component, context)
    if category is not None:
        return Ok(category)
    return Err(ValueError("Cannot resolve generator category; rule default will apply"))


@getter
def get_fuel_price(
    source_component: ThermalStandard | ThermalMultiStart, context: PluginContext
) -> Result[float, ValueError]:
    """Extract fuel price in $/GJ from fuel_cost attribute of FuelCurve, if available."""
    cost = getattr(source_component, "operation_cost", None)
    variable = None
    if cost is not None:
        if isinstance(cost, Mapping):
            variable = cost.get("variable")
        if variable is None:
            variable = getattr(cost, "variable", None)

    if isinstance(variable, Mapping):
        price = variable.get("fuel_cost")
        if price is not None:
            return Ok(round(float(price), 2))
    elif isinstance(variable, FuelCurve):
        price = getattr(variable, "fuel_cost", None)
        if price is not None:
            return Ok(round(float(price), 2))
    return Ok(0.0)


def _is_available(source_component: Any) -> bool:
    """Return False only when the component explicitly sets available=False."""
    available = getattr(source_component, "available", None)
    return available is not False


@getter
def get_thermal_generator_units(
    source_component: ThermalStandard | ThermalMultiStart, context: PluginContext
) -> Result[int, ValueError]:
    """Return thermal generator online status.

    Thermal units in Sienna inputs can express cost with different combinations
    of fuel price and heat-rate terms. Evaluate the full signal (heat rate,
    heat rate base/increment terms, fuel price, and start cost) before deciding
    whether a unit has usable economic metadata.

    Generators default to online unless an explicit source ``units`` flag
    disables them, or a known data-fix exception applies.
    """
    if not _is_available(source_component):
        return Ok(0)

    ext = getattr(source_component, "ext", None)
    if isinstance(ext, dict):
        plant_name = str(ext.get("plant_name", "")).strip().lower()
        state = str(ext.get("state", "")).strip().upper()
        # Explicitly deactivate the known mismapped TX "Monticello" units.
        if plant_name == "monticello" and state == "TX":
            return Ok(0)

    source_units = getattr(source_component, "units", None)
    if source_units is not None:
        try:
            return Ok(1 if int(source_units) > 0 else 0)
        except (TypeError, ValueError):
            pass

    # Consider all heat-rate components, not just heat_rate.
    fuel_price_getter = cast(Any, get_fuel_price)
    start_cost_getter = cast(Any, get_generator_start_cost)

    def _non_zero(value: Any) -> bool:
        try:
            return not math.isclose(float(value), 0.0, rel_tol=0.0, abs_tol=1e-9)
        except (TypeError, ValueError):
            return False

    fuel_price = 0.0
    start_cost = 0.0
    match fuel_price_getter(source_component, context):
        case Ok(value):
            fuel_price = float(value)
        case Err(_):
            fuel_price = 0.0
    match start_cost_getter(source_component, context):
        case Ok(value):
            start_cost = float(value)
        case Err(_):
            start_cost = 0.0

    heat_data = compute_heat_rate_data(source_component)
    has_heat_signal = any(
        _non_zero(heat_data.get(key))
        for key in ("heat_rate", "heat_rate_base", "heat_rate_incr", "heat_rate_incr2", "heat_rate_incr3")
    )

    # If any economic signal exists, keep thermal online.
    if _non_zero(fuel_price) or _non_zero(start_cost) or has_heat_signal:
        return Ok(1)

    return Ok(1)


@getter
def get_dispatch_generator_units(
    source_component: RenewableDispatch | RenewableNonDispatch,
    context: PluginContext,
) -> Result[int, ValueError]:
    """Deactivate renewable dispatch generators that do not have source time series."""
    if not _is_available(source_component):
        return Ok(0)
    return Ok(1 if _has_usable_generator_time_series(source_component, context) else 0)


@getter
def get_hydro_generator_units(
    source_component: HydroDispatch,
    context: PluginContext,
) -> Result[int, ValueError]:
    """Keep dispatch hydro generators online by default.

    Applies to ``HydroDispatch`` and ``HydroEnergyReservoir`` source types.
    Source ``units`` flags in Sienna data encode build counts, not operational
    enablement, so these should not be deactivated from that field.
    """
    if not _is_available(source_component):
        return Ok(0)
    return Ok(1)


@getter
def get_pumped_hydro_generator_units(
    source_component: HydroTurbine | HydroPumpTurbine,
    context: PluginContext,
) -> Result[int, ValueError]:
    """Online status for pump turbine generators.

    Units with zero pump load are treated as regular hydro (always online).
    Units with non-zero pump load are only online when a HydroReservoir with a
    pumped-storage association references this turbine — meaning a PLEXOSStorage
    will actually be created and connected to it.
    """
    if not _is_available(source_component):
        return Ok(0)

    rating = getattr(source_component, "rating", None)
    pump_load_mw = 0.0
    if rating is not None:
        magnitude = get_magnitude(rating)
        if magnitude is not None:
            pump_load_mw = abs(float(magnitude) * resolve_base_power(source_component))

    if math.isclose(pump_load_mw, 0.0, abs_tol=1e-9):
        return Ok(1)

    # Non-zero pump load: only deactivate components that actually resolve to a pumped
    # category.  A HydroTurbine can have rating > 0 yet still resolve to "hydro" via
    # gen_type_string or ReEDS name patterns — those must stay online.
    category = _resolve_generator_category(source_component, context)
    if category is not None and "pump" not in category.lower():
        return Ok(1)

    # Category is pumped-hydro (or could not be resolved → rule default pumped-hydro):
    # only online when a storage-creating HydroReservoir backs this turbine.
    turbine_names = _build_reservoir_pump_turbine_name_set(context)
    comp_name = getattr(source_component, "name", None)
    if comp_name is not None and str(comp_name) in turbine_names:
        return Ok(1)
    return Ok(0)


@getter
def get_max_capacity(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract maximum capacity in MW from rating, active_power_limits, or max_active_power.

    When rating is available, max_capacity must match rating exactly.
    """

    rating = getattr(source_component, "rating", None)
    rating_value = get_magnitude(rating)
    if rating_value is not None:
        capacity = abs(float(rating_value) * resolve_base_power(source_component))
        return Ok(round(capacity, 2))

    limits = getattr(source_component, "active_power_limits", None)
    if isinstance(limits, dict):
        max_value = limits.get("max")
        if isinstance(max_value, int | float):
            return Ok(round(abs(float(max_value)), 2))

    try:
        value = sienna_get_max_active_power(source_component)
    except (TypeError, NotImplementedError, AttributeError, KeyError):
        value = None

    if value is not None:
        return Ok(round(abs(float(value)), 2))

    return Err(ValueError("active_power_limits or rating missing"))


@getter
def get_generator_commit(component: object, context: PluginContext) -> Result[int, ValueError]:
    """Return 1 if technology is in commit_technologies list or start cost is 0, -1 otherwise."""
    technology = getattr(component, "technology", "")
    defaults_data = _get_defaults_data(context)
    commit_technologies = defaults_data.get("commit_technologies", [])
    if technology in commit_technologies:
        return Ok(1)
    cost = getattr(component, "operation_cost", None)
    start_up = get_magnitude(getattr(cost, "start_up", None)) if cost else None
    if start_up is not None and float(start_up) == 0.0:
        return Ok(1)
    return Ok(-1)


@getter
def get_generator_load_point(source_component: object, context: PluginContext) -> Result[Any, ValueError]:
    """Extract generator load point from ext dict or computed heat-rate data.

    For piecewise heat-rate curves, ``compute_heat_rate_data`` provides a
    multiband ``load_point`` property which should be passed through directly.
    For scalar heat-rate data, fall back to ``heat_rate * fuel_price``.
    """
    ext = getattr(source_component, "ext", None)
    if isinstance(ext, dict):
        load_point = ext.get("NARIS_Load_Point")
        if isinstance(load_point, int | float):
            return Ok(abs(float(load_point)))

    heat_rate_data = compute_heat_rate_data(source_component)
    computed_load_point = heat_rate_data.get("load_point")
    if computed_load_point is not None:
        coerced = coerce_value(computed_load_point)
        if isinstance(coerced, list):
            return Ok([abs(v) if isinstance(v, int | float) else v for v in coerced])
        return Ok(abs(coerced) if isinstance(coerced, int | float) else coerced)

    heat_rate = heat_rate_data.get("heat_rate")
    fuel_price_getter = cast(Any, get_fuel_price)
    fuel_price_result = fuel_price_getter(source_component, context)
    match fuel_price_result:
        case Ok(fuel_price):
            if heat_rate is not None and fuel_price > 0.0:
                return Ok(abs(float(heat_rate) * float(fuel_price)))
        case Err(_):
            pass

    return Ok(0.0)


@getter
def get_heat_rate(source_component: object, context: PluginContext) -> Result[float | None, ValueError]:
    """Extract heat_rate from computed heat rate data.

    When both heat_rate_base and heat_rate_incr are defined, suppress the
    scalar heat_rate property so only the decomposed terms are exported.
    Returning ``None`` allows rule application to skip just this field.
    """
    heat_rate_data = compute_heat_rate_data(source_component)
    base_value = heat_rate_data.get("heat_rate_base")
    has_base = False
    if base_value is not None:
        if isinstance(base_value, int | float):
            has_base = not math.isclose(float(base_value), 0.0, rel_tol=0.0, abs_tol=1e-9)
        else:
            has_base = True

    has_incr = heat_rate_data.get("heat_rate_incr") is not None
    if has_base and has_incr:
        return Ok(None)

    value = heat_rate_data.get("heat_rate")
    return Ok(abs(float(value)) if value is not None else 0.0)


@getter
def get_heat_rate_base(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate_base from computed heat rate data, round to 2 decimals, and return as float (units='GJ/h')"""
    value = compute_heat_rate_data(source_component).get("heat_rate_base")
    return Ok(abs(float(value)) if value is not None else 0.0)


@getter
def get_heat_rate_incr(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate_incr from computed heat rate data and return as float (units='GJ/MWh')"""
    value = compute_heat_rate_data(source_component).get("heat_rate_incr")
    coerced = coerce_value(value)
    return Ok(abs(coerced) if isinstance(coerced, float) else coerced)


@getter
def get_heat_rate_incr2(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate_incr2 from computed heat rate data, round to 2 decimals, and return as float (units='GJ/MWh^2')"""
    value = compute_heat_rate_data(source_component).get("heat_rate_incr2")
    return Ok(abs(float(value)) if value is not None else 0.0)


@getter
def get_heat_rate_incr3(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract heat_rate_incr3 from computed heat rate data, round to 2 decimals, and return as float (units='GJ/MWh^3')"""
    value = compute_heat_rate_data(source_component).get("heat_rate_incr3")
    return Ok(abs(float(value)) if value is not None else 0.0)


@getter
def get_min_up_time(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract minimum up time from time_limits or ext dict; falls back to category default."""
    value = _get_time_limit(source_component, "up", None)
    if value is not None:
        return Ok(value)
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "min_up_time") if category else 0.0)


@getter
def get_min_down_time(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract minimum down time from time_limits or ext dict; falls back to category default."""
    value = _get_time_limit(source_component, "down", None)
    if value is not None:
        return Ok(value)
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "min_down_time") if category else 0.0)


@getter
def get_max_ramp_up(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract maximum ramp up from ramp_limits, convert to MW/min; falls back to category default."""
    ramp_up = _get_ramp_limit_value(source_component, default=0.0, direction="up")
    ramp_up_mw = abs(ramp_up * resolve_base_power(source_component))
    return Ok(
        _resolve_ramp_rates(
            source_component,
            context,
            initial_ramp_mw=ramp_up_mw,
            defaults_key="max_ramp_up_percentage",
        )
    )


@getter
def get_max_ramp_down(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract maximum ramp down from ramp_limits, convert to MW/min; falls back to category default."""
    ramp_down = _get_ramp_limit_value(source_component, default=None, direction="down")
    ramp_down_mw = abs(ramp_down * resolve_base_power(source_component))
    return Ok(
        _resolve_ramp_rates(
            source_component,
            context,
            initial_ramp_mw=ramp_down_mw,
            defaults_key="max_ramp_up_percentage",
        )
    )


@getter
def get_generator_name(source_component: object, context: PluginContext) -> Result[str, ValueError]:
    """Return plant_name from ext (with _N suffix for duplicates), otherwise component name."""
    index = _build_generator_display_name_index(context)
    orig_name = getattr(source_component, "name", "")
    return Ok(index.get(orig_name, orig_name))


@getter
def get_generator_min_stable_level(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    """Extract minimum stable level in MW from active_power_limits.min * base_power.
    Falls back to min_stable_level_percentage * 100 if zero.
    If fallback value exceeds max_capacity, clamp to 50% of max_capacity.
    If the original min stable level is below 10 MW, use 50% of max_capacity.
    """
    min_pu = _get_minmax_value(getattr(source_component, "active_power_limits", None), "min")
    min_mw = (float(min_pu) * resolve_base_power(source_component)) if min_pu is not None else 0.0
    min_mw = abs(min_mw) if min_mw < 0 else min_mw  # ensure non-negative

    max_capacity_mw = None
    max_capacity_getter = cast(Any, get_max_capacity)
    match max_capacity_getter(source_component, context):
        case Ok(max_capacity):
            max_capacity_mw = float(max_capacity)
        case Err(_):
            max_capacity_mw = None

    if math.isclose(min_mw, 0.0, abs_tol=1e-6):
        category = _resolve_generator_category(source_component, context)
        min_mw = _get_defaults(category, "min_stable_level_percentage") * 100.0

        if max_capacity_mw is not None and max_capacity_mw > 0.0 and min_mw > max_capacity_mw:
            min_mw = 0.5 * max_capacity_mw

    # If the source min stable level is tiny (<10 MW), use 50% of max capacity.
    if min_mw < 10.0 and max_capacity_mw is not None and max_capacity_mw > 0.0:
        min_mw = 0.5 * max_capacity_mw

    # Enforce non-zero fallback when min stable level still resolves to 0.0.
    if math.isclose(min_mw, 0.0, abs_tol=1e-6) and max_capacity_mw is not None and max_capacity_mw > 0.0:
        min_mw = 0.5 * max_capacity_mw

    # Nuclear generators must operate at 70 % of max capacity.
    # If the resolved value is not within 5 % of that target, override it.
    if (
        max_capacity_mw is not None
        and max_capacity_mw > 0.0
        and _resolve_generator_category(source_component, context) == "nuclear"
    ):
        target_mw = 0.7 * max_capacity_mw
        if not math.isclose(min_mw, target_mw, rel_tol=0.05):
            min_mw = target_mw

    return Ok(round(min_mw, 2))


@getter
def get_generator_forced_outage_rate(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    """Extract forced outage rate from ext dict or return category default."""
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "forced_outage_rate") * 100.0 if category else 0.0)


@getter
def get_generator_maintenance_rate(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    """Extract maintenance rate from ext dict or return category default."""
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "maintenance_rate") * 100.0 if category else 0.0)


@getter
def get_generator_mean_time_to_repair(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    """Extract mean time to repair from ext dict or return category default."""
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "mean_time_to_repair") if category else 0.0)


@getter
def get_generator_start_cost(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    cost = getattr(source_component, "operation_cost", None)
    value = None
    if cost is not None:
        if isinstance(cost, Mapping):
            value = cost.get("start_up")
        if value is None:
            value = getattr(cost, "start_up", None)
    # Only trust a non-zero source value; zero means "not set" — fall back to category default.
    if value is not None and float(value) != 0.0:
        return Ok(float(value))
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "startup_cost") if category else 0.0)


@getter
def get_generator_shutdown_cost(
    source_component: object, context: PluginContext
) -> Result[float, ValueError]:
    """Extract shutdown cost in $ from operation_cost.start_up attribute of the source component."""
    cost = getattr(source_component, "operation_cost", None)
    value = None
    if cost is not None:
        if isinstance(cost, Mapping):
            value = get_magnitude(cost.get("shut_down"))
        if value is None:
            value = get_magnitude(getattr(cost, "shut_down", None))
    return Ok(float(value) if value is not None else 0.0)


@getter
def get_generator_rating(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract turbine rating (in MW) from the HydroTurbine."""
    rating = getattr(source_component, "rating", None)
    if rating is not None:
        return Ok(
            round(
                max(
                    0.0,
                    float(rating) * resolve_base_power(source_component),
                ),
                2,
            )
        )
    return Ok(0.0)


@getter
def get_generator_vom_cost(source_component: object, context: PluginContext) -> Result[float, ValueError]:
    """Extract variable operating and maintenance cost ($/MWh) from a Generator."""
    value = compute_markup_data(source_component).get("mark_up")
    if value is not None and float(value) != 0.0:
        return Ok(float(value))
    category = _resolve_generator_category(source_component, context)
    return Ok(_get_defaults(category, "vom_cost") if category else 0.0)


@getter
def get_generator_max_energy_day(
    component: HydroDispatch, context: PluginContext
) -> Result[float | int, ValueError]:
    """Return the maximum energy per day for a hydro generator as a PLEXOSPropertyValue with units MW."""
    value = getattr(component, "max_energy_per_day", None)
    if value is None:
        return Ok(0.0)
    return Ok(value)


@getter
def get_generator_fixed_load(
    source_component: HydroDispatch, context: PluginContext
) -> Result[float, ValueError]:
    """Extract fixed load (in MW) from the Generator."""
    value = getattr(source_component, "fixed_load", None)
    if value is None:
        return Ok(0.0)
    return Ok(value)


@getter
def get_generator_load_subtracter(
    source_component: RenewableDispatch | RenewableNonDispatch, context: PluginContext
) -> Result[float, ValueError]:
    """Extract load subtracter (in MW) from the Generator."""
    load_subtracter = getattr(source_component, "load_subtracter", None)
    if load_subtracter is None:
        return Ok(0.0)
    return Ok(0.0)


@getter
def get_turbine_pump_efficiency(
    source_component: HydroTurbine | HydroPumpTurbine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract pump efficiency (%) from the HydroTurbine and HydroPumpTurbine."""
    ht_pump_efficiency = getattr(source_component, "efficiency", None)

    if isinstance(source_component, HydroTurbine):
        default = round(_get_defaults("pumped-hydro", "efficiency") * 100.0, 2)
        if ht_pump_efficiency is not None and ht_pump_efficiency != 0.0:
            value = (
                float(ht_pump_efficiency) * 100.0
                if float(ht_pump_efficiency) <= 1.0
                else float(ht_pump_efficiency)
            )
        else:
            value = default
        return Ok(round(value, 2))
    elif isinstance(source_component, HydroPumpTurbine):
        pump = getattr(ht_pump_efficiency, "pump", None) if ht_pump_efficiency is not None else None
        default = round(_get_defaults("pumped-hydro", "efficiency") * 100.0, 2)
        if pump is not None and pump != 0.0:
            value = float(pump) * 100.0 if float(pump) <= 1.0 else float(pump)
        else:
            value = default
        return Ok(round(value, 2))
    else:
        # Generic fallback: use scalar efficiency if available, honouring 0-1 vs 0-100 scale.
        if (
            ht_pump_efficiency is not None
            and isinstance(ht_pump_efficiency, int | float)
            and ht_pump_efficiency != 0.0
        ):
            return Ok(
                round(
                    float(ht_pump_efficiency) * 100.0
                    if ht_pump_efficiency <= 1.0
                    else float(ht_pump_efficiency),
                    2,
                )
            )
        return Ok(89.0)


@getter
def get_turbine_pump_load(
    source_component: HydroTurbine | HydroPumpTurbine, context: PluginContext
) -> Result[float, ValueError]:
    """Extract pump load (MW) from the HydroTurbine."""
    pump_load = getattr(source_component, "rating", None)
    if pump_load is not None:
        magnitude = get_magnitude(pump_load)
        if magnitude is not None:
            return Ok(
                round(
                    float(magnitude) * resolve_base_power(source_component),
                    2,
                )
            )
    return Ok(0.0)


def _reservoir_has_hydro_pumped_storage_association(
    source_component: HydroReservoir, context: PluginContext
) -> bool:
    """Return True if reservoir is linked to at least one HydroPumpTurbine."""

    def _is_hydro_pump_turbine(turbine: Any) -> bool:
        return isinstance(turbine, HydroPumpTurbine) or type(turbine).__name__ == "HydroPumpTurbine"

    linked_turbines = [
        *list(getattr(source_component, "upstream_turbines", None) or []),
        *list(getattr(source_component, "downstream_turbines", None) or []),
    ]

    if any(_is_hydro_pump_turbine(turbine) for turbine in linked_turbines):
        return True

    ext = getattr(source_component, "ext", None)
    plant_ids = ext.get("plants") if isinstance(ext, dict) else None
    if not isinstance(plant_ids, list):
        return False

    source_system = _source_system(context)
    pump_turbines_by_name = {
        str(getattr(turbine, "name", "")): turbine
        for turbine in source_system.get_components(HydroPumpTurbine)
    }
    return any(isinstance(plant_id, str) and plant_id in pump_turbines_by_name for plant_id in plant_ids)


def _build_reservoir_pump_turbine_name_set(context: PluginContext) -> set[str]:
    """Build the set of turbine names referenced by any storage-creating HydroReservoir, cached.

    Only reservoirs that pass ``_reservoir_has_hydro_pumped_storage_association``
    are considered, so the returned names correspond to turbines that will
    actually receive a PLEXOSStorage membership.
    """
    cached = context._cache.get("reservoir_pump_turbine_name_set")
    if cached is not None:
        return cast(set[str], cached)

    names: set[str] = set()
    for reservoir in _source_system(context).get_components(HydroReservoir):
        if not _reservoir_has_hydro_pumped_storage_association(reservoir, context):
            continue
        for turbine in [
            *list(getattr(reservoir, "upstream_turbines", None) or []),
            *list(getattr(reservoir, "downstream_turbines", None) or []),
        ]:
            tname = getattr(turbine, "name", None)
            if tname:
                names.add(str(tname))
        ext = getattr(reservoir, "ext", None)
        plant_ids = ext.get("plants") if isinstance(ext, dict) else None
        if isinstance(plant_ids, list):
            for plant_id in plant_ids:
                if isinstance(plant_id, str):
                    names.add(plant_id)

    context._cache["reservoir_pump_turbine_name_set"] = names
    return names


def _get_reservoir_location(source_component: HydroReservoir) -> str | None:
    """Return normalized reservoir location label (HEAD/TAIL) when available.

    Falls back to ext metadata and name suffixes when explicit reservoir_location
    is missing in source data.
    """
    # Most reliable signal in EI data: explicit _head/_tail suffix in component name.
    name = str(getattr(source_component, "name", "")).strip().upper()
    if name.endswith(("_HEAD", " HEAD")):
        return "HEAD"
    if name.endswith(("_TAIL", " TAIL")):
        return "TAIL"

    location = getattr(source_component, "reservoir_location", None)
    raw = getattr(location, "value", location)
    if raw is not None:
        label = str(raw).upper()
        if "HEAD" in label:
            return "HEAD"
        if "TAIL" in label:
            return "TAIL"

    ext = getattr(source_component, "ext", None)
    if isinstance(ext, dict):
        ext_loc = ext.get("reservoir_location") or ext.get("RESERVOIR_LOCATION")
        if ext_loc is not None:
            label = str(getattr(ext_loc, "value", ext_loc)).upper()
            if "HEAD" in label:
                return "HEAD"
            if "TAIL" in label:
                return "TAIL"

    return None


def _get_reservoir_name_suffix_location(source_component: HydroReservoir) -> str | None:
    """Return HEAD/TAIL when reservoir name explicitly ends with _head/_tail."""
    name = str(getattr(source_component, "name", "")).strip().casefold()
    if name.endswith(("_head", " head")):
        return "HEAD"
    if name.endswith(("_tail", " tail")):
        return "TAIL"
    return None


def _get_reservoir_storage_base_name(source_component: HydroReservoir) -> str:
    """Return canonical storage base name for a reservoir."""
    ext = getattr(source_component, "ext", None)
    if isinstance(ext, dict):
        plant_name = ext.get("plant_name")
        if plant_name:
            return str(plant_name)
    return _reservoir_base_name(source_component.name)


def _has_explicit_side_reservoir_for_base(
    source_component: HydroReservoir,
    context: PluginContext,
    side: str,
) -> bool:
    """Return True when another reservoir with same base explicitly maps the requested side."""
    this_base = _get_reservoir_storage_base_name(source_component).casefold()
    this_uuid = getattr(source_component, "uuid", None)

    for other in _source_system(context).get_components(HydroReservoir):
        other_uuid = getattr(other, "uuid", None)
        if this_uuid is not None and other_uuid == this_uuid:
            continue
        if _get_reservoir_storage_base_name(other).casefold() != this_base:
            continue
        if _get_reservoir_name_suffix_location(other) == side:
            return True

    return False


@getter
def get_head_storage_name(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    """Return the storage name for the head reservoir (appends _head), using plant_name from ext if available."""
    if not _reservoir_has_hydro_pumped_storage_association(source_component, context):
        return Err(
            ValueError(
                f"Skipping head storage conversion for reservoir '{source_component.name}': no HydroPumpTurbine association"
            )
        )

    # Only explicit suffixes gate conversion. Unsuffixed reservoirs are expanded
    # into both _head and _tail storages.
    suffix_location = _get_reservoir_name_suffix_location(source_component)
    if suffix_location == "TAIL":
        return Err(
            ValueError(
                f"Skipping head storage conversion for reservoir '{source_component.name}': name indicates tail reservoir"
            )
        )

    if suffix_location is None and _has_explicit_side_reservoir_for_base(
        source_component, context, side="HEAD"
    ):
        return Err(
            ValueError(
                f"Skipping head storage conversion for reservoir '{source_component.name}': explicit head reservoir already exists for this plant"
            )
        )

    base = _get_reservoir_storage_base_name(source_component)
    return Ok(f"{base}_head")


@getter
def get_head_storage_uuid(
    source_component: HydroReservoir,
    context: PluginContext,
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the head reservoir storage based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_head")))


@getter
def get_tail_storage_name(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    """Return the storage name for the tail reservoir (appends _tail), using plant_name from ext if available."""
    if not _reservoir_has_hydro_pumped_storage_association(source_component, context):
        return Err(
            ValueError(
                f"Skipping tail storage conversion for reservoir '{source_component.name}': no HydroPumpTurbine association"
            )
        )

    # Only explicit suffixes gate conversion. Unsuffixed reservoirs are expanded
    # into both _head and _tail storages.
    suffix_location = _get_reservoir_name_suffix_location(source_component)
    if suffix_location == "HEAD":
        return Err(
            ValueError(
                f"Skipping tail storage conversion for reservoir '{source_component.name}': name indicates head reservoir"
            )
        )

    if suffix_location is None and _has_explicit_side_reservoir_for_base(
        source_component, context, side="TAIL"
    ):
        return Err(
            ValueError(
                f"Skipping tail storage conversion for reservoir '{source_component.name}': explicit tail reservoir already exists for this plant"
            )
        )

    base = _get_reservoir_storage_base_name(source_component)
    return Ok(f"{base}_tail")


@getter
def get_tail_storage_uuid(
    source_component: HydroReservoir, context: PluginContext
) -> Result[str, ValueError]:
    """Generate a deterministic UUID for the tail reservoir storage based on the source component's UUID and a suffix."""
    import uuid

    return Ok(str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_component.uuid}_tail")))


@getter
def get_storage_initial_volume(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the initial storage volume for a storage type."""
    value = getattr(source_component, "initial_volume", None)
    if value is not None and float(value) != 0.0:
        return Ok(round(float(value) / 1000.0, 2))
    storage_limits = getattr(source_component, "storage_level_limits", None)
    if storage_limits is None:
        return Ok(50.0)
    if isinstance(storage_limits, dict):
        max_val = storage_limits.get("max")
    else:
        max_val = getattr(storage_limits, "max", None)
    if isinstance(max_val, int | float) and max_val:
        return Ok(round(float(max_val) * 0.5 / 1000.0, 2))
    return Ok(50.0)


@getter
def get_storage_max_volume(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the max storage volume for a storage type."""
    value = getattr(source_component, "storage_level_limits", None)
    if value is None:
        return Ok(100.0)
    if isinstance(value, dict):
        max_val = value.get("max")
        if isinstance(max_val, int | float) and max_val:
            return Ok(round(float(max_val) / 1000.0, 2))
        return Ok(100.0)
    max_val = getattr(value, "max", None)
    if isinstance(max_val, int | float) and max_val:
        return Ok(round(float(max_val) / 1000.0, 2))
    return Ok(100.0)


@getter
def get_storage_natural_inflow(
    source_component: HydroReservoir, context: PluginContext
) -> Result[float, ValueError]:
    """Return the natural inflow for a storage type."""
    value = getattr(source_component, "inflow", None)
    if value is not None:
        return Ok(float(value))
    return Ok(0.0)


@getter
def get_battery_capacity(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract battery capacity in MWh from storage_capacity attribute, convert using base power, and return as float."""
    value = getattr(source_component, "storage_capacity", None)
    if value is not None and float(value) != 0.0:
        return Ok(round(float(value) * resolve_base_power(source_component), 2))
    return Ok(round(_get_defaults("battery", "capacity_MW"), 2))


@getter
def get_battery_charge_efficiency(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract battery charge efficiency from efficiency attribute, convert to percentage if necessary, and return as float."""
    efficiency = source_component.efficiency
    value = float(efficiency.get("input", 0.0)) if isinstance(efficiency, dict) else float(efficiency.input)
    if value != 0.0:
        return Ok(round(value * 100 if value <= 1.0 else value, 2))
    return Ok(round(_get_defaults("battery", "charge_efficiency") * 100, 2))


@getter
def get_battery_discharge_efficiency(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract battery discharge efficiency from efficiency attribute, convert to percentage if necessary, and return as float."""
    efficiency = source_component.efficiency
    value = float(efficiency.get("output", 0.0)) if isinstance(efficiency, dict) else float(efficiency.output)
    if value != 0.0:
        return Ok(round(value * 100 if value <= 1.0 else value, 2))
    return Ok(round(_get_defaults("battery", "discharge_efficiency") * 100, 2))


@getter
def get_battery_initial_soc(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract initial state of charge from initial_storage_capacity_level attribute, convert to percentage if necessary, and return as float."""
    value = getattr(source_component, "initial_storage_capacity_level", None)
    if value is None:
        return Ok(_get_defaults("battery", "initial_soc") * 100)
    return Ok(float(value) * 100)


@getter
def get_battery_min_soc(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract minimum state of charge from storage_level_limits attribute, convert to percentage if necessary, and return as float."""
    limits = getattr(source_component, "storage_level_limits", None)
    if limits is None:
        return Ok(_get_defaults("battery", "min_soc") * 100)
    if isinstance(limits, dict):
        min_val = limits.get("min")
        if isinstance(min_val, int | float):
            return Ok(float(min_val) * 100)
        return Ok(_get_defaults("battery", "min_soc") * 100)
    return Ok(float(limits.min) * 100)


@getter
def get_battery_max_soc(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    """Extract maximum state of charge from storage_level_limits attribute, convert to percentage if necessary, and return as float."""
    limits = getattr(source_component, "storage_level_limits", None)
    if limits is None:
        return Ok(_get_defaults("battery", "max_soc") * 100)
    if isinstance(limits, dict):
        max_val = limits.get("max")
        if isinstance(max_val, int | float):
            return Ok(float(max_val) * 100)
        return Ok(_get_defaults("battery", "max_soc") * 100)
    return Ok(float(limits.max) * 100)


@getter
def get_battery_cycles(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    value = getattr(source_component, "cycle_limits", None)
    if value is None:
        return Ok(10000.0)
    return Ok(float(value))


@getter
def get_battery_max_power(
    source_component: EnergyReservoirStorage, context: PluginContext
) -> Result[float, ValueError]:
    rating = getattr(source_component, "rating", None)
    rating_value = get_magnitude(rating)
    if rating_value is not None:
        return Ok(round(float(rating_value) * resolve_base_power(source_component), 2))

    limits = getattr(source_component, "output_active_power_limits", None)
    if limits is None:
        return Ok(0.0)
    if isinstance(limits, dict):
        max_val = limits.get("max")
        if isinstance(max_val, int | float):
            return Ok(float(max_val) * resolve_base_power(source_component))
        return Ok(0.0)
    if getattr(limits, "max", None) is None:
        return Ok(0.0)
    value = get_magnitude(limits.max)
    return Ok(float(value) * resolve_base_power(source_component) if value is not None else 0.0)


@getter
def get_reserve_timeframe(
    source_component: VariableReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get reserve timeframe in seconds."""
    time_frame = getattr(source_component, "time_frame", 0.0)
    return Ok(time_frame * 60)


@getter
def get_reserve_duration(
    source_component: VariableReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get reserve sustained time in seconds."""
    sustained_time = getattr(source_component, "sustained_time", 0.0)
    return Ok(sustained_time)


@getter
def get_reserve_min_provision(
    source_component: VariableReserve, context: PluginContext
) -> Result[float, ValueError]:
    """Get reserve requirement in MW (source requirement is p.u. of system base)."""
    requirement = getattr(source_component, "requirement", 0.0)
    try:
        return Ok(float(requirement) * _get_system_base_power(context))
    except (TypeError, ValueError):
        return Ok(0.0)


@getter
def get_reserve_type(source_component: VariableReserve, context: PluginContext) -> Result[int, ValueError]:
    """Get PLEXOS reserve type from Sienna ReserveType."""
    reserve_type_mapping = {
        ReserveType.SPINNING: 1,
        ReserveType.FLEXIBILITY: 2,
        ReserveType.REGULATION: 3,
    }
    plexos_type = reserve_type_mapping.get(source_component.reserve_type, 1)
    return Ok(plexos_type)


@getter
def get_reserve_vors(source_component: VariableReserve, context: PluginContext) -> Result[float, ValueError]:
    """Get reserve VORS."""
    vors = getattr(source_component, "vors", -1.0)
    return Ok(vors)


@getter
def get_interface_min_flow(
    source_component: TransmissionInterface, context: PluginContext
) -> Result[float, ValueError]:
    """Get min_flow as the negative sum of all constituent line ratings (MW) in direction_mapping."""
    direction_mapping = getattr(source_component, "direction_mapping", None) or {}
    if not direction_mapping:
        limits = getattr(source_component, "active_power_flow_limits", None)
        if limits is None:
            return Ok(-99999.0)
        value = limits.get("min") if isinstance(limits, dict) else getattr(limits, "min", None)
        return Ok(float(value) if isinstance(value, int | float) else -99999.0)

    total_rating = 0.0
    for line_name in direction_mapping:
        source_line = _find_source_line(context, line_name)
        if source_line is None:
            continue
        rating = getattr(source_line, "rating", None)
        magnitude = get_magnitude(rating)
        if magnitude is not None:
            total_rating += abs(float(magnitude)) * _get_system_base_power(context)
        elif isinstance(rating, int | float):
            total_rating += abs(float(rating)) * _get_system_base_power(context)

    return Ok(round(-total_rating, 2) if total_rating > 0.0 else -99999.0)


@getter
def get_interface_max_flow(
    source_component: TransmissionInterface, context: PluginContext
) -> Result[float, ValueError]:
    """Get max_flow as the sum of all constituent line ratings (MW) in direction_mapping."""
    direction_mapping = getattr(source_component, "direction_mapping", None) or {}
    if not direction_mapping:
        limits = getattr(source_component, "active_power_flow_limits", None)
        if limits is None:
            return Ok(99999.0)
        value = limits.get("max") if isinstance(limits, dict) else getattr(limits, "max", None)
        return Ok(float(value) if isinstance(value, int | float) else 99999.0)

    total_rating = 0.0
    for line_name in direction_mapping:
        source_line = _find_source_line(context, line_name)
        if source_line is None:
            continue
        rating = getattr(source_line, "rating", None)
        magnitude = get_magnitude(rating)
        if magnitude is not None:
            total_rating += abs(float(magnitude)) * _get_system_base_power(context)
        elif isinstance(rating, int | float):
            total_rating += abs(float(rating)) * _get_system_base_power(context)

    return Ok(round(total_rating, 2) if total_rating > 0.0 else 99999.0)


@getter
def membership_parent_component(component: object, context: PluginContext) -> Result[Any, ValueError]:
    """Return the component itself for membership parent/child fields."""
    return Ok(component)


@getter
def membership_collection_nodes(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Nodes collection enum."""
    return Ok(CollectionEnum.Nodes)


@getter
def membership_collection_lines(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Lines collection enum."""
    return Ok(CollectionEnum.Lines)


@getter
def membership_collection_generators(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Generators collection enum."""
    return Ok(CollectionEnum.Generators)


@getter
def membership_collection_batteries(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Batteries collection enum."""
    return Ok(CollectionEnum.Batteries)


@getter
def membership_collection_region(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Region collection enum."""
    return Ok(CollectionEnum.Region)


@getter
def membership_collection_zone(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Zone collection enum."""
    return Ok(CollectionEnum.Zone)


@getter
def membership_collection_node_from(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the NodeFrom collection enum."""
    return Ok(CollectionEnum.NodeFrom)


@getter
def membership_collection_node_to(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the NodeTo collection enum."""
    return Ok(CollectionEnum.NodeTo)


@getter
def membership_collection_head_storage(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Head Storage collection enum."""
    return Ok(CollectionEnum.HeadStorage)


@getter
def membership_collection_tail_storage(
    component: object, context: PluginContext
) -> Result[CollectionEnum, ValueError]:
    """Return the Tail Storage collection enum."""
    return Ok(CollectionEnum.TailStorage)


@getter
def membership_reserve_child_generator(
    reserve: VariableReserve, context: PluginContext
) -> Result[PLEXOSGenerator, ValueError]:
    target_system = cast(Any, context.target_system)
    reserve_index = _build_source_reserve_name_index(context)
    service_index = _build_generator_service_index(context)

    reserve_name = getattr(reserve, "name", "")
    source_reserve = reserve_index.get(reserve_name)
    if source_reserve is None:
        return Err(ValueError(f"Source reserve '{reserve_name}' not found"))

    for gen in service_index.get(source_reserve.name, []):
        target_device = target_system.get_component_by_uuid(gen.uuid)
        if target_device:
            return Ok(target_device)

    return Err(ValueError(f"No contributing generators found for reserve '{reserve_name}'"))


@getter
def membership_reserve_child_battery(
    reserve: VariableReserve, context: PluginContext
) -> Result[PLEXOSBattery, ValueError]:
    target_system = cast(Any, context.target_system)
    reserve_index = _build_source_reserve_name_index(context)
    battery_service_index = _build_battery_service_index(context)

    reserve_name = getattr(reserve, "name", "")
    source_reserve = reserve_index.get(reserve_name)
    if source_reserve is None:
        logger.warning("Source reserve '{}' not found", reserve_name)
        return Err(ValueError(f"Source reserve '{reserve_name}' not found"))

    for battery in battery_service_index.get(source_reserve.name, []):
        target_device = target_system.get_component_by_uuid(battery.uuid)
        if target_device and isinstance(target_device, PLEXOSBattery):
            return Ok(target_device)

    logger.warning("No contributing batteries found for reserve '{}'", reserve_name)
    return Err(ValueError(f"No contributing batteries found for reserve '{reserve_name}'"))


@getter
def membership_component_child_node(
    component: object, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Resolve a component's bus to the translated node.

    Works for both PLEXOSGenerator and PLEXOSBattery components.
    Also attaches time series from source to target component.
    """
    comp_name = getattr(component, "name", "")

    if isinstance(component, PLEXOSGenerator):
        source_comp = _lookup_source_generator(context, comp_name)
        comp_type = "generator"
        _attach_generator_time_series(context, comp_name, component)
    elif isinstance(component, PLEXOSBattery):
        source_comp = _lookup_source_battery(context, comp_name)
        comp_type = "battery"
    else:
        source_comp = _lookup_source_generator(context, comp_name)
        if source_comp is None:
            source_comp = _lookup_source_battery(context, comp_name)
            comp_type = "battery" if source_comp is not None else "component"
        else:
            comp_type = "generator"
            _attach_generator_time_series(context, comp_name, component)

    if source_comp is None:
        return Err(ValueError(f"No source {comp_type} found for '{comp_name}'"))

    bus = getattr(source_comp, "bus", None)
    if bus is None or not getattr(bus, "name", None):
        return Err(ValueError(f"Source {comp_type} '{source_comp.name}' is missing bus data"))

    return _lookup_target_node_by_name(context, bus.name)


@getter
def membership_interface_child_line(
    interface: object, context: PluginContext
) -> Result[PLEXOSLine, ValueError]:
    interface_index = _build_source_interface_name_index(context)
    line_index = _build_target_line_name_index(context)

    interface_name = getattr(interface, "name", "")
    source_interface = interface_index.get(interface_name)
    if source_interface is None:
        return Err(ValueError(f"No source TransmissionInterface found for '{interface_name}'"))

    lines = getattr(source_interface, "lines", None)
    if not lines:
        return Err(ValueError(f"TransmissionInterface '{interface_name}' has no lines"))

    first_line = lines[0]
    line_name = first_line.name if hasattr(first_line, "name") else str(first_line)
    target_line = line_index.get(line_name)
    if target_line is None:
        return Err(ValueError(f"No PLEXOSLine found for line '{line_name}'"))
    return Ok(target_line)


@getter
def membership_region_parent_node(region: object, context: PluginContext) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node for membership parent links and attach load time series."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node_by_source_area(context, region_name)
    match result:
        case Ok(node):
            try:
                _attach_region_node_load_time_series(context, region_name, node, region_component=region)
            except Exception as exc:
                logger.warning("Failed to attach load time series for region {}: {}", region_name, exc)
            return result
        case Err(error):
            return Err(ValueError(str(error)) if not isinstance(error, ValueError) else error)
        case _:
            return Err(ValueError(f"Unexpected result type for region '{region_name}'"))


@getter
def membership_region_child_node(region: object, context: PluginContext) -> Result[PLEXOSNode, ValueError]:
    """Find the translated node that matches the region name and attach load time series."""
    region_name = getattr(region, "name", "")
    result = _lookup_target_node_by_source_area(context, region_name)
    match result:
        case Ok(node):
            try:
                _attach_region_node_load_time_series(context, region_name, node, region_component=region)
            except Exception as exc:
                logger.warning("Failed to attach load time series for region {}: {}", region_name, exc)
            return result
        case Err(error):
            return Err(ValueError(str(error)) if not isinstance(error, ValueError) else error)
        case _:
            return Err(ValueError(f"Unexpected result type for region '{region_name}'"))


@getter
def membership_node_child_zone(node: PLEXOSNode, context: PluginContext) -> Result[PLEXOSZone, ValueError]:
    """Resolve a node's source bus load_zone to the translated PLEXOSZone."""
    source_bus = _build_bus_name_index(context).get(getattr(node, "name", ""))
    if source_bus is None:
        return Err(ValueError(f"No source bus found for node '{getattr(node, 'name', '')}'"))

    load_zone = getattr(source_bus, "load_zone", None)
    if load_zone is None:
        area = getattr(source_bus, "area", None)
        load_zone = getattr(area, "load_zone", None) if area is not None else None
    if load_zone is None:
        return Err(ValueError(f"No load_zone found for source bus '{source_bus.name}'"))

    zone_name = getattr(load_zone, "name", None)
    zone_uuid = getattr(load_zone, "uuid", None)

    target_zones = list(_target_system(context).get_components(PLEXOSZone))
    if zone_name is not None:
        for zone in target_zones:
            if getattr(zone, "name", None) == str(zone_name):
                return Ok(zone)

    if zone_uuid is not None:
        zone_uuid_str = str(zone_uuid)
        for zone in target_zones:
            if str(getattr(zone, "uuid", "")) == zone_uuid_str:
                return Ok(zone)

    return Err(
        ValueError(
            f"No translated PLEXOSZone found for bus '{source_bus.name}' load_zone '{zone_name or zone_uuid}'"
        )
    )


@getter
def membership_line_from_parent_node(
    line: PLEXOSLine, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Return the from-node for a translated line."""
    source_line = _find_source_line(context, line.name)

    if source_line is None:
        return Err(ValueError(f"Source line '{line.name}' not found"))

    if not hasattr(source_line, "arc"):
        return Err(ValueError(f"Source line '{line.name}' missing arc data"))

    from_bus = source_line.arc.from_to
    from_bus_name = from_bus.name if hasattr(from_bus, "name") else str(from_bus)

    return _lookup_target_node_by_name(context, from_bus_name)


@getter
def membership_line_to_parent_node(
    line: PLEXOSLine, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Return the to-node for a translated line."""
    source_line = _find_source_line(context, line.name)

    if source_line is None:
        return Err(ValueError(f"Source line '{line.name}' not found"))

    if not hasattr(source_line, "arc"):
        return Err(ValueError(f"Source line '{line.name}' missing arc data"))

    to_bus = source_line.arc.to_from
    to_bus_name = to_bus.name if hasattr(to_bus, "name") else str(to_bus)

    return _lookup_target_node_by_name(context, to_bus_name)


@getter
def membership_transformer_from_parent_node(
    transformer: PLEXOSTransformer, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Return the from-node for a translated transformer (2W and 3W arm transformers)."""
    result_3w = _find_3w_source_transformer(context, transformer.name)
    if result_3w is not None:
        source_3w, arm = result_3w
        arc = getattr(source_3w, f"{arm}_star_arc", None)
        if arc is None:
            return Err(ValueError(f"No '{arm}_star_arc' on source transformer '{source_3w.name}'"))
        from_bus = arc.from_to
        from_bus_name = from_bus.name if hasattr(from_bus, "name") else str(from_bus)
        return _lookup_target_node_by_name(context, from_bus_name)

    source_transformer = _find_source_transformer(context, transformer.name)
    if source_transformer is None:
        return Err(ValueError(f"Source transformer '{transformer.name}' not found"))
    if not hasattr(source_transformer, "arc"):
        return Err(ValueError(f"Source transformer '{transformer.name}' missing arc data"))
    from_bus = source_transformer.arc.from_to
    from_bus_name = from_bus.name if hasattr(from_bus, "name") else str(from_bus)
    return _lookup_target_node_by_name(context, from_bus_name)


@getter
def membership_transformer_to_parent_node(
    transformer: PLEXOSTransformer, context: PluginContext
) -> Result[PLEXOSNode, ValueError]:
    """Return the to-node for a translated transformer (2W arms go to star_bus, 2W go to arc.to_from)."""
    result_3w = _find_3w_source_transformer(context, transformer.name)
    if result_3w is not None:
        source_3w, _ = result_3w
        star_bus = source_3w.star_bus
        star_bus_name = star_bus.name if hasattr(star_bus, "name") else str(star_bus)
        return _lookup_target_node_by_name(context, star_bus_name)

    source_transformer = _find_source_transformer(context, transformer.name)
    if source_transformer is None:
        return Err(ValueError(f"Source transformer '{transformer.name}' not found"))
    if not hasattr(source_transformer, "arc"):
        return Err(ValueError(f"Source transformer '{transformer.name}' missing arc data"))
    to_bus = source_transformer.arc.to_from
    to_bus_name = to_bus.name if hasattr(to_bus, "name") else str(to_bus)
    return _lookup_target_node_by_name(context, to_bus_name)


def _build_reservoir_by_turbine_index(context: PluginContext) -> dict[str, Any]:
    """Build a mapping from source turbine name to its HydroReservoir, using downstream_turbines and ext[\"plants\"]."""
    cache_key = "_reservoir_by_turbine_index"
    if (cached := context._cache.get(cache_key)) is not None:
        return cached
    source_system = cast(Any, context.source_system)
    index: dict[str, Any] = {}
    for reservoir in source_system.get_components(HydroReservoir):
        for turbine in getattr(reservoir, "downstream_turbines", None) or []:
            tname = getattr(turbine, "name", None)
            if tname and tname not in index:
                index[tname] = reservoir
        ext = getattr(reservoir, "ext", None)
        if isinstance(ext, dict):
            for plant_id in ext.get("plants") or []:
                if isinstance(plant_id, str) and plant_id not in index:
                    index[plant_id] = reservoir
    # Also index by display name so target-side PLEXOSGenerator names resolve correctly
    display_index = _build_generator_display_name_index(context)
    for source_name, reservoir in list(index.items()):
        display_name = display_index.get(source_name)
        if display_name and display_name not in index:
            index[display_name] = reservoir
    context._cache[cache_key] = index
    return index


def _is_hydro_pumped_storage_generator(context: PluginContext, gen_name: str) -> bool:
    """Return True when target generator name resolves to a source HydroPumpedStorage."""
    source_generator = _lookup_source_generator(context, gen_name)
    return isinstance(source_generator, HydroPumpedStorage)


@getter
def membership_head_storage_generator(
    generator: HydroTurbine, context: PluginContext
) -> Result[Any, ValueError]:
    gen_name = getattr(generator, "name", "")
    storage_index = _build_target_storage_name_index(context)

    # Primary: look up which reservoir owns this turbine
    reservoir = _build_reservoir_by_turbine_index(context).get(gen_name)
    if reservoir is not None:
        ext = getattr(reservoir, "ext", None)
        base = (
            str(ext["plant_name"])
            if isinstance(ext, dict) and ext.get("plant_name")
            else _reservoir_base_name(reservoir.name)
        )
        storage_name = f"{base}_head"
        target_storage = storage_index.get(storage_name.lower())
        if target_storage is not None:
            _attach_reservoir_time_series_to_storage(context, storage_name, target_storage)
            return Ok(target_storage)

    # Fallback: name-based convention
    storage_name = (
        gen_name.replace("_Turbine", "_Reservoir_head")
        if gen_name.endswith("_Turbine")
        else f"{gen_name}_head"
    )
    target_storage = storage_index.get(storage_name.lower())
    if target_storage is None:
        logger.warning("No PLEXOSStorage found for '{}', skipping membership.", gen_name)
        return Err(ValueError(f"No PLEXOSStorage found for '{gen_name}'"))
    _attach_reservoir_time_series_to_storage(context, storage_name, target_storage)
    return Ok(target_storage)


@getter
def membership_tail_storage_generator(
    generator: HydroTurbine, context: PluginContext
) -> Result[Any, ValueError]:
    gen_name = getattr(generator, "name", "")
    storage_index = _build_target_storage_name_index(context)

    # Primary: look up which reservoir owns this turbine
    reservoir = _build_reservoir_by_turbine_index(context).get(gen_name)
    if reservoir is not None:
        ext = getattr(reservoir, "ext", None)
        base = (
            str(ext["plant_name"])
            if isinstance(ext, dict) and ext.get("plant_name")
            else _reservoir_base_name(reservoir.name)
        )
        storage_name = f"{base}_tail"
        target_storage = storage_index.get(storage_name.lower())
        if target_storage is not None:
            _attach_reservoir_time_series_to_storage(context, storage_name, target_storage)
            return Ok(target_storage)

    # Fallback: name-based convention
    storage_name = (
        gen_name.replace("_Turbine", "_Reservoir_tail")
        if gen_name.endswith("_Turbine")
        else f"{gen_name}_tail"
    )
    target_storage = storage_index.get(storage_name.lower())
    if target_storage is None:
        logger.warning("No PLEXOSStorage found for '{}', skipping membership.", gen_name)
        return Err(ValueError(f"No PLEXOSStorage found for '{gen_name}'"))
    _attach_reservoir_time_series_to_storage(context, storage_name, target_storage)
    return Ok(target_storage)


@getter
def membership_line_parent_interface(line: PLEXOSLine, context: PluginContext) -> Result[Any, ValueError]:
    """Return the parent PLEXOSInterface for a translated line by matching its name against source TransmissionInterface direction_mapping keys."""
    from r2x_plexos.models import PLEXOSInterface

    line_name = getattr(line, "name", "")
    source_system = cast(Any, context.source_system)
    target_system = cast(Any, context.target_system)
    line_to_iface = context._cache.get("line_to_interface_name_index")
    if line_to_iface is None:
        line_to_iface = {}
        for iface in source_system.get_components(TransmissionInterface):
            for mapped_name in getattr(iface, "direction_mapping", None) or {}:
                line_to_iface[mapped_name] = iface.name
        context._cache["line_to_interface_name_index"] = line_to_iface

    interface_name = line_to_iface.get(line_name)
    if interface_name is None:
        return Err(
            ValueError(f"No TransmissionInterface found containing line '{line_name}' in direction_mapping")
        )

    target_iface_index = context._cache.get("target_interface_name_index")
    if target_iface_index is None:
        target_iface_index = {iface.name: iface for iface in target_system.get_components(PLEXOSInterface)}
        context._cache["target_interface_name_index"] = target_iface_index

    target_iface = target_iface_index.get(interface_name)
    if target_iface is None:
        return Err(ValueError(f"No PLEXOSInterface found with name '{interface_name}'"))

    return Ok(target_iface)
