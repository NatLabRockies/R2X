"""Utility helpers for ReEDS → PLEXOS translation."""

from __future__ import annotations

import hashlib
from calendar import monthrange
from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import numpy as np
from infrasys import NonSequentialTimeSeries, SingleTimeSeries
from loguru import logger
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSStorage,
)

from r2x_core import System

if TYPE_CHECKING:
    from r2x_core import PluginContext, System


FUEL_PRICE_TS_NAME = "fuel_price"
FUEL_TS_TYPES = (SingleTimeSeries, NonSequentialTimeSeries)

# (fuel_type, scalar price, sorted fingerprints of fuel price time series)
FuelKey = tuple[str, float, tuple[str, ...]]


def _get_reeds_purchaser_source_types() -> tuple[type[Any], ...]:
    """Return consuming-demand source model types available in the installed ReEDS package."""
    from r2x_reeds import models as reeds_models

    type_names = (
        "ReEDSElectrolyzerDemand",
        "ReEDSSteamMethaneReformingDemand",
        "ReEDSDataCenterDemand",
        "ReEDSConsumingTechnology",
    )
    resolved_types: list[type[Any]] = []
    for type_name in type_names:
        model_type = getattr(reeds_models, type_name, None)
        if isinstance(model_type, type) and model_type not in resolved_types:
            resolved_types.append(model_type)
    return tuple(resolved_types)


def _get_plexos_purchaser_type() -> type[Any]:
    """Return purchaser model type, falling back to generator when purchaser is unavailable."""
    from r2x_plexos import models as plexos_models

    purchaser_type = getattr(plexos_models, "PLEXOSPurchaser", None)
    if isinstance(purchaser_type, type):
        return purchaser_type
    return PLEXOSGenerator


def attach_region_load_time_series(context: PluginContext) -> None:
    """Attach demand load and time series from ReEDSDemand to the translated PLEXOSRegion."""
    from r2x_plexos.models import PLEXOSRegion
    from r2x_reeds.models.components import ReEDSDemand

    if context.target_system is None or context.source_system is None:
        return

    target_regions = {region.name: region for region in context.target_system.get_components(PLEXOSRegion)}

    for demand in context.source_system.get_components(ReEDSDemand):
        region = getattr(demand, "region", None)
        region_name = getattr(region, "name", None)
        if region_name is None or region_name not in target_regions:
            continue

        region_component = target_regions[region_name]

        for metadata in context.source_system.time_series.list_time_series_metadata(demand):
            ts_list = context.source_system.list_time_series(demand, name=metadata.name, **metadata.features)
            if not ts_list:
                logger.warning("Missing demand time series {} for {}", metadata.name, demand.name)
                continue

            ts = deepcopy(ts_list[0])
            ts_type = ts.__class__

            if ts.name == "max_active_power":
                ts.name = "max_active_power_load"

            if not context.target_system.has_time_series(
                region_component, name=ts.name, time_series_type=ts_type, **metadata.features
            ):
                context.target_system.add_time_series(ts, region_component, **metadata.features)
                logger.debug("Attached demand time series {} to region {}", ts.name, region_name)


def attach_reserve_time_series(context: PluginContext) -> None:
    """Attach only min_provision time series from ReEDSReserve to the translated PLEXOSReserve."""
    from r2x_plexos.models import PLEXOSReserve
    from r2x_reeds.models.components import ReEDSReserve

    if context.source_system is None or context.target_system is None:
        return

    source_reserves = {r.name: r for r in context.source_system.get_components(ReEDSReserve)}
    for reserve in context.target_system.get_components(PLEXOSReserve):
        source_reserve = source_reserves.get(reserve.name)
        if source_reserve is None:
            continue

        if context.source_system.has_time_series(source_reserve):
            ts_list = context.source_system.list_time_series(source_reserve)
            for ts in ts_list:
                context.target_system.add_time_series(deepcopy(ts), reserve)


