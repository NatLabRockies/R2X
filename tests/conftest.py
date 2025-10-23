"""R2X pytest configuration and fixtures."""

import pathlib
import sys

import pytest
from _pytest.logging import LogCaptureFixture
from loguru import logger

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest_plugins = [
    "fixtures.plexos_systems",
    "fixtures.sienna_systems",
    "fixtures.profiles",
]


@pytest.fixture
def caplog(caplog: LogCaptureFixture):
    """Configure loguru to work with pytest's caplog.

    Parameters
    ----------
    caplog : LogCaptureFixture
        Pytest's log capture fixture

    Yields
    ------
    LogCaptureFixture
        Configured log capture fixture
    """
    handler_id = logger.add(
        caplog.handler,
        format="{message}",
        level=0,
        filter=lambda record: record["level"].no >= caplog.handler.level,
        enqueue=False,
    )
    yield caplog
    logger.remove(handler_id)
