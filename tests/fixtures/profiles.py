"""Time series profile generators for test fixtures."""

import datetime
import math
from collections.abc import Iterable

import pytest


def daterange(start_date: datetime.date, days: int) -> Iterable[datetime.date]:
    for n in range(days):
        yield start_date + datetime.timedelta(days=n)


@pytest.fixture
def datetime_single_component_data(tmp_path):
    def _datetime_component_data(
        *component_names: str, start_date: datetime.date, days: int, profile: list[float]
    ):
        if not component_names:
            raise ValueError("At least one component name must be provided.")

        header = "Datetime," + ",".join(component_names) + "\n"
        csv_lines = [header]

        for date in daterange(start_date, days):
            for hour, value in enumerate(profile):
                dt = datetime.datetime.combine(date, datetime.time(hour=hour))
                row = f"{dt.isoformat()}," + ",".join(str(value) for _ in component_names)
                csv_lines.append(row + "\n")

        output_fpath = tmp_path / "datetime_series.csv"
        output_fpath.write_text("".join(csv_lines))
        return output_fpath

    return _datetime_component_data


@pytest.fixture
def example_solar_profile():
    """Generate simple deterministic solar profile (0.0-1.0 sine wave).

    Returns
    -------
    callable
        Function that returns list of floats representing solar capacity factors
    """

    def _generate(hours: int = 23) -> list[float]:
        """Generate solar profile with daily sine wave pattern.

        Profile is zero at night (hours 0-6 and 18-24) and follows sine wave during day.

        Parameters
        ----------
        hours : int
            Number of hourly values to generate

        Returns
        -------
        list[float]
            Solar capacity factors (0.0-1.0)
        """
        profile = []

        for hour in range(hours):
            hour_of_day = hour % 24

            if 6 <= hour_of_day < 18:
                day_hour = hour_of_day - 6
                value = math.sin(math.pi * day_hour / 12)
            else:
                value = 0.0

            profile.append(value)

        return profile

    return _generate


@pytest.fixture
def example_wind_profile():
    """Generate simple deterministic wind profile (0.3-0.9 stepped pattern).

    Returns
    -------
    callable
        Function that returns list of floats representing wind capacity factors
    """

    def _generate(hours: int = 23) -> list[float]:
        """Generate wind profile with stepped pattern.

        Creates 4-step pattern repeating every 24 hours.

        Parameters
        ----------
        hours : int
            Number of hourly values to generate

        Returns
        -------
        list[float]
            Wind capacity factors (0.3-0.9)
        """
        profile = []
        steps = [0.4, 0.7, 0.9, 0.5]

        for hour in range(hours):
            step_index = (hour // 6) % 4
            profile.append(steps[step_index])

        return profile

    return _generate


@pytest.fixture
def generate_load_profile():
    """Generate simple deterministic load profile with daily peaks.

    Returns
    -------
    callable
        Function that returns list of floats representing load in MW
    """

    def _generate(base_mw: float = 100.0, peak_mw: float = 150.0, hours: int = 8784) -> list[float]:
        """Generate load profile with daily peak pattern.

        Profile has morning and evening peaks (hours 8-10 and 18-20).

        Parameters
        ----------
        base_mw : float
            Base load in MW
        peak_mw : float
            Peak load in MW
        hours : int
            Number of hourly values to generate

        Returns
        -------
        list[float]
            Load values in MW
        """
        profile = []

        for hour in range(hours):
            hour_of_day = hour % 24

            if 8 <= hour_of_day < 10 or 18 <= hour_of_day < 20:
                load = peak_mw
            else:
                load = base_mw + (peak_mw - base_mw) * 0.5 * (1 + math.sin(2 * math.pi * hour_of_day / 24))

            profile.append(load)

        return profile

    return _generate


@pytest.fixture
def generate_battery_efficiency_profile():
    """Generate simple constant efficiency profile for batteries.

    Returns
    -------
    callable
        Function that returns list of floats representing round-trip efficiency
    """

    def _generate(efficiency: float = 0.85, hours: int = 8784) -> list[float]:
        """Generate constant efficiency profile.

        Parameters
        ----------
        efficiency : float
            Round-trip efficiency (0.0-1.0)
        hours : int
            Number of hourly values to generate

        Returns
        -------
        list[float]
            Efficiency values (constant)
        """
        return [efficiency] * hours

    return _generate
