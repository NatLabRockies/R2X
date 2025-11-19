"""Compact ReEDS fixture with multiple regions and generator types."""

from __future__ import annotations

import pytest
from r2x_reeds.models.components import ReEDSGenerator, ReEDSRegion

from r2x_core import System


@pytest.fixture
def reeds_system_example(vre_single_time_series) -> System:
    """Single ReEDS system containing three regions and four generator types."""
    system = System(name="reeds_example", auto_add_composed_components=True)

    regions = [
        ReEDSRegion(name="R_WEST", interconnect="western", transmission_group="west"),
        ReEDSRegion(name="R_EAST", interconnect="eastern", transmission_group="east"),
        ReEDSRegion(name="R_TEXAS", interconnect="texas", transmission_group="ercot"),
    ]
    for region in regions:
        system.add_component(region)

    generators = [
        ReEDSGenerator(
            name="WEST_CC",
            region=regions[0],
            technology="gas-cc",
            capacity=300.0,
            heat_rate=7.0,
            forced_outage_rate=0.04,
        ),
        ReEDSGenerator(
            name="WEST_WIND",
            region=regions[0],
            technology="wind-ons",
            capacity=150.0,
        ),
        ReEDSGenerator(
            name="EAST_COAL",
            region=regions[1],
            technology="coal-new",
            capacity=500.0,
            forced_outage_rate=0.08,
        ),
        ReEDSGenerator(
            name="TEXAS_SOLAR",
            region=regions[2],
            technology="upv",
            capacity=200.0,
        ),
    ]
    for generator in generators:
        system.add_component(generator)

    solar_generators = [gen for gen in generators if gen.technology and "pv" in gen.technology.lower()]
    if solar_generators:
        system.add_time_series(vre_single_time_series, *solar_generators)

    return system
