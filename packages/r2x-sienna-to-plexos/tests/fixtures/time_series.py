"""Time series fixtures for testing translation of dynamic data."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from infrasys.time_series_models import SingleTimeSeries


VRE_PROFILE = [
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.05,
    0.15,
    0.3,
    0.5,
    0.7,
    0.85,
    0.9,
    0.95,
    0.98,
    1.0,
    0.95,
    0.8,
    0.5,
    0.2,
    0.05,
    0.0,
    0.0,
    0.0,
    0.0,
]


LOAD_PROFILE = [
    0.6,
    0.55,
    0.5,
    0.48,
    0.45,
    0.55,
    0.65,
    0.75,
    0.85,
    0.9,
    0.95,
    0.98,
    1.0,
    0.98,
    0.95,
    0.9,
    0.8,
    0.75,
    0.8,
    0.85,
    0.75,
    0.7,
    0.65,
    0.6,
]


WIND_PROFILE = [
    0.3,
    0.35,
    0.4,
    0.45,
    0.5,
    0.55,
    0.6,
    0.5,
    0.4,
    0.3,
    0.25,
    0.2,
    0.15,
    0.2,
    0.25,
    0.3,
    0.4,
    0.5,
    0.6,
    0.7,
    0.65,
    0.55,
    0.45,
    0.35,
]


HYDRO_PROFILE = [
    0.7,
    0.65,
    0.6,
    0.55,
    0.5,
    0.55,
    0.6,
    0.7,
    0.8,
    0.85,
    0.9,
    0.85,
    0.8,
    0.75,
    0.7,
    0.75,
    0.8,
    0.85,
    0.9,
    0.95,
    0.9,
    0.85,
    0.8,
    0.75,
]


@pytest.fixture
def vre_single_time_series() -> "SingleTimeSeries":
    """Convert solar DataFrame to SingleTimeSeries."""
    from datetime import datetime, timedelta

    from infrasys import SingleTimeSeries

    initial_timestamp = datetime(2025, 1, 1)
    data = VRE_PROFILE

    return SingleTimeSeries.from_array(
        data,
        name="max_active_power",
        initial_timestamp=initial_timestamp,
        resolution=timedelta(hours=1),
    )


@pytest.fixture
def load_single_time_series():
    """Convert load DataFrame to SingleTimeSeries."""
    from datetime import datetime, timedelta

    from infrasys import SingleTimeSeries

    initial_timestamp = datetime(2025, 1, 1)
    data = LOAD_PROFILE
    return SingleTimeSeries.from_array(
        data,
        name="max_active_power",
        initial_timestamp=initial_timestamp,
        resolution=timedelta(hours=1),
    )


@pytest.fixture
def wind_single_time_series() -> "SingleTimeSeries":
    """Wind generation profile."""
    from datetime import datetime, timedelta

    from infrasys import SingleTimeSeries

    initial_timestamp = datetime(2025, 1, 1)
    return SingleTimeSeries.from_array(
        WIND_PROFILE,
        name="max_active_power",
        initial_timestamp=initial_timestamp,
        resolution=timedelta(hours=1),
    )


@pytest.fixture
def hydro_single_time_series() -> "SingleTimeSeries":
    """Hydro generation profile."""
    from datetime import datetime, timedelta

    from infrasys import SingleTimeSeries

    initial_timestamp = datetime(2025, 1, 1)
    return SingleTimeSeries.from_array(
        HYDRO_PROFILE,
        name="max_active_power",
        initial_timestamp=initial_timestamp,
        resolution=timedelta(hours=1),
    )
