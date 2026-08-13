"""End-to-end tests for the reeds_to_sienna translation entry point."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
from infrasys import SingleTimeSeries
from infrasys.normalization import NormalizationByValue
from r2x_reeds.models import (
    EmissionType,
    FromTo_ToFrom,
    ReEDSDemand,
    ReEDSEmission,
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
    HydroPumpTurbine,
    HydroReservoir,
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
    assert result.base_power == 100.0


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


def test_reeds_to_sienna_normalizes_max_active_power_time_series(monkeypatch):
    source = _build_source_system()
    source_wind = source.get_component(ReEDSVariableGenerator, "wind-ons_p1")
    scaling_calls = []

    def record_scaling_call(system, owner, name, function_name):
        scaling_calls.append((system, owner, name, function_name))

    monkeypatch.setattr(
        "r2x_sienna.exporter.set_time_series_scaling_factor_multiplier",
        record_scaling_call,
    )
    source_profile = SingleTimeSeries.from_array(
        data=[0.0, 37.5, 75.0],
        name="max_active_power",
        initial_timestamp=datetime(2012, 1, 1),
        resolution=timedelta(hours=1),
    )
    source.add_time_series(source_profile, source_wind)

    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    target_wind = result.get_component(RenewableDispatch, "wind-ons_p1")
    target_profile = result.get_time_series(target_wind, name="max_active_power")
    target_metadata = result.list_time_series_metadata(target_wind, name="max_active_power")[0]
    preserved_source = source.get_time_series(source_wind, name="max_active_power")

    assert isinstance(target_metadata.normalization, NormalizationByValue)
    assert target_metadata.normalization.value == pytest.approx(75.0)
    assert target_profile.data_array == pytest.approx([0.0, 0.5, 1.0])
    assert preserved_source.data_array == pytest.approx([0.0, 37.5, 75.0])

    assert scaling_calls == [(result, target_wind, "max_active_power", "get_max_active_power")]


def test_reeds_to_sienna_normalizes_reserve_requirement_time_series(monkeypatch):
    source = _build_source_system()
    source_reserve = source.get_component(ReEDSReserve, "spin_up")
    scaling_calls = []

    def record_scaling_call(system, owner, name, function_name):
        scaling_calls.append((system, owner, name, function_name))

    monkeypatch.setattr(
        "r2x_sienna.exporter.set_time_series_scaling_factor_multiplier",
        record_scaling_call,
    )
    source_profile = SingleTimeSeries.from_array(
        data=[0.0, 25.0, 50.0],
        name="requirement",
        initial_timestamp=datetime(2012, 1, 1),
        resolution=timedelta(hours=1),
    )
    source.add_time_series(source_profile, source_reserve)

    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    target_reserve = result.get_component(VariableReserve, "spin_up")
    target_profile = result.get_time_series(target_reserve, name="requirement")
    target_metadata = result.list_time_series_metadata(target_reserve, name="requirement")[0]
    preserved_source = source.get_time_series(source_reserve, name="requirement")

    assert target_reserve.requirement == pytest.approx(0.5)
    assert isinstance(target_metadata.normalization, NormalizationByValue)
    assert target_metadata.normalization.value == pytest.approx(50.0)
    assert target_profile.data_array == pytest.approx([0.0, 0.5, 1.0])
    assert preserved_source.data_array == pytest.approx([0.0, 25.0, 50.0])

    assert scaling_calls == [(result, target_reserve, "requirement", "get_requirement")]


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


def test_reeds_to_sienna_attaches_pumped_hydro_inflow_time_series():
    source = _build_source_system()
    region = source.get_component(ReEDSRegion, name="p1")
    demand = source.get_component(ReEDSDemand, name="load_p1")
    source.add_component(
        ReEDSStorage(
            name="pumped-hydro_p1",
            category="pumped-hydro",
            region=region,
            technology="pumped-hydro",
            capacity=50.0,
            storage_duration=4.0,
            round_trip_efficiency=0.8,
        )
    )
    reference = SingleTimeSeries.from_array(
        data=np.arange(24, dtype=float),
        name="max_active_power",
        initial_timestamp=datetime(2012, 1, 1),
        resolution=timedelta(hours=1),
    )
    source.add_time_series(reference, demand, solve_year=2050, weather_year=2012)

    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    turbine = result.get_component(HydroPumpTurbine, name="pumped-hydro_p1")
    reservoirs = list(result.get_components(HydroReservoir))
    assert len(reservoirs) == 2
    for reservoir in reservoirs:
        inflow = result.list_time_series(
            reservoir,
            name="inflow",
            solve_year=2050,
            weather_year=2012,
        )
        assert len(inflow) == 1
        assert np.array_equal(inflow[0].data, np.zeros(24))
        assert inflow[0].initial_timestamp == reference.initial_timestamp
        assert inflow[0].resolution == reference.resolution

    assert not result.has_time_series(turbine, name="inflow")


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


def test_reeds_to_sienna_attaches_emissions_data():
    from r2x_sienna.models.attributes import EmissionsData
    from r2x_sienna.models.enums import PollutantType

    source = _build_source_system()

    # Attach a CO2 emission to the source thermal generator
    thermal_gen = next(g for g in source.get_components(ReEDSThermalGenerator) if g.name == "gas-cc_p1")
    source.add_supplemental_attribute(thermal_gen, ReEDSEmission(rate=0.45, type=EmissionType.CO2))

    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    target_thermal = next(t for t in result.get_components(ThermalStandard) if t.name == "gas-cc_p1")
    emissions = list(result.get_supplemental_attributes_with_component(target_thermal, EmissionsData))

    assert len(emissions) == 1, f"Expected 1 EmissionsData, got {len(emissions)}"
    attr = emissions[0]
    assert attr.pollutant == PollutantType("CO2")
    assert float(attr.emission_rate.function_data.proportional_term) == pytest.approx(0.45)


def test_reeds_to_sienna_attaches_multiple_emissions():
    from r2x_sienna.models.attributes import EmissionsData
    from r2x_sienna.models.enums import PollutantType

    source = _build_source_system()

    thermal_gen = next(g for g in source.get_components(ReEDSThermalGenerator) if g.name == "gas-cc_p1")
    source.add_supplemental_attribute(thermal_gen, ReEDSEmission(rate=0.5, type=EmissionType.CO2))
    source.add_supplemental_attribute(thermal_gen, ReEDSEmission(rate=0.01, type=EmissionType.NOX))

    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    target_thermal = next(t for t in result.get_components(ThermalStandard) if t.name == "gas-cc_p1")
    emissions = list(result.get_supplemental_attributes_with_component(target_thermal, EmissionsData))

    assert len(emissions) == 2
    pollutants = {attr.pollutant for attr in emissions}
    assert PollutantType("CO2") in pollutants
    assert PollutantType("NOX") in pollutants


def test_reeds_to_sienna_no_emissions_without_source_attribute():
    from r2x_sienna.models.attributes import EmissionsData

    source = _build_source_system()
    # No ReEDSEmission added — generator has no emission attributes

    result = reeds_to_sienna(source, config=ReEDSToSiennaConfig())

    target_thermal = next(t for t in result.get_components(ThermalStandard) if t.name == "gas-cc_p1")
    emissions = list(result.get_supplemental_attributes_with_component(target_thermal, EmissionsData))

    assert len(emissions) == 0
