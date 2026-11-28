from __future__ import annotations

import json
import logging
from collections import Counter
from importlib.resources import files

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSNode,
    PLEXOSPurchaser,
    PLEXOSReserve,
    PLEXOSStorage,
)

from r2x_core import PluginContext, Rule, System, apply_rules_to_context, expose_plugin
from r2x_plexos_to_sienna.plugin_config import PlexosToSiennaConfig
from r2x_plexos_to_sienna.utils import (
    _classify_generator_category_with_fallback,
    _sync_time_series_for_source,
    attach_constant_load_time_series,
    normalize_renewable_max_active_power_time_series,
    normalize_reserve_requirement_time_series,
    prune_region_loads,
    remove_unused_node_loads,
)

logger = logging.getLogger(__name__)


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
    rules = Rule.from_records(json.loads(rules_path.read_text(encoding="utf-8")))
    context.rules = tuple(rules)

    assert context.source_system is not None, "source_system must be set"
    tmp_ts_dir = context.source_system.get_time_series_directory()
    context.source_system.convert_storage(
        time_series_directory=tmp_ts_dir,
        time_series_storage_type=TimeSeriesStorageType.ARROW,
        permanent=True,
    )
    connection = create_in_memory_db()
    ts_manager = TimeSeriesManager(
        connection,
        time_series_directory=tmp_ts_dir,
        time_series_storage_type=TimeSeriesStorageType.ARROW,
        permanent=True,
    )

    # Share one database so supplemental attributes persist with time-series metadata.
    sienna_sys = System(
        name="Sienna",
        system_base=100.0,
        auto_add_composed_components=True,
        con=connection,
        time_series_manager=ts_manager,
    )
    context.target_system = sienna_sys

    generators = list(context.source_system.get_components(PLEXOSGenerator))
    fallback_categories = Counter(
        generator.category
        for generator in generators
        if _classify_generator_category_with_fallback(generator.category)[1]
    )
    if fallback_categories:
        category_counts = ", ".join(
            f"{category!r} ({count} generator{'s' if count != 1 else ''})"
            for category, count in sorted(
                fallback_categories.items(),
                key=lambda item: (item[0] is not None, item[0] or ""),
            )
        )
        logger.warning(
            "Unrecognized PLEXOS generator categories defaulted to 'thermal': %s. "
            "Update the categories or add mappings.",
            category_counts,
        )

    apply_rules_to_context(context)
    prune_region_loads(context)

    for node in context.source_system.get_components(PLEXOSNode):
        _sync_time_series_for_source(node, context)
    for purchaser in context.source_system.get_components(PLEXOSPurchaser):
        _sync_time_series_for_source(purchaser, context)
    for generator in generators:
        _sync_time_series_for_source(generator, context)
    for battery in context.source_system.get_components(PLEXOSBattery):
        _sync_time_series_for_source(battery, context)
    for reserve in context.source_system.get_components(PLEXOSReserve):
        _sync_time_series_for_source(reserve, context)
    for storage in context.source_system.get_components(PLEXOSStorage):
        _sync_time_series_for_source(storage, context)

    remove_unused_node_loads(context)
    attach_constant_load_time_series(context)
    normalize_renewable_max_active_power_time_series(context)
    normalize_reserve_requirement_time_series(context)

    return context.target_system
