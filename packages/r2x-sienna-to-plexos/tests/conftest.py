"""Test configuration for r2x-sienna-to-plexos package tests."""

from __future__ import annotations

import pytest
from loguru import logger

pytest_plugins = [
    "fixtures.configs",
    "fixtures.context",
    "fixtures.five_bus_systems",
    "fixtures.getters_utils",
    "fixtures.rules",
    "fixtures.systems",
    "fixtures.time_series",
]


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
