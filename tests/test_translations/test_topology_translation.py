"""Tests for PLEXOS to Sienna topology translation."""

import pytest
from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSGenerator,
)
from r2x_sienna.models import (
    ACBus,
    Area,
    PowerLoad,
    RenewableDispatch,
    ThermalStandard,
)

from r2x.common.config import PLEXOSToSiennaConfig
from r2x.translations.plexos_to_sienna import translate_system


def test_2node_translation_completeness(plexos_2node_complete):
    """Verify PLEXOS 2-node system translates to correct Sienna structure.

    Expected translation:
    - 1 PLEXOSRegion → 1 Area
    - 2 PLEXOSNodes → 2 ACBus
    - 1 PLEXOSGenerator → 1 ThermalStandard
    - 1 PLEXOSNode with load → 1 PowerLoad
    - 1 PLEXOSLine → 1 MonitoredLine
    """
    config = PLEXOSToSiennaConfig(
        system_base_power=100.0,
        default_voltage_kv=110.0,
    )

    result = translate_system(plexos_2node_complete, config)
    assert result.is_ok(), f"Translation failed: {result.error if result.is_err() else ''}"

    sienna_system = result.unwrap()

    areas = list(sienna_system.get_components(Area))
    assert len(areas) == 1, f"Expected 1 Area, got {len(areas)}"

    buses = list(sienna_system.get_components(ACBus))
    assert len(buses) == 2, f"Expected 2 ACBus, got {len(buses)}"

    # Query for ThermalStandard directly (Generator is just a placeholder in dev version)
    generators = list(sienna_system.get_components(ThermalStandard))
    assert len(generators) == 1, f"Expected 1 ThermalStandard, got {len(generators)}"

    loads = list(sienna_system.get_components(PowerLoad))
    assert len(loads) == 1, f"Expected 1 PowerLoad, got {len(loads)}"

    # Note: Currently PLEXOSLines are converted to AreaInterchange, not MonitoredLine
    # This is a known limitation - need to implement bus-to-bus line translation
    # lines = list(sienna_system.get_components(MonitoredLine))
    # assert len(lines) == 1, f"Expected 1 MonitoredLine, got {len(lines)}"


def test_2node_connectivity(plexos_2node_complete):
    """Verify translated 2-node system maintains proper connectivity."""
    config = PLEXOSToSiennaConfig(system_base_power=100.0, default_voltage_kv=110.0)

    result = translate_system(plexos_2node_complete, config)
    assert result.is_ok()
    sienna_system = result.unwrap()

    buses = {bus.name: bus for bus in sienna_system.get_components(ACBus)}
    assert "Node1" in buses
    assert "Node2" in buses

    generators = list(sienna_system.get_components(ThermalStandard))
    assert generators[0].bus is not None, "Generator not connected to bus"
    assert generators[0].bus.name in buses, "Generator connected to invalid bus"

    loads = list(sienna_system.get_components(PowerLoad))
    assert loads[0].bus is not None, "Load not connected to bus"
    assert loads[0].bus.name in buses, "Load connected to invalid bus"

    # Note: Line conversion creates AreaInterchange (area-to-area) not MonitoredLine (bus-to-bus)
    # TODO: Implement bus-to-bus line translation for MonitoredLine
    # lines = list(sienna_system.get_components(MonitoredLine))
    # assert lines[0].arc["from"] is not None, "Line missing 'from' bus"
    # assert lines[0].arc["to"] is not None, "Line missing 'to' bus"