def _convert_hydro_budget_time_series(ts: Any, cadence: str, capacity: float) -> Any:
    """Convert ReEDS hourly capacity factors to PLEXOS hydro energy limits."""
    from infrasys import SingleTimeSeries

    if not isinstance(ts, SingleTimeSeries) or ts.resolution != timedelta(hours=1):
        raise ValueError(
            "hydro_budget must be an hourly SingleTimeSeries; "
            f"got {type(ts).__name__} with resolution {getattr(ts, 'resolution', None)}"
        )

    hourly_values = [float(value) * capacity for value in ts.data]

    if cadence == "hourly":
        values = hourly_values
        output_resolution = timedelta(hours=1)
    else:
        daily_values = [
            sum(hourly_values[index : index + 24]) / 1000.0 for index in range(0, len(hourly_values), 24)
        ]

        if cadence == "daily":
            values = daily_values
            output_resolution = timedelta(days=1)
        elif cadence == "weekly":
            if len(daily_values) > 364:
                values = [sum(daily_values[index : index + 7]) for index in range(0, 51 * 7, 7)]
                values.append(sum(daily_values[51 * 7 :]))
            else:
                values = [sum(daily_values[index : index + 7]) for index in range(0, len(daily_values), 7)]
            output_resolution = timedelta(days=7)
        elif cadence == "monthly":
            values = []
            year = ts.initial_timestamp.year
            day_index = 0
            while day_index < len(daily_values):
                for month in range(1, 13):
                    days = monthrange(year, month)[1]
                    month_values = daily_values[day_index : day_index + days]
                    if not month_values:
                        break
                    values.append(sum(month_values))
                    day_index += len(month_values)
                year += 1
            output_resolution = timedelta(days=30)
        else:
            raise ValueError(f"Unsupported hydro budget resolution: {cadence}")

    return SingleTimeSeries.from_array(
        data=values,
        name=ts.name,
        initial_timestamp=ts.initial_timestamp,
        resolution=output_resolution,
    )


def attach_time_series_to_generators(context: PluginContext) -> None:
    """Transfer time series from ReEDS generators to translated PLEXOS generators (with duplicate check)."""
    from r2x_reeds.models.components import (
        ReEDSGenerator,
        ReEDSHydroGenerator,
        ReEDSVariableGenerator,
    )

    if context.source_system is None or context.target_system is None:
        return

    source_generators = {gen.name: gen for gen in context.source_system.get_components(ReEDSGenerator)}
    hydro_generators = {gen.name: gen for gen in context.source_system.get_components(ReEDSHydroGenerator)}
    variable_generators = {
        gen.name: gen for gen in context.source_system.get_components(ReEDSVariableGenerator)
    }
    trade_generators = {
        gen.name: category
        for gen in context.source_system.get_components(ReEDSGenerator)
        if (category := (getattr(gen, "category", "") or "").casefold()) in {"imports", "exports"}
    }
    target_generators = {gen.name: gen for gen in context.target_system.get_components(PLEXOSGenerator)}

    for name, source_gen in source_generators.items():
        target_gen = target_generators.get(name)
        if target_gen is None:
            continue

        if name in hydro_generators:
            hydro_gen = hydro_generators[name]
            cadence = getattr(context.config, "hydro_budget_ts", "daily")
            source_keys = context.source_system.list_time_series_keys(source_gen)
            for ts_key in source_keys:
                if hydro_gen.is_dispatchable:
                    if ts_key.name not in {"hydro_budget", "max_active_power"}:
                        continue
                elif ts_key.name != "max_active_power":
                    continue

                if ts_key.name == "hydro_budget":
                    target_name = "hydro_budget"
                elif hydro_gen.is_dispatchable:
                    target_name = "max_energy_hour"
                else:
                    target_name = "fixed_load"
                for ts in context.source_system.list_time_series(
                    source_gen,
                    name=ts_key.name,
                    time_series_type=ts_key.time_series_type,
                    **ts_key.features,
                ):
                    if ts_key.name != target_name and context.target_system.has_time_series(
                        target_gen,
                        name=ts_key.name,
                        time_series_type=type(ts),
                        **ts_key.features,
                    ):
                        context.target_system.remove_time_series(
                            target_gen,
                            name=ts_key.name,
                            time_series_type=type(ts),
                            **ts_key.features,
                        )

                    if context.target_system.has_time_series(
                        target_gen,
                        name=target_name,
                        time_series_type=type(ts),
                        **ts_key.features,
                    ):
                        context.target_system.remove_time_series(
                            target_gen,
                            name=target_name,
                            time_series_type=type(ts),
                            **ts_key.features,
                        )

                    if ts_key.name == "hydro_budget":
                        converted_ts = _convert_hydro_budget_time_series(ts, cadence, hydro_gen.capacity)
                    else:
                        converted_ts = deepcopy(ts)
                        converted_ts.name = target_name
                    context.target_system.add_time_series(
                        converted_ts,
                        target_gen,
                        **ts_key.features,
                    )
            continue

        if name in trade_generators:
            target_ext = dict(target_gen.ext or {})
            target_ext["r2x_category"] = trade_generators[name]
            target_gen.ext = target_ext
            for metadata in context.source_system.time_series.list_time_series_metadata(source_gen):
                for ts in context.source_system.list_time_series(
                    source_gen, name=metadata.name, **metadata.features
                ):
                    if not context.target_system.has_time_series(
                        target_gen,
                        name=ts.name,
                        time_series_type=type(ts),
                        **metadata.features,
                    ):
                        context.target_system.add_time_series(deepcopy(ts), target_gen, **metadata.features)
            continue

        if name in variable_generators:
            for ts in context.source_system.list_time_series(source_gen):
                if ts.name == "max_active_power" and not context.target_system.has_time_series(
                    target_gen, name=ts.name, time_series_type=type(ts)
                ):
                    context.target_system.add_time_series(deepcopy(ts), target_gen)


