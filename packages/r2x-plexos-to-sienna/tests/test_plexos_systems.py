"""End-to-end PLEXOS-to-Sienna translation of the 2-node and IEEE 5-bus fixtures."""

from __future__ import annotations

import json

import numpy as np
import pytest
from fixture.plexos_systems import PROFILE_HOURS, solar_shape, wind_shape
from loguru import logger
from r2x_plexos_to_sienna.plugin_config import PlexosToSiennaConfig
from r2x_plexos_to_sienna.translation import plexos_to_sienna
from r2x_sienna import SiennaExporter
from r2x_sienna.models import (
    ACBus,
    EnergyReservoirStorage,
    HydroDispatch,
    Line,
    PowerLoad,
    RenewableDispatch,
    ThermalStandard,
    VariableReserve,
)
from r2x_sienna.models.enums import ACBusTypes
from r2x_sienna.plugin_config import SiennaExporterConfig
from r2x_sienna.units import get_magnitude

from r2x_core import PluginContext


def _translate(system):
    return plexos_to_sienna(system, config=PlexosToSiennaConfig())


def test_2node_system_translates_topology_and_generation(plexos_2node_complete):
    result = _translate(plexos_2node_complete)

    buses = {bus.name: bus for bus in result.get_components(ACBus)}
    assert set(buses) == {"Node1", "Node2"}
    assert buses["Node1"].bustype == ACBusTypes.SLACK
    assert buses["Node2"].bustype == ACBusTypes.PQ
    assert {bus.area.name for bus in buses.values()} == {"Area1"}
    assert {get_magnitude(bus.base_voltage) for bus in buses.values()} == {110.0}

    line = result.get_component(Line, "Line_1_2")
    assert (line.arc.from_to.name, line.arc.to_from.name) == ("Node1", "Node2")
    assert line.rating * result.base_power == pytest.approx(100.0)

    gen = result.get_component(ThermalStandard, "Gen1")
    assert gen.bus.name == "Node1"
    assert gen.active_power_limits.max * gen.base_power == pytest.approx(50.0)

    assert not any(load.name == "Area1" for load in result.get_components(PowerLoad))


def test_5bus_system_translates_every_device_family(plexos_5bus_complete):
    result = _translate(plexos_5bus_complete)

    assert {bus.name for bus in result.get_components(ACBus)} == {f"Bus{i}" for i in range(1, 6)}
    assert result.get_component(ACBus, "Bus1").bustype == ACBusTypes.SLACK
    lines = {line.name: line for line in result.get_components(Line)}
    assert len(lines) == 7
    assert lines["Line_1_2"].rating * result.base_power == pytest.approx(80.0)

    expected_devices = {
        ("ThermalGen", ThermalStandard, "Bus2", 40.0),
        ("HydroGen", HydroDispatch, "Bus1", 50.0),
        ("SolarGen", RenewableDispatch, "Bus3", 30.0),
        ("WindGen", RenewableDispatch, "Bus5", 25.0),
    }
    for name, target_type, bus_name, capacity_mw in expected_devices:
        device = result.get_component(target_type, name)
        assert device.bus.name == bus_name
        assert device.rating * device.base_power == pytest.approx(capacity_mw)

    for name, target_type, capacity_mw in (
        ("ThermalGen", ThermalStandard, 40.0),
        ("HydroGen", HydroDispatch, 50.0),
    ):
        device = result.get_component(target_type, name)
        limits_mw = (device.active_power_limits.min, device.active_power_limits.max)
        assert tuple(v * device.base_power for v in limits_mw) == pytest.approx(
            (0.25 * capacity_mw, capacity_mw)
        )
        ramps_mw = (device.ramp_limits.up * device.base_power, device.ramp_limits.down * device.base_power)
        assert ramps_mw == pytest.approx((0.1 * capacity_mw, 0.05 * capacity_mw))

    battery = result.get_component(EnergyReservoirStorage, "Battery1")
    assert battery.bus.name == "Bus4"
    assert battery.storage_capacity * battery.base_power == pytest.approx(80.0)
    assert battery.input_active_power_limits.max * battery.base_power == pytest.approx(20.0)
    assert battery.output_active_power_limits.max * battery.base_power == pytest.approx(20.0)
    assert battery.initial_storage_capacity_level == pytest.approx(0.5)
    assert (battery.efficiency.input, battery.efficiency.output) == pytest.approx((0.95, 0.95))


def test_5bus_reserve_is_assigned_only_to_member_devices(plexos_5bus_complete):
    result = _translate(plexos_5bus_complete)

    reserve = result.get_component(VariableReserve, "SpinningReserve")
    assert reserve.time_frame == pytest.approx(600.0)
    providers = {
        device.name
        for device_type in (ThermalStandard, HydroDispatch, RenewableDispatch, EnergyReservoirStorage)
        for device in result.get_components(device_type)
        if reserve in device.services
    }
    assert providers == {"ThermalGen", "HydroGen", "Battery1"}


