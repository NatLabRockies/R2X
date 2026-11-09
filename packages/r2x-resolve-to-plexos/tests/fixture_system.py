"""A small Resolve system built from real r2x-resolve components."""

from __future__ import annotations

from datetime import datetime, timedelta

from infrasys.time_series_models import NonSequentialTimeSeries, SingleTimeSeries
from r2x_resolve import (
    ReserveDirection,
    ResolveBatteryStorage,
    ResolveFuelPrice,
    ResolveFuelType,
    ResolveGenerator,
    ResolveGeneratorFuel,
    ResolveGroupedInterface,
    ResolveInterface,
    ResolveLoad,
    ResolvePrimeMover,
    ResolvePumpedStorage,
    ResolveReserve,
    ResolveTechnology,
    ResolveTransmissionLine,
    ResolveTransmissionRating,
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

    tech, fuel, mover = ResolveTechnology, ResolveFuelType, ResolvePrimeMover
    existing = {"vintage": "existing"}
    for name, zone, technology, fuel_type, prime_mover, capacity, ext in (
        (
            "J:Gas_CCGT",
            zone_j,
            tech.GAS_FO,
            fuel.NATURAL_GAS,
            mover.CC,
            500,
            {**existing, "resource_type": "Gas_CCGT"},
        ),
        (
            "J:FO_ST",
            zone_j,
            tech.GAS_FO,
            fuel.FUEL_OIL,
            mover.ST,
            100,
            {**existing, "resource_type": "FO_ST"},
        ),
        ("J:FO_CT", zone_j, tech.GAS_FO, fuel.FUEL_OIL, mover.CT, 40, {**existing, "resource_type": "FO_CT"}),
        ("J:Gas & FO:new", zone_j, tech.GAS_FO, fuel.GAS_FUEL_OIL, mover.MIXED, 50, {"vintage": "new"}),
        (
            "A:Gas_CT:converted",
            zone_a,
            tech.ZERO_CARBON_FIRM,
            fuel.RNG,
            mover.UNKNOWN,
            80,
            {"vintage": "converted", "resource_type": "Gas_CT", "converted_from": "Gas_CT"},
        ),
        (
            "A:Nuclear",
            zone_a,
            tech.NUCLEAR,
            fuel.URANIUM,
            mover.UNKNOWN,
            1000,
            {**existing, "resource_type": "Nuclear"},
        ),
        ("A:Solar", zone_a, tech.SOLAR, fuel.SOLAR, mover.PV, 200, {}),
        ("J:Wind", zone_j, tech.WIND, fuel.WIND, mover.WT, 0, {}),
        ("J:Offshore Wind", zone_j, tech.OFFSHORE_WIND, fuel.WIND, mover.WT, 300, {}),
    ):
        system.add_component(
            ResolveGenerator(
                name=name,
                zone=zone,
                technology=technology,
                fuel_type=fuel_type,
                prime_mover_type=prime_mover,
                capacity=capacity,
                ext=ext,
            )
        )
    system.add_component(ResolveBatteryStorage(name="A:Battery Storage", zone=zone_a, capacity=20))
    system.add_component(ResolvePumpedStorage(name="A:Pumped Storage", zone=zone_a, capacity=30))
    system.add_time_series(
        _series("max_active_power", [0.0, 50.0, 120.0]), system.get_component(ResolveGenerator, "A:Solar")
    )

    for zone, demand in ((zone_a, [900.0, 950.0, 1000.0]), (zone_j, [4000.0, 4100.0, 4200.0])):
        load = ResolveLoad(name=f"{zone.name}:load", zone=zone, demand=max(demand))
        system.add_component(load)
        system.add_time_series(_series("demand", demand), load)
        system.add_time_series(_series("distributed_pv", [0.0, 10.0, 20.0]), load)

    # NYISO-wide reserves sized from the summed demand above (4900, 5050, 5200 MW).
    for name, direction, share in (
        ("Spin", ReserveDirection.UP, 0.01),
        ("Regulation Down", ReserveDirection.DOWN, 0.005),
    ):
        requirement = [share * mw for mw in (4900.0, 5050.0, 5200.0)]
        reserve = ResolveReserve(
            name=name,
            direction=direction,
            load_percent=share,
            requirement=max(requirement),
            ext={"zones": ["A", "J"]},
        )
        system.add_component(reserve)
        system.add_time_series(_series("requirement", requirement), reserve)

    prices = {}
    for name, fuel_type, price, zones in (
        ("NG_NYISO_A-E", fuel.NATURAL_GAS, 3.86, list("ABCDE")),
        ("NG_NYISO_J", fuel.NATURAL_GAS, 4.99, ["J"]),
        ("DFO_NYISO_J", fuel.FUEL_OIL, 19.75, ["J"]),
        ("RFO_NYISO_J", fuel.FUEL_OIL, 12.42, ["J"]),
        ("RNG_Tier_1", fuel.RNG, 29.87, []),
        ("RNG_Tier_2", fuel.RNG, 35.10, []),
        ("Nuclear", fuel.URANIUM, 0.72, []),
    ):
        fuel_price = ResolveFuelPrice(name=name, fuel_type=fuel_type, price=price, ext={"zones": zones})
        system.add_component(fuel_price)
        prices[name] = fuel_price
        system.add_time_series(
            NonSequentialTimeSeries.from_array(
                [round(price * (0.9 + month / 60), 4) for month in range(1, 13)],
                timestamps=[datetime(2025, month, 1) for month in range(1, 13)],
                name="fuel_price",
            ),
            fuel_price,
        )

    # One link per fuel each generator burns, as the r2x-resolve parser builds them.
    for generator_name, fuel_names in (
        ("J:Gas_CCGT", ["NG_NYISO_J"]),
        ("J:FO_ST", ["RFO_NYISO_J"]),
        ("J:FO_CT", ["DFO_NYISO_J"]),
        ("J:Gas & FO:new", ["NG_NYISO_J", "DFO_NYISO_J", "RFO_NYISO_J"]),
        ("A:Gas_CT:converted", ["RNG_Tier_1", "RNG_Tier_2"]),
        ("A:Nuclear", ["Nuclear"]),
    ):
        generator = system.get_component(ResolveGenerator, generator_name)
        for fuel_name in fuel_names:
            system.add_component(
                ResolveGeneratorFuel(
                    name=f"{generator_name}:{fuel_name}", generator=generator, fuel_price=prices[fuel_name]
                )
            )

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
