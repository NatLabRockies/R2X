"""End-to-end tests for the reeds_to_plexos translation entry point."""

from __future__ import annotations

from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSReserve,
)
from r2x_reeds.models import (
    FromTo_ToFrom,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSReserve,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSTransmissionLine,
    ReEDSVariableGenerator,
)
from r2x_reeds.models.enums import ReserveDirection, ReserveType
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig
from r2x_reeds_to_plexos.translation import reeds_to_plexos

from r2x_core import System


def _build_source_system():
    """Build a minimal ReEDS source system with various component types."""
    source = System(name="reeds-source", auto_add_composed_components=True)

    r1 = ReEDSRegion(name="p1", transmission_region="WECC")
    r2 = ReEDSRegion(name="p2", transmission_region="WECC")
    source.add_component(r1)
    source.add_component(r2)

    gen = ReEDSThermalGenerator(
        name="gas-cc_p1",
        category="gas-cc",
        region=r1,
        technology="gas-cc",
        capacity=100.0,
        heat_rate=9.5,
        fuel_type="gas",
    )
    source.add_component(gen)

    vre = ReEDSVariableGenerator(
        name="wind_p1",
        category="wind-ons",
        region=r1,
        technology="wind-ons",
        capacity=75.0,
    )
    source.add_component(vre)

    storage = ReEDSStorage(
        name="battery_p1",
        category="battery",
        region=r1,
        technology="battery",
        capacity=50.0,
        storage_duration=4.0,
        round_trip_efficiency=0.85,
    )
    source.add_component(storage)

    iface = ReEDSInterface(name="p1_p2", from_region=r1, to_region=r2)
    source.add_component(iface)

    line = ReEDSTransmissionLine(
        name="line_p1_p2",
        interface=iface,
        max_active_power=FromTo_ToFrom(from_to=150.0, to_from=150.0),
    )
    source.add_component(line)

    reserve = ReEDSReserve(
        name="spin_up",
        reserve_type=ReserveType.SPINNING,
        direction=ReserveDirection.UP,
    )
    source.add_component(reserve)

    return source


def test_reeds_to_plexos_returns_system():
    source = _build_source_system()
    result = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    assert isinstance(result, System)
    assert result.name == "PLEXOS"


def test_reeds_to_plexos_translates_region_to_node():
    source = _build_source_system()
    result = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    nodes = list(result.get_components(PLEXOSNode))
    node_names = {n.name for n in nodes}
    assert "p1" in node_names
    assert "p2" in node_names


def test_reeds_to_plexos_translates_thermal_generator():
    source = _build_source_system()
    result = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    generators = list(result.get_components(PLEXOSGenerator))
    gen_names = {g.name for g in generators}
    assert "gas-cc_p1" in gen_names


def test_reeds_to_plexos_translates_variable_generator():
    source = _build_source_system()
    result = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    generators = list(result.get_components(PLEXOSGenerator))
    gen_names = {g.name for g in generators}
    assert "wind_p1" in gen_names


def test_reeds_to_plexos_translates_storage():
    source = _build_source_system()
    result = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    batteries = list(result.get_components(PLEXOSBattery))
    assert any(b.name == "battery_p1" for b in batteries)


def test_reeds_to_plexos_translates_line():
    source = _build_source_system()
    result = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    lines = list(result.get_components(PLEXOSLine))
    assert any(ln.name == "line_p1_p2" for ln in lines)


def test_reeds_to_plexos_translates_reserve():
    source = _build_source_system()
    result = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    reserves = list(result.get_components(PLEXOSReserve))
    assert any(r.name == "spin_up" for r in reserves)


def test_reeds_to_plexos_translates_interface():
    source = _build_source_system()
    result = reeds_to_plexos(source, config=ReedsToPlexosConfig())

    interfaces = list(result.get_components(PLEXOSInterface))
    assert len(interfaces) >= 1
