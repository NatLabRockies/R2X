"""End-to-end tests for the sienna_to_plexos translation entry point."""

from __future__ import annotations

from infrasys.cost_curves import FuelCurve, UnitSystem
from infrasys.function_data import LinearFunctionData
from infrasys.value_curves import InputOutputCurve
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
    ThermalStandard,
    TransmissionInterface,
    VariableReserve,
)
from r2x_sienna.models.costs import RenewableGenerationCost, ThermalGenerationCost
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
        ramp_limits=UpDown(up=10.0, down=10.0),
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
