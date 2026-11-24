"""End-to-end tests for the plexos_to_sienna translation entry point."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pytest
from infrasys import SingleTimeSeries
from infrasys.normalization import NormalizationByValue
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSPurchaser,
    PLEXOSRegion,
    PLEXOSReserve,
    PLEXOSStorage,
    PLEXOSZone,
)
from r2x_plexos_to_sienna import getters as plexos_getters
from r2x_plexos_to_sienna.plugin_config import PlexosToSiennaConfig
from r2x_plexos_to_sienna.translation import plexos_to_sienna
from r2x_sienna.models import (
    ACBus,
    Area,
    EnergyReservoirStorage,
    HydroDispatch,
    HydroReservoir,
    LoadZone,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    ThermalStandard,
    TransmissionInterface,
    TwoTerminalGenericHVDCLine,
    VariableReserve,
)

from r2x_core import System


def _build_source_system():
    """Build a minimal PLEXOS source system with topology and components."""
    source = System(name="plexos-source", auto_add_composed_components=True)

    node = PLEXOSNode(name="NODE1", voltage=115.0, is_slack_bus=0)
    source.add_component(node)

    region = PLEXOSRegion(name="REGION1", load=200.0)
    source.add_component(region)

    zone = PLEXOSZone(name="ZONE1")
    source.add_component(zone)

    # Region membership on node
    mem_region = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node,
        child_object=region,
    )
    source.add_supplemental_attribute(region, mem_region)
    source.add_supplemental_attribute(node, mem_region)

    # Generator with node membership
    gen = PLEXOSGenerator(name="GEN1", category="gas-cc", max_capacity=100.0, units=1)
    source.add_component(gen)
    mem_gen = PLEXOSMembership(collection=CollectionEnum.Nodes, parent_object=gen, child_object=node)
    source.add_supplemental_attribute(gen, mem_gen)
    source.add_supplemental_attribute(node, mem_gen)

    # Battery with node membership
    battery = PLEXOSBattery(name="BAT1", category="battery", initial_soc=0.5)
    source.add_component(battery)
    mem_bat = PLEXOSMembership(collection=CollectionEnum.Nodes, parent_object=battery, child_object=node)
    source.add_supplemental_attribute(battery, mem_bat)
    source.add_supplemental_attribute(node, mem_bat)

    # Reserve
    reserve = PLEXOSReserve(name="SPIN1", timeframe=300.0, duration=3600.0)
    source.add_component(reserve)

    # Interface
    interface = PLEXOSInterface(name="IF1", min_flow=-200.0, max_flow=200.0)
    source.add_component(interface)

    return source


def test_plexos_to_sienna_returns_system():
    source = _build_source_system()
    config = PlexosToSiennaConfig()
    result = plexos_to_sienna(source, config=config)

    assert isinstance(result, System)
    assert result.name == "Sienna"


def test_plexos_to_sienna_warns_once_with_fallback_category_counts(caplog: pytest.LogCaptureFixture):
    source = _build_source_system()
    generator = next(source.get_components(PLEXOSGenerator))
    generator.category = "-"
    source.add_component(PLEXOSGenerator(name="GEN2", category="-", max_capacity=100.0, units=1))
    source.add_component(PLEXOSGenerator(name="GEN3", category="unknown", max_capacity=100.0, units=1))
    with caplog.at_level(logging.WARNING, logger="r2x_plexos_to_sienna.translation"):
        plexos_to_sienna(source, config=PlexosToSiennaConfig())

    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == "r2x_plexos_to_sienna.translation" and record.levelno >= logging.WARNING
    ]
    assert len(warnings) == 1
    assert "'-' (2 generators)" in warnings[0]
    assert "'unknown' (1 generator)" in warnings[0]


def test_plexos_to_sienna_translates_zone():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    zones = list(result.get_components(LoadZone))
    assert len(zones) == 1
    assert zones[0].name == "ZONE1"


def test_plexos_to_sienna_translates_node_to_bus():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    buses = list(result.get_components(ACBus))
    assert any(b.name == "NODE1" for b in buses)

    bus = next(b for b in buses if b.name == "NODE1")
    assert bus.base_voltage.magnitude == 115.0
    assert bus.area is result.get_component(Area, "REGION1")


def test_plexos_to_sienna_translates_region_to_area():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    areas = list(result.get_components(Area))
    assert len(areas) == 1
    assert areas[0].name == "REGION1"
    assert areas[0].peak_active_power == 200.0


def test_plexos_to_sienna_translates_region_to_load():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    loads = list(result.get_components(PowerLoad))
    assert len(loads) >= 1
    load = next(ld for ld in loads if ld.name == "REGION1")
    assert load.active_power.magnitude == 2.0
    assert load.max_active_power.magnitude == 2.0
    assert load.bus is not None
    assert load.bus.name == "NODE1"


def test_plexos_node_time_series_attaches_to_region_load():
    source = _build_source_system()
    node = next(source.get_components(PLEXOSNode))
    source.add_time_series(
        SingleTimeSeries(
            name="load",
            data=np.array([10.0, 20.0]),
            resolution=timedelta(hours=1),
            initial_timestamp=datetime(2026, 1, 1),
        ),
        node,
    )

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    load = next(load for load in result.get_components(PowerLoad) if load.name == "REGION1")
    time_series = result.list_time_series(load, name="max_active_power")
    assert len(time_series) == 1
    np.testing.assert_allclose(time_series[0].data, [0.05, 0.1])


def test_plexos_purchaser_translates_to_load_with_time_series():
    source = _build_source_system()
    node = next(source.get_components(PLEXOSNode))
    purchaser = PLEXOSPurchaser(name="PURCHASER1", units=1.0, fixed_load=75.0, max_load=100.0)
    source.add_component(purchaser)
    membership = PLEXOSMembership(
        collection=CollectionEnum.Nodes,
        parent_object=purchaser,
        child_object=node,
    )
    source.add_supplemental_attribute(purchaser, membership)
    source.add_supplemental_attribute(node, membership)
    source.add_time_series(
        SingleTimeSeries(
            name="max_active_power",
            data=np.array([70.0, 80.0]),
            resolution=timedelta(hours=1),
            initial_timestamp=datetime(2026, 1, 1),
        ),
        purchaser,
    )

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    load = next(load for load in result.get_components(PowerLoad) if load.name == "PURCHASER1")
    assert load.available is True
    assert load.active_power.magnitude == 0.75
    assert load.max_active_power.magnitude == 1.0
    assert load.bus is not None
    assert load.bus.name == "NODE1"
    time_series = result.list_time_series(load, name="max_active_power")
    assert len(time_series) == 1
    np.testing.assert_allclose(time_series[0].data, [0.7, 0.8])


def test_plexos_offline_purchaser_is_unavailable():
    source = _build_source_system()
    node = next(source.get_components(PLEXOSNode))
    purchaser = PLEXOSPurchaser(name="OFFLINE_PURCHASER", units=0.0, fixed_load=75.0, max_load=100.0)
    source.add_component(purchaser)
    membership = PLEXOSMembership(
        collection=CollectionEnum.Nodes,
        parent_object=purchaser,
        child_object=node,
    )
    source.add_supplemental_attribute(purchaser, membership)
    source.add_supplemental_attribute(node, membership)

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    load = next(load for load in result.get_components(PowerLoad) if load.name == "OFFLINE_PURCHASER")
    assert load.available is False
    assert load.active_power.magnitude == 0.75
    assert load.max_active_power.magnitude == 1.0


def test_plexos_to_sienna_translates_generator():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    thermals = list(result.get_components(ThermalStandard))
    assert any(t.name == "GEN1" for t in thermals)

    gen = next(t for t in thermals if t.name == "GEN1")
    assert gen.bus is not None
    assert gen.bus.name == "NODE1"
    assert gen.must_run is False


def test_plexos_generator_time_series_attaches_to_sienna_generator():
    source = _build_source_system()
    generator = next(source.get_components(PLEXOSGenerator))
    source.add_time_series(
        SingleTimeSeries(
            name="active_power",
            data=np.array([10.0, 20.0]),
            resolution=timedelta(hours=1),
            initial_timestamp=datetime(2026, 1, 1),
        ),
        generator,
    )

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    target_generator = next(gen for gen in result.get_components(ThermalStandard) if gen.name == "GEN1")
    time_series = result.list_time_series(target_generator, name="active_power")
    assert len(time_series) == 1
    np.testing.assert_array_equal(time_series[0].data, [10.0, 20.0])


@pytest.mark.parametrize(
    ("name", "values", "hours", "initial_timestamp", "expected_values"),
    [
        ("max_energy_day", [2.4, 1.2], [24, 24], datetime(2012, 1, 1), [1.0, 0.5]),
        ("max_energy_month", [74.4, 1.2], [744, 24], datetime(2012, 1, 1), [1.0, 0.5]),
        (
            "max_energy_week",
            [2.4, 1.2],
            [168, 48],
            datetime(2012, 1, 1),
            [2.4 * 1000 / (100 * 168), 1.2 * 1000 / (100 * 48)],
        ),
        ("max_energy_year", [2.4, 1.2], [24, 24], datetime(2012, 12, 31), [1.0, 0.5]),
    ],
)
def test_plexos_hydro_energy_limits_translate_to_budget(
    name,
    values,
    hours,
    initial_timestamp,
    expected_values,
):
    source = _build_source_system()
    generator = next(source.get_components(PLEXOSGenerator))
    generator.category = "hyded"
    source.add_time_series(
        SingleTimeSeries(
            name=name,
            data=np.repeat(values, hours),
            resolution=timedelta(hours=1),
            initial_timestamp=initial_timestamp,
        ),
        generator,
    )

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    hydro = result.get_component(HydroDispatch, "GEN1")
    profile = result.get_time_series(hydro, name="hydro_budget")
    np.testing.assert_allclose(profile.data, np.repeat(expected_values, hours))


def test_plexos_nondispatchable_hydro_translates_to_fixed_output():
    source = _build_source_system()
    generator = next(source.get_components(PLEXOSGenerator))
    generator.category = "hydend"
    source.add_time_series(
        SingleTimeSeries(
            name="max_active_power",
            data=np.array([40.0, 60.0]),
            resolution=timedelta(hours=1),
            initial_timestamp=datetime(2012, 1, 1),
        ),
        generator,
    )

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    hydro = result.get_component(RenewableNonDispatch, "GEN1")
    profile = result.get_time_series(hydro, name="max_active_power")
    np.testing.assert_allclose(profile.data, [0.4, 0.6])


@pytest.mark.parametrize("category", ["wind-ons", "pv"])
def test_plexos_renewable_max_active_power_is_normalized(category, monkeypatch):
    source = _build_source_system()
    generator = source.get_component(PLEXOSGenerator, "GEN1")
    generator.category = category
    generator.max_capacity = 160.9
    source_values = np.array([30.92, 36.54, 45.74])
    source.add_time_series(
        SingleTimeSeries(
            name="max_active_power",
            data=source_values,
            resolution=timedelta(hours=1),
            initial_timestamp=datetime(2026, 1, 1),
        ),
        generator,
    )
    scaling_calls = []
    set_scaling = plexos_getters.set_time_series_scaling_factor_multiplier

    def record_scaling(system, component, name, function_name):
        scaling_calls.append((system, component, name, function_name))
        set_scaling(system, component, name, function_name)

    monkeypatch.setattr(plexos_getters, "set_time_series_scaling_factor_multiplier", record_scaling)

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    renewable = result.get_component(RenewableDispatch, "GEN1")
    profile = result.get_time_series(renewable, name="max_active_power")
    (metadata,) = result.list_time_series_metadata(renewable, name="max_active_power")
    assert isinstance(metadata.normalization, NormalizationByValue)
    assert metadata.normalization.value == pytest.approx(160.9)
    np.testing.assert_allclose(profile.data_array, source_values / 160.9)
    np.testing.assert_allclose(profile.data_array * renewable.rating * renewable.base_power, source_values)
    assert result.base_power == 100.0
    assert scaling_calls == [(result, renewable, "max_active_power", "get_max_active_power")]


def test_plexos_to_sienna_translates_battery():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    storages = list(result.get_components(EnergyReservoirStorage))
    assert any(s.name == "BAT1" for s in storages)

    bat = next(s for s in storages if s.name == "BAT1")
    assert pytest.approx(0.5) == bat.initial_storage_capacity_level
    assert bat.bus is not None
    assert bat.bus.name == "NODE1"


def test_plexos_hydro_natural_inflow_time_series_translates_to_inflow():
    source = _build_source_system()
    storage = PLEXOSStorage(
        name="RESERVOIR1",
        category="pumped-hydro",
        natural_inflow=5.0,
    )
    source.add_component(storage)
    source.add_time_series(
        SingleTimeSeries(
            name="natural_inflow",
            data=np.array([4.0, 6.0]),
            resolution=timedelta(hours=1),
            initial_timestamp=datetime(2026, 1, 1),
        ),
        storage,
    )

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    reservoir = result.get_component(HydroReservoir, "RESERVOIR1")
    inflow_profiles = result.list_time_series(reservoir, name="inflow")
    assert len(inflow_profiles) == 1
    np.testing.assert_array_equal(inflow_profiles[0].data, [4.0, 6.0])
    assert result.list_time_series(reservoir, name="natural_inflow") == []


def test_plexos_hvdc_flow_limits_translate_to_sienna_base(tmp_path):
    source = _build_source_system()
    source.base_power = 200.0
    node2 = PLEXOSNode(name="NODE_2", voltage=115.0)
    source.add_component(node2)
    region = next(source.get_components(PLEXOSRegion))
    region_membership = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node2,
        child_object=region,
    )
    source.add_supplemental_attribute(region, region_membership)
    source.add_supplemental_attribute(node2, region_membership)
    nodes = {node.name: node for node in source.get_components(PLEXOSNode)}
    line = PLEXOSLine(
        name="HVDC1",
        category="two-terminal-generic-hvdc-line",
        min_flow=-50.0,
        max_flow=100.0,
    )
    source.add_component(line)
    for collection, node_name in (
        (CollectionEnum.NodeFrom, "NODE1"),
        (CollectionEnum.NodeTo, "NODE_2"),
    ):
        source.add_supplemental_attribute(
            line,
            PLEXOSMembership(
                collection=collection,
                parent_object=line,
                child_object=nodes[node_name],
            ),
        )

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    translated = result.get_component(TwoTerminalGenericHVDCLine, "HVDC1")
    assert translated.active_power_limits_from.min == pytest.approx(-0.5)
    assert translated.active_power_limits_from.max == pytest.approx(1.0)
    assert translated.active_power_limits_to.min == pytest.approx(-0.5)
    assert translated.active_power_limits_to.max == pytest.approx(1.0)
    assert translated.active_power_limits_from.min * result.base_power == pytest.approx(-50.0)
    assert translated.active_power_limits_from.max * result.base_power == pytest.approx(100.0)
    assert translated.active_power_limits_to.min * result.base_power == pytest.approx(-50.0)
    assert translated.active_power_limits_to.max * result.base_power == pytest.approx(100.0)


def test_plexos_to_sienna_translates_reserve():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    reserves = list(result.get_components(VariableReserve))
    assert len(reserves) == 1
    assert reserves[0].name == "SPIN1"
    assert reserves[0].time_frame == 300.0


@pytest.mark.parametrize("series_name", ["requirement", "min_provision"])
def test_plexos_reserve_requirement_is_normalized(series_name, monkeypatch):
    source = _build_source_system()
    reserve = source.get_component(PLEXOSReserve, "SPIN1")
    source_profiles = {
        "base": np.array([2359.3, 2295.3]),
        "stress": np.array([4782.0, 2500.0]),
    }
    for scenario, values in source_profiles.items():
        source.add_time_series(
            SingleTimeSeries(
                name=series_name,
                data=values,
                resolution=timedelta(hours=1),
                initial_timestamp=datetime(2026, 1, 1),
            ),
            reserve,
            scenario=scenario,
        )
    scaling_calls = []
    set_scaling = plexos_getters.set_time_series_scaling_factor_multiplier

    def record_scaling(system, component, name, function_name):
        scaling_calls.append((system, component, name, function_name))
        set_scaling(system, component, name, function_name)

    monkeypatch.setattr(plexos_getters, "set_time_series_scaling_factor_multiplier", record_scaling)

    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    target_reserve = result.get_component(VariableReserve, "SPIN1")
    peak_requirement = 4782.0
    assert target_reserve.requirement == pytest.approx(peak_requirement / 100.0)
    assert result.base_power == 100.0
    for scenario, values in source_profiles.items():
        profile = result.get_time_series(target_reserve, name="requirement", scenario=scenario)
        (metadata,) = result.list_time_series_metadata(
            target_reserve,
            name="requirement",
            scenario=scenario,
        )
        assert isinstance(metadata.normalization, NormalizationByValue)
        assert metadata.normalization.value == pytest.approx(peak_requirement)
        np.testing.assert_allclose(profile.data_array, values / peak_requirement)
        np.testing.assert_allclose(
            profile.data_array * target_reserve.requirement * result.base_power,
            values,
        )
    assert scaling_calls == [(result, target_reserve, "requirement", "get_requirement")]


def test_plexos_to_sienna_translates_interface():
    source = _build_source_system()
    result = plexos_to_sienna(source, config=PlexosToSiennaConfig())

    interfaces = list(result.get_components(TransmissionInterface))
    assert len(interfaces) == 1
    assert interfaces[0].name == "IF1"
    assert interfaces[0].active_power_flow_limits.max == 200.0
