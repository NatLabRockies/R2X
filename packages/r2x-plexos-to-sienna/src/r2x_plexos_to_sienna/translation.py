from __future__ import annotations

import json
from importlib.resources import files

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db

from r2x_core import PluginContext, Rule, System, apply_rules_to_context, expose_plugin
from r2x_plexos_to_sienna.plugin_config import PlexosToSiennaConfig


@expose_plugin
def plexos_to_sienna(system: System, config: PlexosToSiennaConfig) -> System:
    """
    Perform the PLEXOS to Sienna translation.

    Args:
        config: PlexosToSiennaConfig with plugin configuration.

    Returns:
        The translated Sienna system.
    """
    context = PluginContext(source_system=system, config=config)
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))
    context.rules = rules

    assert context.source_system is not None, "source_system must be set"
    tmp_ts_dir = context.source_system.get_time_series_directory()
    connection = create_in_memory_db()
    ts_manager = TimeSeriesManager(
        connection,
        time_series_directory=tmp_ts_dir,
        time_series_storage_type=TimeSeriesStorageType.ARROW,
        permanent=True,
    )

    sienna_sys = System(
        name="Sienna",
        auto_add_composed_components=True,
        time_series_manager=ts_manager,
    )
    context.target_system = sienna_sys

    apply_rules_to_context(context)

    return context.target_system
