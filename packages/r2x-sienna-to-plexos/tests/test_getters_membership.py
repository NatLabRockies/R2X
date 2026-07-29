"""Direct getter coverage tests for Sienna-to-PLEXOS."""

from __future__ import annotations

import pytest
from infrasys.value_curves import LinearCurve
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSLine,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_sienna.models import (
    ACBus,
    Arc,
    Area,
    EnergyReservoirStorage,
    HydroReservoir,
    HydroTurbine,
    Line,
    LoadZone,
    MinMax,
    PowerLoad,
    ThermalStandard,
    Transformer2W,
    TransmissionInterface,
    UpDown,
    VariableReserve,
)
from r2x_sienna.models.costs import (
    HydroGenerationCost,
    HydroReservoirCost,
    ThermalGenerationCost,
)
from r2x_sienna.models.enums import (
    HydroTurbineType,
    PrimeMoversType,
    ReserveType,
    ReservoirDataType,
    ReservoirLocation,
    StorageTechs,
    ThermalFuels,
)
from r2x_sienna.models.named_tuples import Complex, FromTo_ToFrom, InputOutput
from r2x_sienna_to_plexos import getters

from r2x_core import DataStore, PluginConfig, PluginContext, System


@pytest.fixture
def context(tmp_path):
    config = PluginConfig(models=("r2x_sienna.models", "r2x_plexos.models", "r2x_sienna_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ctx = PluginContext(config=config, store=store)
    ctx.source_system = System(name="source", auto_add_composed_components=True)
    ctx.target_system = System(name="target", auto_add_composed_components=True)
    return ctx


def make_context(tmp_path) -> PluginContext:
    config = PluginConfig(models=("r2x_sienna.models", "r2x_plexos.models", "r2x_sienna_to_plexos.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    ctx = PluginContext(config=config, store=store)
    ctx.source_system = System(name="source", auto_add_composed_components=True)
    ctx.target_system = System(name="target", auto_add_composed_components=True)
    return ctx


def test_get_storage_charge_discharge_efficiency_100(context):
    battery = EnergyReservoirStorage(
        name="BAT1",
        available=True,
        bus=ACBus(name="N1", base_voltage=115.0, number=1),
        prime_mover_type=PrimeMoversType.BA,
        storage_technology_type=StorageTechs.OTHER_CHEM,
        storage_capacity=1000.0,
        storage_level_limits=MinMax(min=0.1, max=0.9),
        initial_storage_capacity_level=0.5,
        rating=250.0,
        active_power=0.0,
        input_active_power_limits=MinMax(min=0.0, max=200.0),
        output_active_power_limits=MinMax(min=0.0, max=200.0),
        efficiency=InputOutput(input=1.0, output=1.0),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    assert getters.get_battery_charge_efficiency(battery, context).unwrap() == 100.0
    assert getters.get_battery_discharge_efficiency(battery, context).unwrap() == 100.0


def test_get_interface_min_max_flow(context):
    ti = TransmissionInterface(
        name="TI1",
        active_power_flow_limits=MinMax(min=10.0, max=20.0),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    assert getters.get_interface_min_flow(ti, context).unwrap() == -99999.0
    assert getters.get_interface_max_flow(ti, context).unwrap() == 99999.0


def test_membership_parent_component(context):
    dummy = object()
    assert getters.membership_parent_component(dummy, context).unwrap() is dummy


def test_get_head_tail_storage_uuid(context):
    hydro = HydroReservoir(
        name="hydro-reservoir-test",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )
    assert isinstance(getters.get_head_storage_uuid(hydro, context).unwrap(), str)
    assert isinstance(getters.get_tail_storage_uuid(hydro, context).unwrap(), str)


def test_get_area_units_and_load(context):
    area = Area(name="A1", category="region")
    assert getters.get_area_units(area, context).unwrap() == 0.0
    assert getters.get_area_load(area, context).unwrap() == 0.0


def test_get_head_tail_storage_name(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )
    hydro = HydroReservoir(
        name="hydro1",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )
    assert getters.get_head_storage_name(hydro, context).unwrap() == "hydro1_head"
    assert getters.get_tail_storage_name(hydro, context).unwrap() == "hydro1_tail"


def test_get_head_tail_storage_name_without_pumped_storage_association(context):
    hydro = HydroReservoir(
        name="hydro1",
        available=True,
        storage_level_limits=MinMax(min=0.0, max=1000.0),
        initial_level=0.5,
        spillage_limits=MinMax(min=0.0, max=100.0),
        inflow=50.0,
        outflow=30.0,
        level_targets=0.8,
        intake_elevation=500.0,
        head_to_volume_factor=LinearCurve(1.0),
        reservoir_location=ReservoirLocation.HEAD,
        operation_cost=HydroReservoirCost(),
        level_data_type=ReservoirDataType.USABLE_VOLUME,
        category="hydro_reservoir",
    )

    assert getters.get_head_storage_name(hydro, context).is_err()
    assert getters.get_tail_storage_name(hydro, context).is_err()


def test_reservoir_association_true_for_hydropumpturbine_links(context):
    pump_turbine = type("HydroPumpTurbine", (), {})()
    reservoir = type(
        "ReservoirProxy",
        (),
        {
            "upstream_turbines": [pump_turbine],
            "downstream_turbines": [],
        },
    )()

    assert getters._reservoir_has_hydro_pumped_storage_association(reservoir, context)


def test_reservoir_association_false_for_hydroturbine_links(context):
    hydro_turbine = type("HydroTurbine", (), {})()
    reservoir = type(
        "ReservoirProxy",
        (),
        {
            "upstream_turbines": [],
            "downstream_turbines": [hydro_turbine],
        },
    )()

    assert not getters._reservoir_has_hydro_pumped_storage_association(reservoir, context)


def test_membership_component_child_node_generator(context):
    gen = PLEXOSGenerator(name="GEN1")
    node = PLEXOSNode(name="N1")
    bus = ACBus(name="N1", number=1)
    context.source_system.add_component(bus)
    source_gen = ThermalStandard(
        name="GEN1",
        must_run=False,
        bus=bus,
        status=False,
        base_power=100.0,
        rating=200.0,
        active_power=0.0,
        reactive_power=0.0,
        active_power_limits=MinMax(min=0, max=1),
        prime_mover_type=PrimeMoversType.CC,
        fuel=ThermalFuels.NATURAL_GAS,
        operation_cost=ThermalGenerationCost.example(),
        time_at_status=1_000,
    )
    context.source_system.add_component(source_gen)
    context.target_system.add_component(node)
    context.target_system.add_component(gen)
    assert getters.membership_component_child_node(gen, context).unwrap().name == "N1"


def test_membership_component_child_node_battery(context):
    bat = PLEXOSBattery(name="BAT1")
    node = PLEXOSNode(name="N2")
    bus = ACBus(name="N2", number=2)
    context.source_system.add_component(bus)

    source_bat = EnergyReservoirStorage(
        name="BAT1",
        available=True,
        bus=bus,
        prime_mover_type=PrimeMoversType.BA,
        storage_technology_type=StorageTechs.OTHER_CHEM,
        storage_capacity=1000.0,
        storage_level_limits=MinMax(min=0.1, max=0.9),
        initial_storage_capacity_level=0.5,
        rating=250.0,
        active_power=0.0,
        input_active_power_limits=MinMax(min=0.0, max=200.0),
        output_active_power_limits=MinMax(min=0.0, max=200.0),
        efficiency=InputOutput(input=0.95, output=0.95),
        reactive_power=0.0,
        reactive_power_limits=MinMax(min=-50.0, max=50.0),
        base_power=250.0,
        conversion_factor=1.0,
        storage_target=0.5,
        cycle_limits=5000,
    )
    context.source_system.add_component(source_bat)
    context.target_system.add_component(node)
    context.target_system.add_component(bat)
    assert getters.membership_component_child_node(bat, context).unwrap().name == "N2"


def test_membership_node_child_zone_by_name(context):
    area = Area(name="A1")
    zone = LoadZone(name="Z1")
    bus = ACBus(name="N1", area=area, load_zone=zone, number=1)
    node = PLEXOSNode(name="N1")
    target_zone = PLEXOSZone(name="Z1")

    context.source_system.add_component(area)
    context.source_system.add_component(zone)
    context.source_system.add_component(bus)
    context.target_system.add_component(node)
    context.target_system.add_component(target_zone)

    result = getters.membership_node_child_zone(node, context)
    assert result.is_ok()
    assert result.unwrap() == target_zone


def test_membership_node_child_zone_by_uuid(context):
    zone_uuid = "11111111-1111-4111-8111-111111111111"
    area = Area(name="A1")
    source_zone = LoadZone(name="source-zone-name", uuid=zone_uuid)
    bus = ACBus(name="N1", area=area, load_zone=source_zone, number=1)
    node = PLEXOSNode(name="N1")
    target_zone = PLEXOSZone(name="Z_from_uuid", uuid=zone_uuid)

    context.source_system.add_component(area)
    context.source_system.add_component(source_zone)
    context.source_system.add_component(bus)
    context.target_system.add_component(node)
    context.target_system.add_component(target_zone)

    result = getters.membership_node_child_zone(node, context)
    assert result.is_ok()
    assert result.unwrap() == target_zone


def test_membership_region_parent_node(context):
    region = PLEXOSRegion(name="A1")
    node = PLEXOSNode(name="A1")
    area = Area(name="A1")
    bus = ACBus(name="A1", area=area, number=1)
    context.target_system.add_component(region)
    context.target_system.add_component(node)
    context.source_system.add_component(area)
    context.source_system.add_component(bus)
    assert getters.membership_region_parent_node(region, context).unwrap().name == "A1"


def test_membership_line_from_to_parent_node(context):
    line = PLEXOSLine(name="L1")
    node_from = PLEXOSNode(name="N1")
    node_to = PLEXOSNode(name="N2")
    bus_from = ACBus(name="N1", number=1)
    bus_to = ACBus(name="N2", number=2)
    context.source_system.add_component(bus_from)
    context.source_system.add_component(bus_to)
    arc = Arc(from_to=bus_from, to_from=bus_to)
    context.source_system.add_component(arc)

    source_line = Line(
        name="L1",
        arc=arc,
        rating=100.0,
        r=0.01,
        x=0.1,
        b=FromTo_ToFrom(from_to=3.0, to_from=3.0),
        active_power_flow=100,
        reactive_power_flow=100,
        angle_limits=MinMax(min=-0.03, max=0.03),
    )

    context.source_system.add_component(source_line)
    context.target_system.add_component(line)
    context.target_system.add_component(node_from)
    context.target_system.add_component(node_to)
    assert getters.membership_line_from_parent_node(line, context).unwrap().name == "N1"
    assert getters.membership_line_to_parent_node(line, context).unwrap().name == "N2"


def test_membership_transformer_from_to_parent_node(context):
    transformer = PLEXOSTransformer(name="T1")
    node_from = PLEXOSNode(name="N1")
    node_to = PLEXOSNode(name="N2")
    bus_from = ACBus(name="N1", number=1)
    bus_to = ACBus(name="N2", number=2)
    context.source_system.add_component(bus_from)
    context.source_system.add_component(bus_to)

    arc = Arc(from_to=bus_from, to_from=bus_to)
    context.source_system.add_component(arc)

    source_transformer = Transformer2W(
        name="T1",
        arc=arc,
        primary_shunt=Complex(real=0.0, imag=0.0),
        rating=50.0,
        base_power=2.0,
        x=0.1,
        r=0.01,
    )

    context.source_system.add_component(source_transformer)
    context.target_system.add_component(transformer)
    context.target_system.add_component(node_from)
    context.target_system.add_component(node_to)
    assert getters.membership_transformer_from_parent_node(transformer, context).unwrap().name == "N1"
    assert getters.membership_transformer_to_parent_node(transformer, context).unwrap().name == "N2"


def test_membership_head_tail_storage_generator(context, monkeypatch):
    monkeypatch.setattr(getters, "_is_hydro_pumped_storage_generator", lambda _ctx, _name: True)

    bus1 = ACBus(name="N2", base_voltage=115.0, number=1)
    context.source_system.add_component(bus1)
    ht = HydroTurbine(
        name="hydro1_Turbine",
        available=True,
        bus=bus1,
        active_power=120.0,
        reactive_power=0.0,
        rating=150.0,
        active_power_limits=MinMax(min=15.0, max=150.0),
        reactive_power_limits=MinMax(min=-45.0, max=45.0),
        base_power=150.0,
        operation_cost=HydroGenerationCost.example(),
        powerhouse_elevation=350.0,
        ramp_limits=UpDown(up=8.0, down=8.0),
        time_limits=UpDown(up=1.5, down=1.5),
        outflow_limits=MinMax(min=5.0, max=100.0),
        efficiency=0.92,
        turbine_type=HydroTurbineType.FRANCIS,
        prime_mover_type=PrimeMoversType.OT,
        conversion_factor=1.0,
        reservoirs=[],
        category="hydro_turbine",
    )
    storage_head = PLEXOSStorage(name="hydro1_Reservoir_head")
    storage_tail = PLEXOSStorage(name="hydro1_Reservoir_tail")
    context.target_system.add_component(storage_head)
    context.target_system.add_component(storage_tail)
    assert getters.membership_head_storage_generator(ht, context).unwrap().name == "hydro1_Reservoir_head"
    assert getters.membership_tail_storage_generator(ht, context).unwrap().name == "hydro1_Reservoir_tail"


def test_membership_collection_nodes(context):
    dummy = object()
    assert getters.membership_collection_nodes(dummy, context).unwrap().name == "Nodes"


def test_membership_collection_lines(context):
    dummy = object()
    assert getters.membership_collection_lines(dummy, context).unwrap().name == "Lines"


def test_membership_collection_generators(context):
    dummy = object()
    assert getters.membership_collection_generators(dummy, context).unwrap().name == "Generators"


def test_membership_collection_batteries(context):
    dummy = object()
    assert getters.membership_collection_batteries(dummy, context).unwrap().name == "Batteries"


def test_membership_collection_region(context):
    dummy = object()
    assert getters.membership_collection_region(dummy, context).unwrap().name == "Region"


def test_membership_collection_node_from(context):
    dummy = object()
    assert getters.membership_collection_node_from(dummy, context).unwrap().name == "NodeFrom"


def test_membership_collection_node_to(context):
    dummy = object()
    assert getters.membership_collection_node_to(dummy, context).unwrap().name == "NodeTo"


def test_membership_collection_head_storage(context):
    dummy = object()
    assert getters.membership_collection_head_storage(dummy, context).unwrap().name == "HeadStorage"


def test_membership_collection_tail_storage(context):
    dummy = object()
    assert getters.membership_collection_tail_storage(dummy, context).unwrap().name == "TailStorage"


def test_get_head_storage_uuid(context):
    hydro = HydroReservoir(
        name="HeadReservoir",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert isinstance(getters.get_head_storage_uuid(hydro, context).unwrap(), str)


def test_get_tail_storage_uuid(context):
    hydro = HydroReservoir(
        name="TailReservoir",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert isinstance(getters.get_tail_storage_uuid(hydro, context).unwrap(), str)


def test_get_area_units(context):
    area = Area(name="A1", category="region")
    assert getters.get_area_units(area, context).unwrap() == 0.0


def test_get_area_units_active_when_region_has_positive_lpf(context):
    area = Area(name="A1", category="region")
    bus = ACBus(name="N1", area=area, base_voltage=115.0, number=1)
    load = PowerLoad(name="Load-1", bus=bus, max_active_power=100.0)

    context.source_system.add_component(area)
    context.source_system.add_component(bus)
    context.source_system.add_component(load)

    assert getters.get_area_units(area, context).unwrap() == 1.0


def test_get_area_load(context):
    area = Area(name="A1", category="region")
    assert getters.get_area_load(area, context).unwrap() == 0.0


def test_get_head_storage_name(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    hydro = HydroReservoir(
        name="hydro1_head",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert getters.get_head_storage_name(hydro, context).unwrap() == "hydro1_head"


def test_get_tail_storage_name(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    hydro = HydroReservoir(
        name="hydro1_tail",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
    )
    assert getters.get_tail_storage_name(hydro, context).unwrap() == "hydro1_tail"


def test_head_tail_storage_name_infers_location_from_suffix_when_missing(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    head = HydroReservoir(
        name="Plant_head",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.HEAD,
        ext={"plant_name": "Plant"},
    )
    tail = HydroReservoir(
        name="Plant_tail",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.TAIL,
        ext={"plant_name": "Plant"},
    )

    assert getters.get_head_storage_name(head, context).unwrap() == "Plant_head"
    assert getters.get_tail_storage_name(head, context).is_err()
    assert getters.get_head_storage_name(tail, context).is_err()
    assert getters.get_tail_storage_name(tail, context).unwrap() == "Plant_tail"


def test_head_tail_storage_name_suffix_overrides_conflicting_metadata(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    # Source metadata can be wrong; suffix should control head/tail assignment.
    tail_with_wrong_metadata = HydroReservoir(
        name="Abitibi Canyon_tail",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.HEAD,
        ext={"plant_name": "Abitibi Canyon"},
    )

    assert getters.get_head_storage_name(tail_with_wrong_metadata, context).is_err()
    assert getters.get_tail_storage_name(tail_with_wrong_metadata, context).unwrap() == "Abitibi Canyon_tail"


def test_unsuffixed_reservoir_skips_side_with_explicit_reservoir(context, monkeypatch):
    monkeypatch.setattr(
        getters,
        "_reservoir_has_hydro_pumped_storage_association",
        lambda _source_component, _context: True,
    )

    explicit_head = HydroReservoir(
        name="Wallace Dam_head",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.HEAD,
        ext={"plant_name": "Wallace Dam"},
    )
    unsuffixed = HydroReservoir(
        name="Wallace Dam",
        available=True,
        initial_level=500.0,
        storage_level_limits={"min": 0.0, "max": 1000.0},
        spillage_limits=None,
        inflow=0.0,
        outflow=0.0,
        level_targets=1000.0,
        level_data_type="USABLE_VOLUME",
        intake_elevation=0.0,
        operation_cost=HydroReservoirCost.example(),
        reservoir_location=ReservoirLocation.TAIL,
        ext={"plant_name": "Wallace Dam"},
    )

    context.source_system.add_component(explicit_head)
    context.source_system.add_component(unsuffixed)

    assert getters.get_head_storage_name(explicit_head, context).unwrap() == "Wallace Dam_head"
    assert getters.get_head_storage_name(unsuffixed, context).is_err()
    assert getters.get_tail_storage_name(unsuffixed, context).unwrap() == "Wallace Dam_tail"


def test_membership_reserve_child_generator_err(context):
    reserve = VariableReserve(
        name="missing", reserve_type=ReserveType.SPINNING, vors=10.0, direction="UP", requirement=100.0
    )
    result = getters.membership_reserve_child_generator(reserve, context)
    assert result.is_err()


def test_membership_reserve_child_battery_err(context):
    reserve = VariableReserve(
        name="missing", reserve_type=ReserveType.SPINNING, vors=10.0, direction="UP", requirement=100.0
    )
    result = getters.membership_reserve_child_battery(reserve, context)
    assert result.is_err()


def test_membership_component_child_node_err(context):
    gen = PLEXOSGenerator(name="missing")
    result = getters.membership_component_child_node(gen, context)
    assert result.is_err()


def test_membership_interface_child_line_err(context):
    interface = TransmissionInterface(
        name="ExampleTransmissionInterface",
        active_power_flow_limits=MinMax(min=-100, max=100),
        direction_mapping={"line-01": 1, "line-02": -2},
    )
    result = getters.membership_interface_child_line(interface, context)
    assert result.is_err()