@pytest.mark.parametrize(("name", "shape"), [("SolarGen", solar_shape()), ("WindGen", wind_shape())])
def test_5bus_renewable_profiles_preserve_mw(plexos_5bus_complete, name, shape):
    source_capacity = {"SolarGen": 30.0, "WindGen": 25.0}[name]
    result = _translate(plexos_5bus_complete)

    renewable = result.get_component(RenewableDispatch, name)
    profile = result.get_time_series(renewable, name="max_active_power")
    assert len(profile.data_array) == PROFILE_HOURS
    np.testing.assert_allclose(
        profile.data_array * renewable.rating * renewable.base_power,
        source_capacity * shape,
    )


def test_5bus_translation_exports_to_complete_sienna_json(plexos_5bus_complete, tmp_path):
    result = _translate(plexos_5bus_complete)
    output = tmp_path / "5bus.json"
    warnings: list[str] = []
    logger.enable("r2x_sienna")
    sink = logger.add(lambda message: warnings.append(str(message)), level="WARNING")
    try:
        exporter = SiennaExporter.from_context(
            PluginContext(system=result, config=SiennaExporterConfig(output_path=str(output)))
        )
        exporter.on_export().unwrap()
    finally:
        logger.remove(sink)
        logger.disable("r2x_sienna")

    assert not [message for message in warnings if "PowerSystems.jl requires" in message]
    exported = {
        (component["__metadata__"]["type"], component["name"])
        for component in json.loads(output.read_text())["data"]["components"]
        if "name" in component
    }
    assert {
        ("ThermalStandard", "ThermalGen"),
        ("HydroDispatch", "HydroGen"),
        ("RenewableDispatch", "SolarGen"),
        ("RenewableDispatch", "WindGen"),
        ("EnergyReservoirStorage", "Battery1"),
        ("VariableReserve", "SpinningReserve"),
    } <= exported
    assert ("PowerLoad", "Area1") not in exported
    assert sum(component_type == "Line" for component_type, _ in exported) == 7


def test_pumped_hydro_units_attach_to_head_and_tail_reservoirs(plexos_2node_complete, tmp_path):
    from datetime import datetime, timedelta

    from fixture.plexos_systems import _connect
    from infrasys import SingleTimeSeries
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSNode, PLEXOSStorage
    from r2x_sienna.models import HydroPumpTurbine, HydroReservoir

    system = plexos_2node_complete
    node = system.get_component(PLEXOSNode, "Node2")
    head = PLEXOSStorage(name="Plant_head", category="head", max_volume=10.0, natural_inflow=8.0)
    tail = PLEXOSStorage(name="Plant_tail", category="tail", max_volume=10.0)
    system.add_components(head, tail)
    system.add_time_series(
        SingleTimeSeries(
            name="natural_inflow",
            data=np.array([4.0, 8.0, 2.0]),
            resolution=timedelta(hours=1),
            initial_timestamp=datetime(2026, 1, 1),
        ),
        head,
    )
    for name in ("Plant_1", "Plant_2"):
        unit = PLEXOSGenerator(
            name=name,
            category="pumped-hydro",
            max_capacity=40.0,
            pump_load=30.0,
            pump_efficiency=81.0,
            units=1,
        )
        system.add_component(unit)
        _connect(system, unit, node, CollectionEnum.Nodes)
        _connect(system, unit, head, CollectionEnum.HeadStorage)
        _connect(system, unit, tail, CollectionEnum.TailStorage)

    result = _translate(system)

    # The CLI hands each step's system to the next through a JSON artifact.
    artifact = tmp_path / "artifact" / "system.json"
    artifact.parent.mkdir()
    result.to_json(artifact)
    result = type(result).from_json(artifact)

    units = {unit.name: unit for unit in result.get_components(HydroPumpTurbine)}
    assert set(units) == {"Plant_1", "Plant_2"}
    unit = units["Plant_1"]
    assert unit.time_at_status == pytest.approx(1e4)
    assert unit.bus.name == "Node2"
    assert unit.efficiency.pump == pytest.approx(0.9)
    assert unit.active_power_limits_pump.max * unit.base_power == pytest.approx(30.0)
    head_reservoir = result.get_component(HydroReservoir, "Plant_head")
    tail_reservoir = result.get_component(HydroReservoir, "Plant_tail")
    assert {turbine.name for turbine in head_reservoir.downstream_turbines} == set(units)
    assert {turbine.name for turbine in tail_reservoir.upstream_turbines} == set(units)
    assert head_reservoir.upstream_turbines == []
    assert tail_reservoir.downstream_turbines == []
    assert head_reservoir.inflow == pytest.approx(8.0)
    head_inflow = result.get_time_series(head_reservoir, name="inflow")
    np.testing.assert_allclose(head_inflow.data_array * head_reservoir.inflow, [4.0, 8.0, 2.0])
    np.testing.assert_allclose(
        result.get_time_series(tail_reservoir, name="inflow").data_array, [0.0, 0.0, 0.0]
    )

    output = tmp_path / "pumped.json"
    exporter = SiennaExporter.from_context(
        PluginContext(system=result, config=SiennaExporterConfig(output_path=str(output)))
    )
    exporter.on_export().unwrap()
    components = json.loads(output.read_text())["data"]["components"]
    uuids = {
        component["name"]: component["internal"]["uuid"]["value"]
        for component in components
        if component["__metadata__"]["type"] == "HydroPumpTurbine"
    }
    exported_head = next(component for component in components if component.get("name") == "Plant_head")
    assert {reference["value"] for reference in exported_head["downstream_turbines"]} == set(uuids.values())