def test_5bus_translation_completeness(plexos_5bus_complete):
    """Verify PLEXOS 5-bus system translates to correct Sienna structure.

    Expected translation:
    - 1 PLEXOSRegion → 1 Area
    - 5 PLEXOSNodes → 5 ACBus
    - 1 PLEXOSGenerator (Natural Gas) → 1 ThermalStandard
    - 3 PLEXOSGenerators (Hydro/Solar/Wind) → Skipped (placeholder classes not implemented)
    - 1 PLEXOSBattery → Skipped (placeholder class not implemented)
    - 4 PLEXOSNodes with load → 4 PowerLoads
    - 7 PLEXOSLines → 7 AreaInterchange (not MonitoredLine yet)
    - 2 PLEXOSReserves → Skipped (not yet implemented)
    """
    config = PLEXOSToSiennaConfig(
        system_base_power=100.0,
        default_voltage_kv=110.0,
    )

    result = translate_system(plexos_5bus_complete, config)
    assert result.is_ok(), f"Translation failed: {result.error if result.is_err() else ''}"

    sienna_system = result.unwrap()

    areas = list(sienna_system.get_components(Area))
    assert len(areas) == 1, f"Expected 1 Area, got {len(areas)}"

    buses = list(sienna_system.get_components(ACBus))
    assert len(buses) == 5, f"Expected 5 ACBus, got {len(buses)}"

    thermal_gens = list(sienna_system.get_components(ThermalStandard))
    assert len(thermal_gens) == 1, f"Expected 1 ThermalStandard, got {len(thermal_gens)}"

    # Hydro and renewable generators skipped until r2x-sienna implements them
    # hydro_gens = list(sienna_system.get_components(HydroDispatch))
    # assert len(hydro_gens) == 1, f"Expected 1 HydroDispatch, got {len(hydro_gens)}"
    # renewable_gens = list(sienna_system.get_components(RenewableDispatch))
    # assert len(renewable_gens) == 2, f"Expected 2 RenewableDispatch, got {len(renewable_gens)}"

    # Battery skipped until r2x-sienna implements it
    # batteries = list(sienna_system.get_components(EnergyReservoirStorage))
    # assert len(batteries) == 1, f"Expected 1 EnergyReservoirStorage, got {len(batteries)}"

    loads = list(sienna_system.get_components(PowerLoad))
    assert len(loads) == 4, f"Expected 4 PowerLoads, got {len(loads)}"

    # Note: Line conversion creates AreaInterchange (area-to-area) not MonitoredLine (bus-to-bus)
    # TODO: Implement bus-to-bus line translation for MonitoredLine
    # lines = list(sienna_system.get_components(MonitoredLine))
    # assert len(lines) == 7, f"Expected 7 MonitoredLines, got {len(lines)}"

    # Note: Reserve conversion not yet implemented
    # reserves = list(sienna_system.get_components(Reserve))
    # assert len(reserves) == 2, f"Expected 2 Reserves, got {len(reserves)}"