def attach_time_series_to_purchasers(context: PluginContext) -> None:
    """Transfer consuming-demand time series to translated PLEXOS purchasers."""
    if context.source_system is None or context.target_system is None:
        return

    source_demands: dict[str, Any] = {}
    for demand_type in _get_reeds_purchaser_source_types():
        for demand in context.source_system.get_components(demand_type):
            source_demands[demand.name] = demand
    purchaser_type = _get_plexos_purchaser_type()
    target_purchasers = {
        purchaser.name: purchaser for purchaser in context.target_system.get_components(purchaser_type)
    }

    for demand_name, source_demand in source_demands.items():
        target_purchaser = target_purchasers.get(demand_name)
        if target_purchaser is None:
            continue

        for metadata in context.source_system.time_series.list_time_series_metadata(source_demand):
            ts_list = context.source_system.list_time_series(
                source_demand, name=metadata.name, **metadata.features
            )
            if not ts_list:
                logger.warning(
                    "Missing purchaser demand time series {} for {}",
                    metadata.name,
                    source_demand.name,
                )
                continue

            ts = deepcopy(ts_list[0])
            ts_type = ts.__class__
            if not context.target_system.has_time_series(
                target_purchaser,
                name=ts.name,
                time_series_type=ts_type,
                **metadata.features,
            ):
                context.target_system.add_time_series(ts, target_purchaser, **metadata.features)
                logger.debug(
                    "Attached purchaser time series {} to purchaser {}",
                    ts.name,
                    target_purchaser.name,
                )


def _time_series_fingerprint(ts: Any, features: dict[str, Any]) -> str:
    """Return a stable digest of a time series' values, timing, and features."""
    timestamps = getattr(ts, "timestamps", None)
    header = (
        type(ts).__name__,
        sorted((key, type(value).__qualname__, repr(value)) for key, value in features.items()),
        str(getattr(ts, "initial_timestamp", None)),
        str(getattr(ts, "resolution", None)),
        [str(stamp) for stamp in timestamps] if timestamps is not None else [],
    )
    digest = hashlib.sha256(repr(header).encode())
    data = getattr(ts.data, "magnitude", ts.data)
    digest.update(np.ascontiguousarray(np.asarray(data, dtype=float)).tobytes())
    return digest.hexdigest()


def _fuel_price_time_series(system: System, component: Any) -> list[tuple[Any, dict[str, Any]]]:
    """Return every fuel price time series on a component with its features."""
    series: list[tuple[Any, dict[str, Any]]] = []
    for ts_type in FUEL_TS_TYPES:
        for key in system.list_time_series_keys(component, name=FUEL_PRICE_TS_NAME, time_series_type=ts_type):
            series.extend(
                (ts, dict(key.features))
                for ts in system.list_time_series(
                    component, name=key.name, time_series_type=key.time_series_type, **key.features
                )
            )
    return series


