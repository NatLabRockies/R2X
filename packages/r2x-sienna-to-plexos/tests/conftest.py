"""Test configuration for r2x-sienna-to-plexos package tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from loguru import logger

# Ensure the package src is importable without requiring installation.
ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

pytest_plugins = [
    "tests.fixtures.time_series",
    "tests.fixtures.systems",
    "tests.fixtures.rules",
    "tests.fixtures.context",
    "tests.fixtures.configs",
    "tests.fixtures.getters_utils",
    "tests.fixtures.five_bus_systems",
]


@pytest.fixture
def caplog(caplog):
    from r2x_core.logger import setup_logging

    setup_logging(level="TRACE", module="r2x_sienna_to_plexos", tracing=True)

    yield caplog
    logger.remove()
