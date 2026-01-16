from __future__ import annotations

import json
from importlib.resources import files
from typing import TYPE_CHECKING

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db

from r2x_core import Rule, System, TranslationContext, apply_rules_to_context

from .plugin_config import PlexosToSiennaConfig

if TYPE_CHECKING:
    from r2x_core import TranslationContext


def perform_translation(system: System) -> System:
    """
    Perform the PLEXOS to Sienna translation.

    Args:
        system: The input PLEXOS system to be translated.

    Returns:
        The translated Sienna system.
    """
    rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    tmp_ts_dir = system.get_time_series_directory()

    connection = create_in_memory_db()
    ts_manager = TimeSeriesManager(
        connection,
        time_series_directory=tmp_ts_dir,
        time_series_storage_type=TimeSeriesStorageType.ARROW,
        permanent=True,
    )

    sienna_system = System(name="Sienna", auto_add_composed_components=True, time_series_manager=ts_manager)

    context = TranslationContext(
        source_system=system,
        target_system=sienna_system,
        config=PlexosToSiennaConfig(),
        rules=rules,
    )
    apply_rules_to_context(context)

    return context.target_system
