"""Test configuration for r2x-sienna-to-plexos package tests."""

from __future__ import annotations

import pytest
from loguru import logger


@pytest.fixture
def caplog(caplog):
    from r2x_core.logger import setup_logging

    try:
        setup_logging(level="TRACE", module="r2x_sienna_to_plexos", tracing=True)
    except TypeError:
        # Backward-compatible fallback for older setup_logging signatures.
        setup_logging()

    yield caplog
    logger.remove()


@pytest.fixture(autouse=True)
def core_time_series_legacy_hook(monkeypatch):
    import r2x_core.time_series as time_series

    if not hasattr(time_series, "_setup_target_and_child_tables"):
        monkeypatch.setattr(
            time_series,
            "_setup_target_and_child_tables",
            time_series.create_target_and_child_tables,
            raising=False,
        )
