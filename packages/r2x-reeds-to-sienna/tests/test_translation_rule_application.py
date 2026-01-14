"""Translation tests."""

from __future__ import annotations

import json
from importlib.resources import files

import pytest


def test_reeds_region_translates_to_area() -> None:
    """Ensure ReEDSRegion produces a Sienna Area with mapped fields and defaults."""
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import Area

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    source.add_component(
        ReEDSRegion(name="R_TEST", category="region-cat", max_active_power=123.0, interconnect="west")
    )

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    areas = list(target.get_components(Area))
    assert len(areas) == 1
    area = areas[0]
    assert area.name == "R_TEST"
    assert area.category == "region-cat"
    assert pytest.approx(123.0) == area.peak_active_power
    assert pytest.approx(0.0) == area.peak_reactive_power
    assert pytest.approx(0.0) == area.load_response


def test_reeds_region_translates_to_acbus() -> None:
    """Ensure ReEDSRegion produces a Sienna ACBus with correct defaults."""
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import ACBus, Area

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    source.add_component(ReEDSRegion(name="p42", category="region"))

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    buses = list(target.get_components(ACBus))
    assert len(buses) == 1
    bus = buses[0]
    assert bus.name == "p42_BUS"
    assert bus.number == 42
    assert bus.base_voltage.magnitude == 115.0
    assert bus.magnitude == 1.0
    assert bus.angle == 0.0
    assert bus.available is True

    # Check bus is associated with correct area
    areas = list(target.get_components(Area))
    assert len(areas) == 1
    assert bus.area == areas[0]


def test_reeds_region_with_non_numeric_name() -> None:
    """Ensure ReEDSRegion with non-numeric name gets assigned bus number."""
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import ACBus

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    source.add_component(ReEDSRegion(name="otx", category="region"))

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    buses = list(target.get_components(ACBus))
    assert len(buses) == 1
    bus = buses[0]
    assert bus.name == "otx_BUS"
    assert bus.number >= 10000  # Non-numeric regions start at 10000


def test_reeds_generators_translate_to_sienna_types() -> None:
    """Ensure ReEDS thermal/variable generators translate to Sienna components."""
    from r2x_reeds.models import ReEDSRegion, ReEDSThermalGenerator, ReEDSVariableGenerator
    from r2x_sienna.models import (
        ACBus,
        Area,
        RenewableDispatch,
        RenewableNonDispatch,
        ThermalStandard,
    )

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    source.add_component(region)
    source.add_component(
        ReEDSThermalGenerator(
            name="THERM1",
            region=region,
            technology="gas-cc",
            capacity=100.0,
            heat_rate=7.5,
            fuel_type="gas",
        )
    )
    source.add_component(
        ReEDSVariableGenerator(
            name="VRE1",
            region=region,
            technology="wind-ons",
            capacity=50.0,
        )
    )
    source.add_component(
        ReEDSVariableGenerator(
            name="DISTPV",
            region=region,
            technology="distpv",
            capacity=25.0,
        )
    )

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    # Check Area and Bus were created
    areas = list(target.get_components(Area))
    assert len(areas) == 1

    buses = list(target.get_components(ACBus))
    assert len(buses) == 1

    # Check generators
    thermal_gens = list(target.get_components(ThermalStandard))
    vre_dispatch = list(target.get_components(RenewableDispatch))
    vre_nondispatch = list(target.get_components(RenewableNonDispatch))

    assert len(thermal_gens) == 1
    assert len(vre_dispatch) == 1
    assert len(vre_nondispatch) == 1

    thermal = thermal_gens[0]
    assert thermal.name == "THERM1"
    assert thermal.category == "gas-cc"
    assert thermal.rating == 100.0
    assert thermal.bus == buses[0]

    wind = vre_dispatch[0]
    assert wind.name == "VRE1"
    assert wind.category == "wind-ons"
    assert wind.rating == 50.0
    assert wind.bus == buses[0]

    pv = vre_nondispatch[0]
    assert pv.name == "DISTPV"
    assert pv.category == "distpv"
    assert pv.rating == 25.0
    assert pv.bus == buses[0]


def test_reeds_hydro_translates_to_hydro_dispatch() -> None:
    """Ensure ReEDSHydroGenerator translates to HydroDispatch."""
    from r2x_reeds.models import ReEDSHydroGenerator, ReEDSRegion
    from r2x_sienna.models import HydroDispatch

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    source.add_component(region)
    source.add_component(
        ReEDSHydroGenerator(
            name="HYDRO1",
            region=region,
            technology="hydro",
            capacity=100.0,
            is_dispatchable=True,
            ramp_rate=10.0,
        )
    )

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    hydros = list(target.get_components(HydroDispatch))
    assert len(hydros) == 1

    hydro = hydros[0]
    assert hydro.name == "HYDRO1"
    assert hydro.category == "hydro"
    assert hydro.rating == 100.0
    assert hydro.active_power_limits.max == 100.0
    assert hydro.ramp_limits.up == pytest.approx(10.0)
    assert hydro.time_limits.up == 0.0
    assert hydro.time_limits.down == 0.0


