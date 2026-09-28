"""A small Resolve system built from real r2x-resolve components."""

from __future__ import annotations

from datetime import datetime, timedelta

from infrasys.time_series_models import SingleTimeSeries
from r2x_resolve import (
    ResolveBatteryStorage,
    ResolveFuel,
    ResolveGasFO,
    ResolveGroupedInterface,
    ResolveInterface,
    ResolveLoad,
    ResolveNuclear,
    ResolveSolar,
    ResolveTransmissionLine,
    ResolveTransmissionRating,
    ResolveWind,
    ResolveZeroCarbonFirm,
    ResolveZone,
)

from r2x_core import System

START = datetime(2025, 1, 1)
HOUR = timedelta(hours=1)


def _series(name: str, values: list[float]) -> SingleTimeSeries:
    return SingleTimeSeries.from_array(values, name=name, initial_timestamp=START, resolution=HOUR)


def resolve_system() -> System:
    """Zones A and J plus external PJM_W, with split generators, loads, fuels and lines."""
    system = System(name="resolve", auto_add_composed_components=True)
    zone_a = ResolveZone(name="A")
    zone_j = ResolveZone(name="J")
    pjm_w = ResolveZone(name="PJM_W", ext={"external": True})
    for zone in (zone_a, zone_j, pjm_w):
        system.add_component(zone)

    existing = {"vintage": "existing"}
    for generator in (
        ResolveGasFO(
            name="J:Gas_CCGT", zone=zone_j, capacity=500, ext={**existing, "resource_type": "Gas_CCGT"}
        ),
        ResolveGasFO(name="J:FO_ST", zone=zone_j, capacity=100, ext={**existing, "resource_type": "FO_ST"}),
        ResolveGasFO(name="J:Gas & FO:new", zone=zone_j, capacity=50, ext={"vintage": "new"}),
        ResolveZeroCarbonFirm(
            name="A:Gas_CT:converted",
            zone=zone_a,
            capacity=80,
            ext={"vintage": "converted", "resource_type": "Gas_CT", "converted_from": "Gas_CT"},
        ),
        ResolveNuclear(
            name="A:Nuclear", zone=zone_a, capacity=1000, ext={**existing, "resource_type": "Nuclear"}
        ),
        ResolveSolar(name="A:Solar", zone=zone_a, capacity=200),
        ResolveWind(name="J:Wind", zone=zone_j, capacity=0),
        ResolveBatteryStorage(name="A:Battery Storage", zone=zone_a, capacity=20),
    ):
        system.add_component(generator)
    system.add_time_series(
        _series("max_active_power", [0.0, 50.0, 120.0]), system.get_component(ResolveSolar, "A:Solar")
    )

    for zone, demand in ((zone_a, [900.0, 950.0, 1000.0]), (zone_j, [4000.0, 4100.0, 4200.0])):
        load = ResolveLoad(name=f"{zone.name}:load", zone=zone, demand=max(demand))
        system.add_component(load)
        system.add_time_series(_series("demand", demand), load)
        system.add_time_series(_series("distributed_pv", [0.0, 10.0, 20.0]), load)

    for name, fuel_type, price, zones in (
        ("NG_NYISO_A-E", "NG", 3.86, list("ABCDE")),
        ("NG_NYISO_J", "NG", 4.99, ["J"]),
        ("RFO_NYISO_J", "RFO", 12.42, ["J"]),
        ("RNG_Tier_1", "RNG", 29.87, []),
        ("Nuclear", "Nuclear", 0.72, []),
    ):
        system.add_component(ResolveFuel(name=name, fuel_type=fuel_type, price=price, ext={"zones": zones}))

    lines = {}
    for from_zone, to_zone, from_to, to_from in (
        (zone_a, zone_j, 1000.0, 400.0),
        (zone_j, pjm_w, 315.0, 915.0),
    ):
        interface = ResolveInterface(
            name=f"{from_zone.name}_to_{to_zone.name}", from_zone=from_zone, to_zone=to_zone
        )
        line = ResolveTransmissionLine(
            name=f"{interface.name}:line",
            interface=interface,
            max_active_power=ResolveTransmissionRating(from_to=from_to, to_from=to_from),
        )
        system.add_component(interface)
        system.add_component(line)
        lines[line.name] = line

    directions = {"A_to_J:line": 1, "J_to_PJM_W:line": -1}
    system.add_component(
        ResolveGroupedInterface(
            name="Test East",
            lines=list(lines.values()),
            forward_limit=900.0,
            reverse_limit=None,
            ext={"line_directions": directions},
        )
    )
    return system
