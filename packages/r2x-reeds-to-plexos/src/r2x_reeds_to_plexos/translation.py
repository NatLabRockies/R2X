from __future__ import annotations

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db

from r2x_core import PluginContext, System, apply_rules_to_context

from .getters_utils import (
    attach_region_load_time_series,
    attach_reserve_time_series,
    attach_time_series_to_generators,
)


def perform_translation(context: PluginContext) -> System:
    """
    Perform the ReEDS to PLEXOS translation.

    Args:
        context: PluginContext with source_system, config, and rules set.

    Returns:
        The translated PLEXOS system.
    """
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
    attach_reserve_time_series(context)
    attach_time_series_to_generators(context)
    attach_region_load_time_series(context)

    return context.target_system
