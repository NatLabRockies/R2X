from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db

from r2x_core import Rule, System, TranslationContext, apply_rules_to_context

from .getters_utils import (
    ensure_battery_node_memberships,
    ensure_generator_node_memberships,
    ensure_head_storage_generator_membership,
    ensure_interface_line_memberships,
    ensure_node_zone_memberships,
    ensure_region_node_memberships,
    ensure_reserve_battery_memberships,
    ensure_reserve_generator_memberships,
    ensure_tail_storage_generator_membership,
    ensure_transformer_node_memberships,
)
from .plugin_config import SiennaToPlexosConfig

if TYPE_CHECKING:
    from r2x_core import TranslationContext


def perform_translation(system: System) -> System:
    """
    Perform the Sienna to PLEXOS translation.

    Args:
        system: The input Sienna system to be translated.

    Returns:
        The translated PLEXOS system.
    """
    rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    # Get time series directory from source system
    source_ts_dir = system.time_series_manager.time_series_directory

    # Create time series manager for target system
    connection = create_in_memory_db()
    ts_manager = TimeSeriesManager(
        connection,
        time_series_directory=source_ts_dir,
        time_series_storage_type=TimeSeriesStorageType.ARROW,
        permanent=True,
    )

    plexos_system = System(
        name="PLEXOS",
        auto_add_composed_components=True,
        time_series_manager=ts_manager,
    )

    context = TranslationContext(
        source_system=system,
        target_system=plexos_system,
        config=SiennaToPlexosConfig(),
        rules=rules,
    )

    apply_rules_to_context(context)

    # Apply membership utilities
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
