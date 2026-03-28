from __future__ import annotations

import json
from importlib.resources import files

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db

from r2x_core import PluginContext, Rule, System, apply_rules_to_context

from .getters_utils import (
    ensure_battery_node_memberships,
    ensure_generator_node_memberships,
    ensure_generator_time_series,
    ensure_head_storage_generator_membership,
    ensure_interface_line_memberships,
    ensure_node_zone_memberships,
    ensure_region_node_memberships,
    ensure_reserve_battery_memberships,
    ensure_reserve_generator_memberships,
    ensure_tail_storage_generator_membership,
    ensure_transformer_node_memberships,
)


def perform_translation(context: PluginContext) -> System:
    """
    Perform the Sienna to PLEXOS translation.

    Args:
        system: The input Sienna system to be translated.

    Returns:
        The translated PLEXOS system.
    """
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))
    context.rules = rules

    tmp_ts_dir = context.source_system.get_time_series_directory()
    connection = create_in_memory_db()
    ts_manager = TimeSeriesManager(
        connection,
        time_series_directory=tmp_ts_dir,
        time_series_storage_type=TimeSeriesStorageType.ARROW,
        permanent=True,
    )

    plexos_system = System(name="PLEXOS", auto_add_composed_components=True, time_series_manager=ts_manager)
    context.target_system = plexos_system

    apply_rules_to_context(context)
    ensure_generator_time_series(context)
    ensure_region_node_memberships(context)
    ensure_generator_node_memberships(context)
    ensure_battery_node_memberships(context)
    ensure_node_zone_memberships(context)
    ensure_reserve_battery_memberships(context)
    ensure_reserve_generator_memberships(context)
    ensure_transformer_node_memberships(context)
    ensure_interface_line_memberships(context)
    ensure_head_storage_generator_membership(context)
    ensure_tail_storage_generator_membership(context)

    return context.target_system