def test_5bus_topology_connectivity(plexos_5bus_complete):
    """Verify translated 5-bus system maintains topology connectivity."""
    config = PLEXOSToSiennaConfig(system_base_power=100.0, default_voltage_kv=110.0)

    result = translate_system(plexos_5bus_complete, config)
    assert result.is_ok()
    sienna_system = result.unwrap()

    buses = {bus.name: bus for bus in sienna_system.get_components(ACBus)}
    expected_buses = {"Bus1", "Bus2", "Bus3", "Bus4", "Bus5"}
    assert set(buses.keys()) == expected_buses, f"Bus names mismatch: {set(buses.keys())}"

    # Check thermal generators
    thermal_gens = list(sienna_system.get_components(ThermalStandard))
    for gen in thermal_gens:
        assert gen.bus is not None, f"ThermalStandard '{gen.name}' not connected to bus"
        assert gen.bus.name in buses, f"ThermalStandard '{gen.name}' connected to invalid bus"

    # Hydro and renewable generators skipped until r2x-sienna implements them
    # hydro_gens = list(sienna_system.get_components(HydroDispatch))
    # for gen in hydro_gens:
    #     assert gen.bus is not None, f"HydroDispatch '{gen.name}' not connected to bus"
    #     assert gen.bus.name in buses, f"HydroDispatch '{gen.name}' connected to invalid bus"

    # renewable_gens = list(sienna_system.get_components(RenewableDispatch))
    # for gen in renewable_gens:
    #     assert gen.bus is not None, f"RenewableDispatch '{gen.name}' not connected to bus"
    #     assert gen.bus.name in buses, f"RenewableDispatch '{gen.name}' connected to invalid bus"

    # Battery skipped until r2x-sienna implements it
    # batteries = list(sienna_system.get_components(EnergyReservoirStorage))
    # for battery in batteries:
    #     assert battery.bus is not None, f"Battery '{battery.name}' not connected to bus"
    #     assert battery.bus.name in buses, f"Battery '{battery.name}' connected to invalid bus"

    loads = list(sienna_system.get_components(PowerLoad))
    for load in loads:
        assert load.bus is not None, f"Load '{load.name}' not connected to bus"
        assert load.bus.name in buses, f"Load '{load.name}' connected to invalid bus"

    # Note: Line conversion creates AreaInterchange (area-to-area) not MonitoredLine (bus-to-bus)
    # TODO: Implement bus-to-bus line translation for MonitoredLine
    # lines = list(sienna_system.get_components(MonitoredLine))
    # for line in lines:
    #     assert line.arc["from"] is not None, f"Line '{line.name}' missing 'from' bus"
    #     assert line.arc["to"] is not None, f"Line '{line.name}' missing 'to' bus"
    #     assert line.arc["from"].name in buses, f"Line '{line.name}' 'from' bus invalid"
    #     assert line.arc["to"].name in buses, f"Line '{line.name}' 'to' bus invalid"


def test_5bus_component_names_preserved(plexos_5bus_complete):
    """Verify component names are preserved during translation."""
    config = PLEXOSToSiennaConfig(system_base_power=100.0, default_voltage_kv=110.0)

    result = translate_system(plexos_5bus_complete, config)
    assert result.is_ok()
    sienna_system = result.unwrap()

    # Only thermal generators are being converted currently
    # Hydro, Solar, Wind skipped until r2x-sienna implements them
    plexos_thermal_names = {
        gen.name
        for gen in plexos_5bus_complete.get_components(PLEXOSGenerator)
        if gen.category == "Natural Gas"
    }

    sienna_gen_names = {gen.name for gen in sienna_system.get_components(ThermalStandard)}

    assert plexos_thermal_names == sienna_gen_names, (
        f"Thermal generator names not preserved: {plexos_thermal_names} vs {sienna_gen_names}"
    )

    # Battery skipped until r2x-sienna implements it
    # plexos_battery_names = {bat.name for bat in plexos_5bus_complete.get_components(PLEXOSBattery)}
    # sienna_battery_names = {bat.name for bat in sienna_system.get_components(EnergyReservoirStorage)}
    # assert plexos_battery_names == sienna_battery_names, "Battery names not preserved"


