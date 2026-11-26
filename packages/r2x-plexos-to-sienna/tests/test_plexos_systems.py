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

    load = result.get_component(PowerLoad, "Area1")
    assert load.bus.area.name == "Area1"


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
        ("PowerLoad", "Area1"),
    } <= exported
    assert sum(component_type == "Line" for component_type, _ in exported) == 7