def _assign_fuel_names(variants: dict[FuelKey, list[tuple[Any, PLEXOSGenerator]]]) -> dict[FuelKey, str]:
    """Name each fuel variant deterministically.

    A fuel type with a single variant keeps the bare fuel type name; otherwise each
    variant is suffixed with the first region (sorted) that uses it.
    """
    by_type: dict[str, list[FuelKey]] = {}
    for key in variants:
        by_type.setdefault(key[0], []).append(key)

    names: dict[FuelKey, str] = {keys[0]: fuel_type for fuel_type, keys in by_type.items() if len(keys) == 1}
    used: set[str] = set(names.values())
    for fuel_type, keys in sorted(by_type.items()):
        if len(keys) == 1:
            continue

        def first_region(key: FuelKey) -> str:
            return min(str(source_gen.region.name) for source_gen, _ in variants[key])

        for key in sorted(keys, key=lambda k: (first_region(k), k)):
            base = f"{fuel_type}_{first_region(key)}"
            name, index = base, 2
            while name in used:
                name, index = f"{base}_{index}", index + 1
            used.add(name)
            names[key] = name
    return names


def attach_fuels_to_generators(context: PluginContext) -> None:
    """Create PLEXOS Fuel objects from ReEDS fuel data and link generators via Generator.Fuels.

    Fuel price (scalar and time series) is a Fuel object property, so it moves from the
    generator to the Fuel. Heat rate stays on the generator: each generator has a single
    fuel, so no Generator.Fuels membership override is needed.
    """
    from r2x_plexos.models import PLEXOSFuel
    from r2x_reeds.models.components import ReEDSGenerator, ReEDSThermalGenerator

    if context.source_system is None or context.target_system is None:
        return

    source_system = context.source_system
    target_system = context.target_system
    target_generators = {gen.name: gen for gen in target_system.get_components(PLEXOSGenerator)}

    variants: dict[FuelKey, list[tuple[Any, PLEXOSGenerator]]] = {}
    variant_series: dict[FuelKey, list[tuple[Any, dict[str, Any]]]] = {}
    for source_gen in source_system.get_components(ReEDSGenerator):
        # Only these source types map fuel price onto PLEXOSGenerator in rules.json.
        if not isinstance(source_gen, ReEDSThermalGenerator) and type(source_gen) is not ReEDSGenerator:
            continue
        target_gen = target_generators.get(source_gen.name)
        if not source_gen.fuel_type or target_gen is None:
            continue

        series = _fuel_price_time_series(source_system, source_gen)
        key: FuelKey = (
            str(source_gen.fuel_type),
            float(source_gen.fuel_price or 0.0),
            tuple(sorted(_time_series_fingerprint(ts, features) for ts, features in series)),
        )
        variants.setdefault(key, []).append((source_gen, target_gen))
        variant_series.setdefault(key, series)

    names = _assign_fuel_names(variants)
    for key in sorted(variants, key=lambda k: names[k]):
        fuel_type, price, _ = key
        fuel = PLEXOSFuel(name=names[key], category=fuel_type, price=price)
        target_system.add_component(fuel)
        for ts, features in variant_series[key]:
            target_system.add_time_series(deepcopy(ts), fuel, **features)

        for _, target_gen in sorted(variants[key], key=lambda pair: pair[1].name):
            target_gen.fuel_price = 0
            for ts_type in FUEL_TS_TYPES:
                if target_system.has_time_series(
                    target_gen, name=FUEL_PRICE_TS_NAME, time_series_type=ts_type
                ):
                    target_system.remove_time_series(
                        target_gen, name=FUEL_PRICE_TS_NAME, time_series_type=ts_type
                    )
            membership = PLEXOSMembership(
                parent_object=target_gen, child_object=fuel, collection=CollectionEnum.Fuels
            )
            target_system.add_supplemental_attribute(target_gen, membership)
            target_system.add_supplemental_attribute(fuel, membership)
        logger.debug("Linked {} generators to fuel {}", len(variants[key]), fuel.name)


def ensure_region_node_memberships(context: PluginContext) -> None:
    """Ensure every translated region has a node child membership with matching name."""
    system = context.target_system
    if system is None:
        return

    nodes_by_name = {node.name: node for node in system.get_components(PLEXOSNode)}

    for region in system.get_components(PLEXOSRegion):
        node = nodes_by_name.get(region.name)
        if node is None:
            continue
        _ensure_membership(system, node, region, CollectionEnum.Region)


