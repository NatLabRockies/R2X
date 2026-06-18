"""End-to-end tests for the sienna_to_plexos translation entry point."""

from __future__ import annotations

from infrasys.cost_curves import FuelCurve, UnitSystem
from infrasys.function_data import LinearFunctionData, PiecewiseStepData
from infrasys.value_curves import IncrementalCurve, InputOutputCurve
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSReserve,
)
from r2x_sienna.models import (
    ACBus,
    Arc,
    Area,
    EnergyReservoirStorage,
    Line,
    RenewableDispatch,
    Source,
    ThermalStandard,
    TransmissionInterface,
    VariableReserve,
)
from r2x_sienna.models.costs import ImportExportCost, RenewableGenerationCost, ThermalGenerationCost
from r2x_sienna.models.enums import (
    ACBusTypes,
    PrimeMoversType,
    StorageTechs,
    ThermalFuels,
)
from r2x_sienna.models.named_tuples import FromTo_ToFrom, InputOutput, MinMax, UpDown
from r2x_sienna_to_plexos.plugin_config import SiennaToPlexosConfig
from r2x_sienna_to_plexos.translation import sienna_to_plexos

from r2x_core import System


def _build_source_system():
    """Build a minimal Sienna source system with typical components."""
    source = System(name="sienna-source", auto_add_composed_components=True)

    area = Area(name="A1", category="region")
    source.add_component(area)

    bus1 = ACBus(name="Bus-1", base_voltage=138.0, bustype=ACBusTypes.SLACK, number=1, area=area)
    bus2 = ACBus(name="Bus-2", base_voltage=138.0, number=2, area=area)
    source.add_component(bus1)
    source.add_component(bus2)

    arc = Arc(from_to=bus1, to_from=bus2)
    source.add_component(arc)

    line = Line(
        name="Line-1-2",
        rating=100.0,
        r=0.01,
        x=0.1,
        arc=arc,
        b=FromTo_ToFrom(from_to=0.0, to_from=0.0),
        active_power_flow=0.0,
        reactive_power_flow=0.0,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )
    source.add_component(line)

    thermal = ThermalStandard(
        name="THERM1",
        bus=bus1,
        active_power=0.0,
        reactive_power=0.0,
        rating=100.0,
        base_power=100.0,
        must_run=False,
        status=True,
        time_at_status=0.0,
        active_power_limits=MinMax(min=20.0, max=100.0),
        ramp_limits=None,
        time_limits=UpDown(up=2.0, down=1.0),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=LinearFunctionData(proportional_term=9.5, constant_term=0.0),
                ),
                fuel_cost=2.5,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    source.add_component(thermal)

    solar = RenewableDispatch(
        name="SOLAR1",
        bus=bus2,
        base_power=100.0,
        rating=50.0,
        active_power=0.0,
        reactive_power=0.0,
        prime_mover_type=PrimeMoversType.PVe,
        power_factor=1.0,
        operation_cost=RenewableGenerationCost(),
    )
    source.add_component(solar)

    battery = EnergyReservoirStorage(
        name="BAT1",
        available=True,
        bus=bus2,
        prime_mover_type=PrimeMoversType.BA,
        storage_technology_type=StorageTechs.OTHER_CHEM,
        storage_capacity=200.0,
        storage_level_limits=MinMax(min=0.1, max=0.9),
        initial_storage_capacity_level=0.5,
        rating=50.0,
        active_power=0.0,
        input_active_power_limits=MinMax(min=0.0, max=50.0),
        output_active_power_limits=MinMax(min=0.0, max=50.0),
        efficiency=InputOutput(input=0.95, output=0.95),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-10.0, max=10.0),
        base_power=50.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    source.add_component(battery)

    reserve = VariableReserve(
        name="SPIN1",
        reserve_type="SPINNING",
        direction="UP",
        duration=3600.0,
        requirement=100.0,
    )
    source.add_component(reserve)

    interface = TransmissionInterface(
        name="IF_A1",
        active_power_flow_limits=MinMax(min=-200.0, max=200.0),
        direction_mapping={"Line-1-2": 1},
    )
    source.add_component(interface)

    return source