def test_reeds_storage_translates_to_energy_reservoir() -> None:
    """Ensure ReEDSStorage translates to EnergyReservoirStorage."""
    from r2x_reeds.models import ReEDSRegion, ReEDSStorage
    from r2x_sienna.models import EnergyReservoirStorage

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    source.add_component(region)
    source.add_component(
        ReEDSStorage(
            name="BATT1",
            region=region,
            technology="battery_4",
            capacity=50.0,
            storage_duration=4.0,
            round_trip_efficiency=0.85,
        )
    )

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    storages = list(target.get_components(EnergyReservoirStorage))
    assert len(storages) == 1

    storage = storages[0]
    assert storage.name == "BATT1"
    assert storage.category == "battery_4"
    assert storage.rating == 50.0
    assert storage.storage_capacity == 200.0  # 50 * 4
    assert storage.efficiency.output == pytest.approx(0.85)


def test_reeds_demand_translates_to_power_load() -> None:
    """Ensure ReEDSDemand translates to PowerLoad."""
    from r2x_reeds.models import ReEDSDemand, ReEDSRegion
    from r2x_sienna.models import PowerLoad

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    region = ReEDSRegion(name="p1", category="region")
    source.add_component(region)
    source.add_component(
        ReEDSDemand(
            name="LOAD1",
            region=region,
            max_active_power=500.0,
        )
    )

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    loads = list(target.get_components(PowerLoad))
    assert len(loads) == 1

    load = loads[0]
    assert load.name == "LOAD1"
    assert load.max_active_power.magnitude == 500.0
    assert load.base_power.magnitude == 100.0


def test_reeds_interface_translates_to_area_interchange() -> None:
    """Ensure ReEDSInterface translates to AreaInterchange."""
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion
    from r2x_sienna.models import AreaInterchange

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    region1 = ReEDSRegion(name="p1", category="region")
    region2 = ReEDSRegion(name="p2", category="region")
    source.add_component(region1)
    source.add_component(region2)
    source.add_component(ReEDSInterface(name="IFACE_1_2", from_region=region1, to_region=region2))

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    interchanges = list(target.get_components(AreaInterchange))
    assert len(interchanges) == 1

    interchange = interchanges[0]
    assert interchange.name == "IFACE_1_2"
    assert interchange.from_area.name == "p1"
    assert interchange.to_area.name == "p2"
    assert interchange.active_power_flow == 0.0


def test_reeds_reserve_translates_to_variable_reserve() -> None:
    """Ensure ReEDSReserve translates to VariableReserve."""
    from r2x_reeds.models import ReEDSReserve
    from r2x_sienna.models import VariableReserve

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    source.add_component(
        ReEDSReserve(
            name="REG_UP",
            reserve_type="REGULATION",
            direction="Up",
            time_frame=300.0,
            duration=3600.0,
        )
    )

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    reserves = list(target.get_components(VariableReserve))
    assert len(reserves) == 1

    reserve = reserves[0]
    assert reserve.name == "REG_UP"
    assert reserve.requirement == 0.0
    assert reserve.time_frame == 300.0
    assert reserve.sustained_time == 3600.0
    assert reserve.max_output_fraction == 1.0
    assert reserve.deployed_fraction == 1.0


def test_reeds_transmission_line_translates_to_line() -> None:
    """Ensure ReEDSTransmissionLine translates to Line."""
    from r2x_reeds.models import ReEDSInterface, ReEDSRegion, ReEDSTransmissionLine
    from r2x_sienna.models import Line

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    region1 = ReEDSRegion(name="p1", category="region")
    region2 = ReEDSRegion(name="p2", category="region")
    source.add_component(region1)
    source.add_component(region2)
    interface = ReEDSInterface(name="IFACE", from_region=region1, to_region=region2)
    source.add_component(interface)
    source.add_component(
        ReEDSTransmissionLine(
            name="LINE_1_2", interface=interface, max_active_power={"from_to": 150.0, "to_from": 150.0}
        )
    )

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    lines = list(target.get_components(Line))
    assert len(lines) == 1

    line = lines[0]
    assert line.name == "LINE_1_2"
    assert line.rating == 150.0
    assert line.r == 0.0
    assert line.x == 0.0
    assert line.angle_limits.min == -90.0
    assert line.angle_limits.max == 90.0
    assert line.arc is not None


def test_multiple_regions_create_multiple_buses_and_areas() -> None:
    """Ensure multiple ReEDSRegions create corresponding buses and areas."""
    from r2x_reeds.models import ReEDSRegion
    from r2x_sienna.models import ACBus, Area

    from r2x_core import PluginConfig, Rule, System, TranslationContext, apply_rules_to_context

    rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
    rules = Rule.from_records(json.loads(rules_path.read_text()))

    source = System(name="source", auto_add_composed_components=True)
    source.add_component(ReEDSRegion(name="p1", category="region"))
    source.add_component(ReEDSRegion(name="p2", category="region"))
    source.add_component(ReEDSRegion(name="p3", category="region"))

    target = System(name="target", auto_add_composed_components=True)
    config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
    context = TranslationContext(source_system=source, target_system=target, config=config, rules=rules)

    result = apply_rules_to_context(context)
    assert result.total_rules > 0

    areas = list(target.get_components(Area))
    buses = list(target.get_components(ACBus))

    assert len(areas) == 3
    assert len(buses) == 3

    area_names = {area.name for area in areas}
    bus_names = {bus.name for bus in buses}

    assert area_names == {"p1", "p2", "p3"}
    assert bus_names == {"p1_BUS", "p2_BUS", "p3_BUS"}
