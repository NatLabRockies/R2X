"""Translation steps the one-to-one rules cannot express."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from infrasys.time_series_models import NonSequentialTimeSeries
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSFuel,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSRegion,
)
from r2x_resolve import InvestmentComponent, ResolveFuel, ResolveGroupedInterface, ResolveLoad

if TYPE_CHECKING:
    from r2x_core import PluginContext, System

# Region Load is net of distributed PV, so only the demand series carries over.
LOAD_SERIES = "demand"
# Wind and solar output profiles, written by the PLEXOS exporter as Rating.
PROFILE_SERIES = "max_active_power"
# Monthly fuel prices at their own dates, written by the PLEXOS exporter as Price.
FUEL_PRICE_SERIES = "fuel_price"


def _systems(context: PluginContext) -> tuple[System, System]:
    assert context.source_system is not None
    assert context.target_system is not None
    return context.source_system, context.target_system


def attach_region_load(context: PluginContext) -> None:
    """Attach each zone's hourly demand to its Region."""
    source, target = _systems(context)
    regions = {region.name: region for region in target.get_components(PLEXOSRegion)}
    for load in source.get_components(ResolveLoad):
        if source.has_time_series(load, name=LOAD_SERIES):
            series = source.get_time_series(load, name=LOAD_SERIES)
            target.add_time_series(deepcopy(series), regions[load.zone.name])


def attach_generator_profiles(context: PluginContext) -> None:
    """Attach wind and solar output profiles to their Generators."""
    source, target = _systems(context)
    generators = {generator.name: generator for generator in target.get_components(PLEXOSGenerator)}
    for unit in source.get_components(InvestmentComponent):
        if source.has_time_series(unit, name=PROFILE_SERIES):
            series = source.get_time_series(unit, name=PROFILE_SERIES)
            target.add_time_series(deepcopy(series), generators[unit.name])


def attach_fuel_prices(context: PluginContext) -> None:
    """Attach each fuel's monthly price series to its Fuel."""
    source, target = _systems(context)
    fuels = {fuel.name: fuel for fuel in target.get_components(PLEXOSFuel)}
    for fuel in source.get_components(ResolveFuel):
        if source.has_time_series(fuel, name=FUEL_PRICE_SERIES, time_series_type=NonSequentialTimeSeries):
            series = source.get_time_series(
                fuel, name=FUEL_PRICE_SERIES, time_series_type=NonSequentialTimeSeries
            )
            target.add_time_series(deepcopy(series), fuels[fuel.name])


def add_interface_lines(context: PluginContext) -> None:
    """Add each grouped interface's member Lines; a Line may sit in several interfaces."""
    source, target = _systems(context)
    interfaces = {interface.name: interface for interface in target.get_components(PLEXOSInterface)}
    lines = {line.name: line for line in target.get_components(PLEXOSLine)}
    for group in source.get_components(ResolveGroupedInterface):
        interface = interfaces[group.name]
        for member in group.lines:
            line = lines[member.name]
            membership = PLEXOSMembership(
                parent_object=interface, child_object=line, collection=CollectionEnum.Lines
            )
            target.add_supplemental_attribute(interface, membership)
            target.add_supplemental_attribute(line, membership)
