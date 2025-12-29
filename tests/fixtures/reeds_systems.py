"""Compact ReEDS fixture with multiple regions and generator types."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_core import System


@pytest.fixture
def reeds_system_example(
    vre_single_time_series, load_single_time_series, wind_single_time_series, hydro_single_time_series
) -> System:
    """Single ReEDS system containing key component families."""
    from r2x_reeds.models import (
        EmissionType,
        FromTo_ToFrom,
        FuelType,
        ReEDSDemand,
        ReEDSEmission,
        ReEDSInterface,
        ReEDSRegion,
        ReEDSReserve,
        ReEDSReserveRegion,
        ReEDSStorage,
        ReEDSThermalGenerator,
        ReEDSTransmissionLine,
        ReEDSVariableGenerator,
        ReserveDirection,
        ReserveType,
    )

    from r2x_core import System

    system = System(name="reeds_example", auto_add_composed_components=True)

    regions = [
        ReEDSRegion(name="R_WEST", interconnect="western", transmission_group="west"),
        ReEDSRegion(name="R_EAST", interconnect="eastern", transmission_group="east"),
        ReEDSRegion(name="R_TEXAS", interconnect="texas", transmission_group="ercot"),
    ]
    for region in regions:
        system.add_component(region)

    generators = [
        ReEDSThermalGenerator(
            name="WEST_CC",
            region=regions[0],
            technology="gas-cc",
            capacity=300.0,
            heat_rate=7.0,
            fuel_type=FuelType.NATURAL_GAS,
            forced_outage_rate=0.04,
        ),
        ReEDSVariableGenerator(
            name="WEST_WIND",
            region=regions[0],
            technology="wind-ons",
            capacity=150.0,
        ),
        ReEDSThermalGenerator(
            name="EAST_COAL",
            region=regions[1],
            technology="coal-new",
            capacity=500.0,
            heat_rate=7.0,
            fuel_type=FuelType.COAL,
            forced_outage_rate=0.08,
        ),
        ReEDSVariableGenerator(
            name="TEXAS_SOLAR",
            region=regions[2],
            technology="upv",
            capacity=200.0,
        ),
        ReEDSStorage(
            name="WEST_PSH",
            region=regions[0],
            storage_duration=10,
            technology="pumped-hydro",
            round_trip_efficiency=0.85,
            capacity=250.0,
        ),
        ReEDSStorage(
            name="WEST_BATTERY",
            region=regions[0],
            technology="battery",
            storage_duration=4,
            round_trip_efficiency=0.85,
            category="battery_4h",
            capacity=75.0,
        ),
    ]
    for generator in generators:
        system.add_component(generator)

    solar_generators = [gen for gen in generators if gen.technology and "pv" in gen.technology.lower()]
    if solar_generators:
        system.add_time_series(vre_single_time_series, *solar_generators)

    wind_generators = [gen for gen in generators if gen.technology and "wind" in gen.technology.lower()]
    if wind_generators:
        system.add_time_series(wind_single_time_series, *wind_generators)

    system.add_supplemental_attribute(
        generators[0],
        ReEDSEmission(rate=0.5, type=EmissionType.CO2),
    )

    interface = ReEDSInterface(name="WEST_EAST_IFACE", from_region=regions[0], to_region=regions[1])
    system.add_component(interface)
    system.add_component(
        ReEDSTransmissionLine(
            name="Line_WE",
            interface=interface,
            max_active_power=FromTo_ToFrom(from_to=500.0, to_from=450.0),
            line_type="ac",
        )
    )

    # Regional demand with load profile
    demand = ReEDSDemand(name="Load_West", region=regions[0], max_active_power=650.0)
    system.add_component(demand)
    system.add_time_series(load_single_time_series, demand)

    # Reserve requirement tied to a reserve region
    reserve_region = ReEDSReserveRegion(name="RR_WEST")
    system.add_component(reserve_region)
    system.add_component(
        ReEDSReserve(
            name="SpinningReserve",
            region=reserve_region,
            reserve_type=ReserveType.SPINNING,
            direction=ReserveDirection.UP,
            time_frame=900.0,
            duration=600.0,
            max_requirement=200.0,
        )
    )

    return system