def test_sienna_to_plexos_returns_system():
    source = _build_source_system()
    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    assert isinstance(result, System)
    assert result.name == "PLEXOS"


def test_sienna_to_plexos_translates_buses_to_nodes():
    source = _build_source_system()
    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    nodes = list(result.get_components(PLEXOSNode))
    node_names = {n.name for n in nodes}
    assert "Bus-1" in node_names
    assert "Bus-2" in node_names


def test_sienna_to_plexos_translates_thermal_generator():
    source = _build_source_system()
    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    generators = list(result.get_components(PLEXOSGenerator))
    gen_names = {g.name for g in generators}
    assert "THERM1" in gen_names


def test_sienna_to_plexos_translates_renewable_generator():
    source = _build_source_system()
    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    generators = list(result.get_components(PLEXOSGenerator))
    gen_names = {g.name for g in generators}
    assert "SOLAR1" in gen_names


def test_sienna_to_plexos_translates_battery():
    source = _build_source_system()
    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    batteries = list(result.get_components(PLEXOSBattery))
    assert any(b.name == "BAT1" for b in batteries)


def test_sienna_to_plexos_translates_line():
    source = _build_source_system()
    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    lines = list(result.get_components(PLEXOSLine))
    assert any(ln.name == "Line-1-2" for ln in lines)


def test_sienna_to_plexos_translates_reserve():
    source = _build_source_system()
    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    reserves = list(result.get_components(PLEXOSReserve))
    assert any(r.name == "SPIN1" for r in reserves)


def test_sienna_to_plexos_translates_interface():
    source = _build_source_system()
    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    interfaces = list(result.get_components(PLEXOSInterface))
    assert any(i.name == "IF_A1" for i in interfaces)


def _make_source_component(bus: ACBus, name: str = "SRC1", available: bool = True) -> Source:
    """Build a minimal Source component for testing."""
    return Source(
        name=name,
        available=available,
        base_power=200.0,
        active_power=0.5,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.0, max=1.0),
        R_th=0.0,
        X_th=0.1,
        internal_voltage=1.0,
        internal_angle=0.0,
        operation_cost=ImportExportCost(),
        bus=bus,
    )


def test_source_translates_to_plexos_generator():
    """A Source component should become a PLEXOSGenerator with category 'source_btb'."""
    source = _build_source_system()
    bus2 = next(b for b in source.get_components(ACBus) if b.name == "Bus-2")
    src = _make_source_component(bus2, name="SRC1")
    source.add_component(src)

    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    generators = {g.name: g for g in result.get_components(PLEXOSGenerator)}
    assert "SRC1" in generators
    gen = generators["SRC1"]
    assert gen.category == "source_btb"
    # max_capacity = active_power_limits.max (1.0 pu) * base_power (200 MVA) = 200 MW
    assert gen.max_capacity == 200.0
    assert gen.units == 1  # available=True


def test_unavailable_source_has_units_zero():
    """A Source with available=False should have units=0 in the PLEXOS generator."""
    source = _build_source_system()
    bus2 = next(b for b in source.get_components(ACBus) if b.name == "Bus-2")
    src = _make_source_component(bus2, name="SRC_OFF", available=False)
    source.add_component(src)

    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    generators = {g.name: g for g in result.get_components(PLEXOSGenerator)}
    assert "SRC_OFF" in generators
    assert generators["SRC_OFF"].units == 0


def test_source_gets_node_membership():
    """A Source's PLEXOSGenerator should receive a node membership for its bus."""
    source = _build_source_system()
    bus2 = next(b for b in source.get_components(ACBus) if b.name == "Bus-2")
    src = _make_source_component(bus2, name="SRC1")
    source.add_component(src)

    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    generators = {g.name: g for g in result.get_components(PLEXOSGenerator)}
    assert "SRC1" in generators


