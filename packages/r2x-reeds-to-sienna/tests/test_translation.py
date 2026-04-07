"""End-to-end tests for the reeds_to_sienna translation entry point."""

from __future__ import annotations

from r2x_reeds.models import (
    FromTo_ToFrom,
    ReEDSDemand,
    ReEDSHydroGenerator,
    ReEDSInterface,
    ReEDSRegion,
    ReEDSReserve,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSTransmissionLine,
    ReEDSVariableGenerator,
)
from r2x_reeds.models.enums import ReserveDirection, ReserveType
from r2x_reeds_to_sienna.plugin_config import ReEDSToSiennaConfig
from r2x_reeds_to_sienna.translation import reeds_to_sienna
from r2x_sienna.models import (
    ACBus,
    Area,
    AreaInterchange,
    EnergyReservoirStorage,
    HydroDispatch,
    Line,
    PowerLoad,
    RenewableDispatch,
    ThermalStandard,
    VariableReserve,
)

from r2x_core import System


def _build_source_system():
    """Build a minimal ReEDS source system with various component types."""
    source = System(name="reeds-source", auto_add_composed_components=True)

    r1 = ReEDSRegion(name="p1")
    r2 = ReEDSRegion(name="p2")
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
        name="wind-ons_p1",
        category="wind-ons",
        region=r1,
        technology="wind-ons",
        capacity=75.0,
    )
    source.add_component(vre)

    hydro = ReEDSHydroGenerator(
        name="hydro_p1",
        category="hydro",
        region=r1,
        technology="hydro",
        capacity=50.0,
        is_dispatchable=True,
    )
    source.add_component(hydro)

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

    demand = ReEDSDemand(name="load_p1", region=r1, max_active_power=500.0)
    source.add_component(demand)

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


def test_reeds_to_sienna_returns_system():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    assert isinstance(result, System)
    assert result.name == "Sienna"


def test_reeds_to_sienna_translates_region_to_bus():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    buses = list(result.get_components(ACBus))
    bus_names = {b.name for b in buses}
    assert any("p1" in name for name in bus_names)
    assert any("p2" in name for name in bus_names)


def test_reeds_to_sienna_translates_region_to_area():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    areas = list(result.get_components(Area))
    area_names = {a.name for a in areas}
    assert "p1" in area_names


def test_reeds_to_sienna_translates_thermal_generator():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    thermals = list(result.get_components(ThermalStandard))
    assert any(t.name == "gas-cc_p1" for t in thermals)


def test_reeds_to_sienna_translates_wind_to_renewable_dispatch():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    renewables = list(result.get_components(RenewableDispatch))
    assert any(r.name == "wind-ons_p1" for r in renewables)


def test_reeds_to_sienna_translates_hydro():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    hydros = list(result.get_components(HydroDispatch))
    assert any(h.name == "hydro_p1" for h in hydros)


def test_reeds_to_sienna_translates_storage():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    storages = list(result.get_components(EnergyReservoirStorage))
    assert any(s.name == "battery_p1" for s in storages)


def test_reeds_to_sienna_translates_demand_to_load():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    loads = list(result.get_components(PowerLoad))
    assert any(ld.name == "load_p1" for ld in loads)


def test_reeds_to_sienna_translates_line():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    lines = list(result.get_components(Line))
    assert any(ln.name == "line_p1_p2" for ln in lines)


def test_reeds_to_sienna_translates_reserve():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    reserves = list(result.get_components(VariableReserve))
    assert any(r.name == "spin_up" for r in reserves)


def test_reeds_to_sienna_translates_interface():
    source = _build_source_system()
    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    interchanges = list(result.get_components(AreaInterchange))
    assert any(i.name == "p1_p2" for i in interchanges)
