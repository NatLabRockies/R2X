from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db

from r2x_core import PluginContext, Rule, System, apply_rules_to_context, expose_plugin
from r2x_reeds_to_sienna.plugin_config import ReEDSToSiennaConfig


@expose_plugin
def reeds_to_sienna(system: System, config: ReEDSToSiennaConfig) -> System:
    """
    Perform the ReEDS to Sienna translation.

    Args:
        system: The input ReEDS system to be translated.

    Returns:
        The translated Sienna system.
    """
    context = PluginContext(source_system=system, config=config)
    rules_path = files("r2x_reeds_to_sienna.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))
    context.rules = rules

    source_system = cast(Any, context.source_system)
    tmp_ts_dir = source_system.get_time_series_directory()
    connection = create_in_memory_db()
    ts_manager = TimeSeriesManager(
        connection,
        time_series_directory=tmp_ts_dir,
        time_series_storage_type=TimeSeriesStorageType.ARROW,
        permanent=True,
    )

    sienna_system = System(name="Sienna", auto_add_composed_components=True, time_series_manager=ts_manager)
    context.target_system = sienna_system

    apply_rules_to_context(context)

    return context.target_system