def ensure_generator_node_memberships(context: PluginContext) -> None:
    """Ensure every translated generator has a node membership based on its source region."""
    from r2x_reeds.models import ReEDSGenerator

    if context.source_system is None or context.target_system is None:
        return

    source_generators = {gen.name: gen for gen in context.source_system.get_components(ReEDSGenerator)}
    target_generators = {gen.name: gen for gen in context.target_system.get_components(PLEXOSGenerator)}
    nodes_by_name = {node.name: node for node in context.target_system.get_components(PLEXOSNode)}

    for name, source_gen in source_generators.items():
        target_gen = target_generators.get(name)
        if target_gen is None:
            continue

        # Get the region name from the source generator
        region = getattr(source_gen, "region", None)
        if region is None:
            continue

        # Find corresponding node and create membership if needed
        node = nodes_by_name.get(region.name)
        if node is not None:
            _ensure_membership(context.target_system, target_gen, node, CollectionEnum.Nodes)


def link_line_memberships(context: PluginContext) -> None:
    """Connect translated lines to their originating region nodes."""
    from r2x_reeds.models.components import ReEDSTransmissionLine

    if context.source_system is None or context.target_system is None:
        return

    source_lines = {line.name: line for line in context.source_system.get_components(ReEDSTransmissionLine)}
    nodes_by_name = {node.name: node for node in context.target_system.get_components(PLEXOSNode)}

    for plexos_line in context.target_system.get_components(PLEXOSLine):
        source_line = source_lines.get(plexos_line.name)
        if not source_line or not source_line.interface:
            continue

        from_node = nodes_by_name.get(source_line.interface.from_region.name)
        to_node = nodes_by_name.get(source_line.interface.to_region.name)
        if from_node is None or to_node is None:
            continue

        _ensure_membership(context.target_system, from_node, plexos_line, CollectionEnum.NodeFrom)
        _ensure_membership(context.target_system, to_node, plexos_line, CollectionEnum.NodeTo)


def attach_emissions_to_generators(context: PluginContext) -> None:
    """Copy ReEDS emission metadata onto translated generators."""
    from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator

    if context.source_system is None or context.target_system is None:
        return

    source_generators = {gen.name: gen for gen in context.source_system.get_components(ReEDSGenerator)}
    target_generators = {gen.name: gen for gen in context.target_system.get_components(PLEXOSGenerator)}

    for name, plexos_gen in target_generators.items():
        source_gen = source_generators.get(name)
        if not source_gen:
            continue
        emissions = context.source_system.get_supplemental_attributes_with_component(
            source_gen, ReEDSEmission
        )
        for emission in emissions:
            context.target_system.add_supplemental_attribute(plexos_gen, emission.model_copy())


def convert_pumped_storage_generators(context: PluginContext) -> None:
    """Ensure pumped-storage generators also exist as storage components."""
    from r2x_reeds.models.components import ReEDSGenerator

    if context.source_system is None or context.target_system is None:
        return

    source_generators = {gen.name: gen for gen in context.source_system.get_components(ReEDSGenerator)}
    pumped_names = {
        name
        for name, gen in source_generators.items()
        if getattr(gen, "technology", "").lower() in PUMPED_STORAGE_TECHS
    }
    if not pumped_names:
        return

    target_generators = {gen.name: gen for gen in context.target_system.get_components(PLEXOSGenerator)}
    target_storages = {
        storage.name: storage for storage in context.target_system.get_components(PLEXOSStorage)
    }
    for name in pumped_names:
        source_gen = source_generators[name]
        generator = target_generators.get(name)
        storage = target_storages.get(name)
        if storage is None:
            storage = PLEXOSStorage(name=source_gen.name, category=source_gen.technology)
            context.target_system.add_component(storage)
            target_storages[name] = storage

        if generator is None:
            continue

        _ensure_membership(context.target_system, generator, storage, CollectionEnum.Storages)


def _ensure_membership(system: System, parent: Any, child: Any, collection: CollectionEnum) -> None:
    """Attach a membership if one does not already exist."""
    existing = system.get_supplemental_attributes_with_component(child, PLEXOSMembership)
    for membership in existing:
        if membership.parent_object == parent and membership.collection == collection:
            return

    membership = PLEXOSMembership(parent_object=parent, child_object=child, collection=collection)
    system.add_supplemental_attribute(parent, membership)
    system.add_supplemental_attribute(child, membership)


PUMPED_STORAGE_TECHS = {"pumped-hydro", "pumped_storage"}
