import os

os.environ["LOGURU_LEVEL"] = "TRACE"

import pytest
from loguru import logger

pytest_plugins = [
    "tests.fixtures.time_series",
    "tests.fixtures.systems",
    "tests.fixtures.rules",
    "tests.fixtures.context",
    "tests.fixtures.configs",
    "tests.fixtures.getters_utils",
    "tests.fixtures.five_bus_systems",
    "tests.fixtures.reeds_systems",
]


@pytest.fixture
def caplog(caplog):
    from r2x_core.logger import setup_logging

    setup_logging(level="TRACE", module="r2x_sienna_to_plexos", tracing=True)
    setup_logging(level="TRACE", module="r2x_plexos_to_sienna", tracing=True)

    yield caplog
    logger.remove()
