"""Test configuration for r2x-plexos-to-sienna package tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_plexos_number_state():
    """Reset the global number-extraction state before each test.

    extract_number_from_name uses module-level globals to track assigned bus
    numbers. Without resetting, tests become order-dependent because numbers
    accumulate in PLEXOS_NUMBER_USED across the session.
    """
    import r2x_plexos_to_sienna.getters as g

    g.PLEXOS_NUMBER_COUNTER = g.PLEXOS_NUMBER_BASE
    g.PLEXOS_NUMBER_MAP = {}
    g.PLEXOS_NUMBER_USED = set()
