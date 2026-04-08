"""Fixtures for getters_utils testing.

Provides test data and fixtures for multiband heat rate and markup conversion tests.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def two_band_load_points() -> list[float]:
    """Load points for a 2-band piecewise linear curve."""
    return [60.0, 120.0]


@pytest.fixture
def two_band_heat_rate_slopes() -> list[float]:
    """Heat rate slopes for a 2-band piecewise linear fuel curve."""
    return [12.0, 13.0]


@pytest.fixture
def two_band_markup_slopes() -> list[float]:
    """Markup slopes for a 2-band piecewise linear VOM cost curve."""
    return [13.0, 16.0]


@pytest.fixture
def three_band_load_points() -> list[float]:
    """Load points for a 3-band piecewise linear curve."""
    return [30.0, 60.0, 90.0]


@pytest.fixture
def three_band_heat_rate_slopes() -> list[float]:
    """Heat rate slopes for a 3-band piecewise linear fuel curve."""
    return [11.5, 12.0, 13.5]


@pytest.fixture
def three_band_markup_slopes() -> list[float]:
    """Markup slopes for a 3-band piecewise linear VOM cost curve."""
    return [12.0, 14.0, 17.0]


@pytest.fixture
def single_band_load_points() -> list[float]:
    """Load points for a single-band curve."""
    return [100.0]


@pytest.fixture
def single_band_heat_rate_slope() -> list[float]:
    """Heat rate slope for a single-band fuel curve."""
    return [12.5]


@pytest.fixture
def empty_load_points() -> list[float]:
    """Empty load points list."""
    return []


@pytest.fixture
def empty_slopes() -> list[float]:
    """Empty slopes list."""
    return []
