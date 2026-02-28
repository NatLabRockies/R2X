"""Utility helpers for ReEDS → PLEXOS translation."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

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


def attach_region_load_time_series(context: PluginContext) -> None:
    """Attach demand load and time series from ReEDSDemand to the translated PLEXOSRegion."""
    from r2x_plexos.models import PLEXOSRegion
    from r2x_reeds.models.components import ReEDSDemand

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

    source_reserves = {r.name: r for r in context.source_system.get_components(ReEDSReserve)}
    for reserve in context.target_system.get_components(PLEXOSReserve):
        source_reserve = source_reserves.get(reserve.name)
        if source_reserve is None:
            continue

        if context.source_system.has_time_series(source_reserve):
            ts_list = context.source_system.list_time_series(source_reserve)
            for ts in ts_list:
                context.target_system.add_time_series(deepcopy(ts), reserve)


def attach_time_series_to_generators(context: PluginContext) -> None:
    """Transfer time series from ReEDS generators to translated PLEXOS generators (with duplicate check)."""
    from r2x_reeds.models.components import ReEDSGenerator, ReEDSHydroGenerator, ReEDSVariableGenerator

    source_generators = {gen.name: gen for gen in context.source_system.get_components(ReEDSGenerator)}
    hydro_generators = {gen.name: gen for gen in context.source_system.get_components(ReEDSHydroGenerator)}
    variable_generators = {
        gen.name: gen for gen in context.source_system.get_components(ReEDSVariableGenerator)
    }
    target_generators = {gen.name: gen for gen in context.target_system.get_components(PLEXOSGenerator)}

    for name, source_gen in source_generators.items():
        target_gen = target_generators.get(name)
        if target_gen is None:
            continue

        if name in hydro_generators:
            for ts in context.source_system.list_time_series(source_gen):
                if ts.name == "hydro_budget" and not context.target_system.has_time_series(
                    target_gen, name=ts.name, time_series_type=type(ts)
                ):
                    context.target_system.add_time_series(deepcopy(ts), target_gen)
            continue

        if name in variable_generators:
            for ts in context.source_system.list_time_series(source_gen):
                if ts.name == "max_active_power" and not context.target_system.has_time_series(
                    target_gen, name=ts.name, time_series_type=type(ts)
                ):
                    context.target_system.add_time_series(deepcopy(ts), target_gen)
            continue


def ensure_region_node_memberships(context: PluginContext) -> None:
    """Ensure every translated region has a node child membership with matching name."""
    system = context.target_system
    nodes_by_name = {node.name: node for node in system.get_components(PLEXOSNode)}

    for region in system.get_components(PLEXOSRegion):
        node = nodes_by_name.get(region.name)
        if node is None:
            continue
        _ensure_membership(system, node, region, CollectionEnum.Region)


def ensure_generator_node_memberships(context: PluginContext) -> None:
    """Ensure every translated generator has a node membership based on its source region."""
    from r2x_reeds.models import ReEDSGenerator

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

    source_lines = {line.name: line for line in context.source_system.get_components(ReEDSTransmissionLine)}
    nodes_by_name = {node.name: node for node in context.target_system.get_components(PLEXOSNode)}

    for plexos_line in context.target_system.get_components(PLEXOSLine):
        source_line = source_lines.get(plexos_line.name)
        if not source_line or not source_line.interface:
            continue

        from_node = nodes_by_name.get(source_line.interface.from_region.name)
        to_node = nodes_by_name.get(source_line.interface.to_region.name)
        if not from_node or not to_node:
            continue

        _ensure_membership(context.target_system, from_node, plexos_line, CollectionEnum.NodeFrom)
        _ensure_membership(context.target_system, to_node, plexos_line, CollectionEnum.NodeTo)


def attach_emissions_to_generators(context: PluginContext) -> None:
    """Copy ReEDS emission metadata onto translated generators."""
    from r2x_reeds.models.components import ReEDSEmission, ReEDSGenerator

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