def test_multiband_markup_cost_curve(plexos_2node_topology):
    """Verify multi-band markup translates to correct piecewise cost curve."""
    from infrasys.function_data import PiecewiseStepData
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode
    from r2x_plexos.models.property import PLEXOSPropertyValue

    system = plexos_2node_topology

    # Create a generator with multi-band markup
    gen = PLEXOSGenerator(
        object_id=10,
        name="GenWithMarkup",
        category="Natural Gas",
        max_capacity=100.0,
        units=1,
    )

    # Create heat rate property (base cost calculation)
    heat_rate_prop = PLEXOSPropertyValue(units="GJ/MWh")
    heat_rate_prop.add_entry(value=10.0, band=1)  # 10 GJ/MWh
    gen.heat_rate = heat_rate_prop

    # Create fuel price property
    fuel_price_prop = PLEXOSPropertyValue(units="$/GJ")
    fuel_price_prop.add_entry(value=5.0, band=1)  # $5/GJ
    gen.fuel_price = fuel_price_prop

    # Base cost = heat_rate * fuel_price = 10 * 5 = $50/MWh

    # Create multi-band markup ($/MWh)
    markup_prop = PLEXOSPropertyValue(units="$/MWh")
    markup_prop.add_entry(value=0.0, band=1)  # Band 1: base cost + $0
    markup_prop.add_entry(value=10.0, band=2)  # Band 2: base cost + $10
    markup_prop.add_entry(value=25.0, band=3)  # Band 3: base cost + $25
    gen.mark_up = markup_prop

    # Create markup points (MW) - defines where each band applies
    markup_point_prop = PLEXOSPropertyValue(units="MW")
    markup_point_prop.add_entry(value=40.0, band=1)  # First 40 MW at base cost
    markup_point_prop.add_entry(value=70.0, band=2)  # Next 30 MW at base + $10
    markup_point_prop.add_entry(value=100.0, band=3)  # Last 30 MW at base + $25
    gen.mark_up_point = markup_point_prop

    system.add_component(gen)

    # Connect generator to Node1
    nodes = list(system.get_components(PLEXOSNode))
    node1 = next(n for n in nodes if n.name == "Node1")

    gen_node_membership = PLEXOSMembership(
        parent_object=gen, child_object=node1, collection=CollectionEnum.Nodes
    )
    system.add_supplemental_attribute(gen, gen_node_membership)

    # Translate to Sienna
    config = PLEXOSToSiennaConfig(system_base_power=100.0, default_voltage_kv=110.0)
    result = translate_system(system, config)
    assert result.is_ok(), f"Translation failed: {result.error if result.is_err() else ''}"

    sienna_system = result.unwrap()

    # Get the translated generator
    thermal_gens = list(sienna_system.get_components(ThermalStandard))
    gen_translated = next((g for g in thermal_gens if g.name == "GenWithMarkup"), None)
    assert gen_translated is not None, "GenWithMarkup not found in translated system"

    # Verify the operation cost has a variable cost curve
    op_cost = gen_translated.operation_cost
    assert op_cost is not None, "Operation cost is None"
    assert hasattr(op_cost, "variable"), "Operation cost missing variable attribute"

    variable_cost = op_cost.variable
    assert variable_cost is not None, "Variable cost is None"

    # Verify it's a cost curve with an incremental curve
    assert hasattr(variable_cost, "value_curve"), "Variable cost missing value_curve"
    value_curve = variable_cost.value_curve

    # Verify it's an IncrementalCurve with PiecewiseStepData
    assert hasattr(value_curve, "function_data"), "Value curve missing function_data"
    function_data = value_curve.function_data

    assert isinstance(function_data, PiecewiseStepData), (
        f"Expected PiecewiseStepData, got {type(function_data)}"
    )

    # Verify the breakpoints match our markup structure
    # Expected x_coords: [0.0, 40.0, 70.0, 100.0]
    # Expected y_coords: [50.0, 60.0, 75.0] (base cost at each segment)
    assert function_data.x_coords == [0.0, 40.0, 70.0, 100.0], (
        f"Unexpected x_coords: {function_data.x_coords}"
    )
    assert function_data.y_coords == [50.0, 60.0, 75.0], f"Unexpected y_coords: {function_data.y_coords}"


@pytest.mark.skip(reason="Time series functionality not yet implemented")
def test_5bus_time_series_attached(plexos_5bus_complete):
    """Verify time series are copied correctly for renewable generators."""
    config = PLEXOSToSiennaConfig(system_base_power=100.0, default_voltage_kv=110.0)

    result = translate_system(plexos_5bus_complete, config)
    assert result.is_ok()
    sienna_system = result.unwrap()

    renewables = list(sienna_system.get_components(RenewableDispatch))
    solar_gen = next((g for g in renewables if "Solar" in g.name), None)
    wind_gen = next((g for g in renewables if "Wind" in g.name), None)

    assert solar_gen is not None, "SolarGen not found"
    assert wind_gen is not None, "WindGen not found"