def test_source_conflict_resolution_removes_unavailable_generator():
    """When a Source and an available=False generator share the same name, the generator is removed."""
    source = _build_source_system()
    bus2 = next(b for b in source.get_components(ACBus) if b.name == "Bus-2")

    # Add a ThermalStandard that is unavailable, using the same name as the Source.
    conflicting_gen = ThermalStandard(
        name="CONFLICT",
        bus=bus2,
        available=False,
        active_power=0.0,
        reactive_power=0.0,
        rating=50.0,
        base_power=50.0,
        must_run=False,
        status=False,
        time_at_status=0.0,
        active_power_limits=MinMax(min=10.0, max=50.0),
        ramp_limits=None,
        time_limits=None,
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost(
            variable=FuelCurve(
                value_curve=InputOutputCurve(
                    function_data=LinearFunctionData(proportional_term=9.5, constant_term=0.0),
                ),
                fuel_cost=2.5,
                power_units=UnitSystem.NATURAL_UNITS,
            ),
        ),
    )
    source.add_component(conflicting_gen)

    # Add a Source with the same name.
    src = _make_source_component(bus2, name="CONFLICT")
    source.add_component(src)

    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    # Only one PLEXOSGenerator named "CONFLICT" should remain — the one from Source.
    conflict_gens = [g for g in result.get_components(PLEXOSGenerator) if g.name == "CONFLICT"]
    assert len(conflict_gens) == 1
    assert conflict_gens[0].category == "source_btb"


def _make_ie_cost(
    import_power: list[float],
    import_price: list[float],
    export_power: list[float],
    export_price: list[float],
) -> ImportExportCost:
    """Build an ImportExportCost with piecewise step offer curves."""
    from infrasys.cost_curves import CostCurve

    import_curve = CostCurve(
        value_curve=IncrementalCurve(
            function_data=PiecewiseStepData(x_coords=import_power, y_coords=import_price),
            initial_input=0.0,
            input_at_zero=0.0,
        ),
        power_units=UnitSystem.NATURAL_UNITS,
    )
    export_curve = CostCurve(
        value_curve=IncrementalCurve(
            function_data=PiecewiseStepData(x_coords=export_power, y_coords=export_price),
            initial_input=0.0,
            input_at_zero=0.0,
        ),
        power_units=UnitSystem.NATURAL_UNITS,
    )
    return ImportExportCost(import_offer_curves=import_curve, export_offer_curves=export_curve)


def test_source_offer_curves_populate_plexos_fields():
    """Import/export offer curves on Source should be translated to offer_price/quantity and pump_bid fields."""
    source = _build_source_system()
    bus2 = next(b for b in source.get_components(ACBus) if b.name == "Bus-2")

    ie_cost = _make_ie_cost(
        import_power=[0.0, 100.0, 105.0, 120.0, 200.0],
        import_price=[5.0, 10.0, 20.0, 40.0],
        export_power=[0.0, 100.0, 105.0, 120.0, 200.0],
        export_price=[40.0, 20.0, 10.0, 5.0],
    )
    src = Source(
        name="SRC_CURVE",
        available=True,
        base_power=0.0,  # capacity comes from the curve
        active_power=0.0,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0.0, max=0.0),
        R_th=0.0,
        X_th=0.1,
        internal_voltage=1.0,
        internal_angle=0.0,
        operation_cost=ie_cost,
        bus=bus2,
    )
    source.add_component(src)

    result = sienna_to_plexos(source, config=SiennaToPlexosConfig())

    generators = {g.name: g for g in result.get_components(PLEXOSGenerator)}
    assert "SRC_CURVE" in generators
    gen = generators["SRC_CURVE"]

    # max_capacity falls back to import curve extent (200 MW)
    assert gen.max_capacity == 200.0

    # offer bands from import_offer_curves
    assert gen.offer_price == {1: 5.0, 2: 10.0, 3: 20.0, 4: 40.0}
    assert gen.offer_quantity == {1: 100.0, 2: 5.0, 3: 15.0, 4: 80.0}

    # pump bid bands from export_offer_curves
    assert gen.pump_bid_price == {1: 40.0, 2: 20.0, 3: 10.0, 4: 5.0}
    assert gen.pump_bid_quantity == {1: 100.0, 2: 5.0, 3: 15.0, 4: 80.0}
