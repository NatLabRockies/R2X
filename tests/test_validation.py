"""Validate translation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_sienna_to_plexos import Rule

    from r2x_core import System


@pytest.fixture
def default_rules() -> list[Rule]:
    import json
    from importlib.resources import files

    from r2x_sienna_to_plexos import Rule

    config_files = files("r2x_sienna_to_plexos.config")
    rules_file = config_files / "rules.json"
    rules_json = json.loads(rules_file.read_text())
    return Rule.from_records(rules_json)


def test_validate_conversion_level_1(system_complete: System, default_rules: list[Rule], caplog):
    import sqlite3

    from infrasys.time_series_manager import TimeSeriesManager
    from r2x_plexos.models import PLEXOSNode
    from r2x_sienna.models import PowerLoad
    from r2x_sienna_to_plexos import SiennaToPlexosConfig, TranslationContext, apply_rules_to_context

    from r2x_core import System

    sys_in = system_complete

    tgt_con = sqlite3.connect(":memory:")
    tgt_ts_mgr = TimeSeriesManager(
        con=tgt_con,
        storage=sys_in.time_series.storage,
        initialize=True,
    )

    sys_out = System(
        name="TargetSystem",
        auto_add_composed_components=True,
        time_series_manager=tgt_ts_mgr,
    )
    config = SiennaToPlexosConfig()
    context = TranslationContext(
        source_system=sys_in, target_system=sys_out, config=config, rules=default_rules
    )

    _ = apply_rules_to_context(context)

    assert any(sys_out.has_time_series(comp) for comp in sys_out.get_components(PLEXOSNode))

    sys_in_ts_keys = [
        (comp, ts_key)
        for comp in sys_in.get_components(PowerLoad)
        if sys_in.has_component(comp)
        for ts_key in sys_in.list_time_series_keys(comp)
    ]

    for comp, key in sys_in_ts_keys:
        sys_in.get_time_series_by_key(comp, key)

    sys_out_comp_ts = list(
        sys_out.get_components(PLEXOSNode, filter_func=lambda comp: sys_out.has_component(comp))
    )

    for component in sys_out_comp_ts:
        assert sys_out.list_time_series_keys(sys_out_comp_ts[0])
        assert sys_out.get_time_series(sys_out_comp_ts[0])
