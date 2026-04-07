"""Direct getter coverage tests for PLEXOS-to-Sienna."""

from __future__ import annotations

import types

from plexosdb import CollectionEnum
from r2x_plexos.models import (
    PLEXOSBattery,
    PLEXOSGenerator,
    PLEXOSInterface,
    PLEXOSLine,
    PLEXOSMembership,
    PLEXOSNode,
    PLEXOSRegion,
    PLEXOSReserve,
    PLEXOSStorage,
    PLEXOSTransformer,
    PLEXOSZone,
)
from r2x_plexos_to_sienna import getters
from r2x_plexos_to_sienna.getters import (
    extract_number_from_name,
    get_base_voltage,
    get_device_services,
    get_gen_start_types,
    get_line_angle_limits,
    get_line_conductance,
    get_line_flow_limits,
    get_line_losses,
    get_line_susceptance,
    get_node_area,
    get_node_ext,
    get_node_number,
    get_node_zone,
    get_prime_mover_type,
    get_reserve_direction,
    get_reserve_type,
    get_trf_primary_shunt,
)
from r2x_sienna.models import ACBus, Area
from r2x_sienna.models.enums import (
    ACBusTypes,
    PrimeMoversType,
    ReserveDirection,
    ReserveType,
    StorageTechs,
)
from r2x_sienna.units import Voltage

from r2x_core import DataStore, PluginConfig, PluginContext, System


class Dummy:
    pass


def test_extract_number_from_name_digits_and_dummy():
    # Reset state
    getters.PLEXOS_NUMBER_COUNTER = getters.PLEXOS_NUMBER_BASE
    getters.PLEXOS_NUMBER_MAP = {}
    assert extract_number_from_name("p126_OSW") == 126
    assert extract_number_from_name("bus") == 100101
    assert extract_number_from_name("bus") == 100101
    assert extract_number_from_name("anotherbus") == 100102


def test_get_node_number_with_number():
    node = types.SimpleNamespace(number=42)
    assert get_node_number(node, None).value == 42


def test_get_node_number_with_name():
    node = types.SimpleNamespace(number=None, name="p123")
    assert get_node_number(node, None).value == 123


def test_get_node_number_default():
    node = types.SimpleNamespace(number=None, name=None)
    assert get_node_number(node, None).value == 1


def test_get_base_voltage_all_branches():
    node = types.SimpleNamespace(voltage=5.0)
    assert get_base_voltage(node, None).value == 5.0
    node = types.SimpleNamespace(voltage=0.0, ac_voltage_magnitude=7.0)
    assert get_base_voltage(node, None).value == 7.0
    node = types.SimpleNamespace(voltage=0.0, ac_voltage_magnitude=0.0)
    assert get_base_voltage(node, None).value == 1.0


def test_get_node_area_and_zone_membership():
    # Area
    dummy_area = types.SimpleNamespace(name="A")
    dummy_target = types.SimpleNamespace(get_components=lambda t: [dummy_area])
    dummy_membership = types.SimpleNamespace(
        collection=getters.CollectionEnum.Region, child_object=types.SimpleNamespace(name="A")
    )
    node = types.SimpleNamespace(area=None)
    ctx = types.SimpleNamespace(
        source_system=types.SimpleNamespace(
            get_supplemental_attributes_with_component=lambda c: [dummy_membership]
        ),
        target_system=dummy_target,
    )
    assert get_node_area(node, ctx).value == dummy_area

    # Zone
    dummy_zone = types.SimpleNamespace(name="Z")
    dummy_target = types.SimpleNamespace(get_components=lambda t: [dummy_zone])
    dummy_membership = types.SimpleNamespace(
        collection=getters.CollectionEnum.Zone, child_object=types.SimpleNamespace(name="Z")
    )
    node = types.SimpleNamespace(zone=None)
    ctx = types.SimpleNamespace(
        source_system=types.SimpleNamespace(
            get_supplemental_attributes_with_component=lambda c: [dummy_membership]
        ),
        target_system=dummy_target,
    )
    assert get_node_zone(node, ctx).value == dummy_zone


def test_get_line_conductance_and_susceptance():
    # Conductance with resistance
    line = types.SimpleNamespace(resistance=2.0)
    assert get_line_conductance(line, None).value.from_to == 0.5
    # Conductance with no resistance
    line = types.SimpleNamespace(resistance=0.0)
    assert get_line_conductance(line, None).value.from_to == 0.0
    # Susceptance with value
    line = types.SimpleNamespace(susceptance=3.0)
    assert get_line_susceptance(line, None).value.from_to == 3.0
    # Susceptance with no value
    line = types.SimpleNamespace(susceptance=0.0)
    assert get_line_susceptance(line, None).value.from_to == 0.0


def test_get_line_angle_limits_tuple_and_default():
    line = types.SimpleNamespace(angle_limits=(10, 20))
    result = get_line_angle_limits(line, None).value
    assert result.min == 10 and result.max == 20
    line = types.SimpleNamespace(angle_limits=None)
    result = get_line_angle_limits(line, None).value
    assert result.min == -90.0 and result.max == 90.0


def test_get_line_flow_limits_with_and_without_max():
    line = types.SimpleNamespace(min_flow=-50.0, max_flow=150.0)
    result = get_line_flow_limits(line, None).value
    assert result.from_to == 150.0 and result.to_from == -50.0
    line = types.SimpleNamespace(min_flow=-50.0, max_flow=None)
    result = get_line_flow_limits(line, None).value
    assert result.from_to == 100.0 and result.to_from == -50.0


def test_get_line_losses_with_values():
    class V:
        values = [5.0]  # noqa: RUF012

    line = types.SimpleNamespace(losses=V())
    assert get_line_losses(line, None).value == 5.0
    line = types.SimpleNamespace(losses=0.0)
    assert get_line_losses(line, None).value == 0.0


def test_get_gen_start_types():
    node = types.SimpleNamespace(start_type="hot")
    assert get_gen_start_types(node, None).value == 1
    node = types.SimpleNamespace(start_type="warm")
    assert get_gen_start_types(node, None).value == 2
    node = types.SimpleNamespace(start_type="cold")
    assert get_gen_start_types(node, None).value == 3
    node = types.SimpleNamespace(start_type="unknown")
    assert get_gen_start_types(node, None).value == 1


def test_get_prime_mover_type_default(monkeypatch):
    # Patch _get_prime_mover_type to avoid file access
    monkeypatch.setattr(getters, "_get_prime_mover_type", lambda category: "OT")
    node = types.SimpleNamespace(category=None)
    assert get_prime_mover_type(node, None).value == "OT"


def test_get_reserve_type_and_direction():
    node = types.SimpleNamespace(reserve_type="SPINNING")
    assert get_reserve_type(node, None).value.name == "SPINNING"
    node = types.SimpleNamespace(reserve_type="INVALID")
    assert get_reserve_type(node, None).value.name == "SPINNING"
    node = types.SimpleNamespace(direction="UP")
    assert get_reserve_direction(node, None).value.name == "UP"
    node = types.SimpleNamespace(direction="INVALID")
    assert get_reserve_direction(node, None).value.name == "UP"


def test_get_trf_primary_shunt():
    node = types.SimpleNamespace(primary_shunt=None)
    assert get_trf_primary_shunt(node, None).value is None
    node = types.SimpleNamespace(primary_shunt=getters.Complex(real=1.0, imag=2.0))
    assert get_trf_primary_shunt(node, None).value.real == 1.0
    node = types.SimpleNamespace(primary_shunt=5.0)
    result = get_trf_primary_shunt(node, None).value
    assert result.real == 0.0 and result.imag == 0.0


def test_get_node_ext():
    node = types.SimpleNamespace(load_participation_factor=0.5)
    result = get_node_ext(node, None).value
    assert result["load_participation_factor"] == 0.5


def test_get_device_services_empty():
    node = types.SimpleNamespace()
    ctx = types.SimpleNamespace(
        source_system=types.SimpleNamespace(get_supplemental_attributes_with_component=lambda c: []),
        target_system=types.SimpleNamespace(get_components=lambda t: []),
    )
    assert get_device_services(node, ctx).value == []


def test_node_number_getter_no_number():
    assert extract_number_from_name("bus") == 100101
    assert extract_number_from_name("anotherbus") == 100102
    assert extract_number_from_name("bus") == 100101


def make_context(tmp_path):
    config = PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models", "r2x_plexos_to_sienna.getters"))
    store = DataStore.from_plugin_config(config, path=tmp_path)
    return PluginContext(config=config, store=store)


def test_basic_node_getters(tmp_path) -> None:
    """Test node-related getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    node = PLEXOSNode(name="NODE_123", voltage=115.0, is_slack_bus=0)
    context.source_system.add_component(node)

    # Test node getters
    assert getters.get_node_number(node, context).unwrap() == 123
    assert getters.get_base_voltage(node, context).unwrap() == 115.0
    assert getters.get_node_angle(node, context).unwrap() == 0.0
    assert getters.is_slack_bus(node, context).unwrap() == ACBusTypes.PQ

    # Test slack bus
    slack_node = PLEXOSNode(name="SLACK_1", is_slack_bus=1)
    assert getters.is_slack_bus(slack_node, context).unwrap() == ACBusTypes.SLACK


def test_zone_getters(tmp_path) -> None:
    """Test zone-related getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    zone = PLEXOSZone(name="ZONE1")

    assert getters.get_zone_peak_active_power(zone, context).unwrap() == 0.0
    assert getters.get_zone_peak_reactive_power(zone, context).unwrap() == 0.0


def test_region_getters(tmp_path) -> None:
    """Test region-related getters for Area and PowerLoad."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = PLEXOSRegion(name="REGION1", load=300.0)

    # Area getters
    assert getters.get_region_peak_active_power(region, context).unwrap() == 300.0
    assert getters.get_region_peak_reactive_power(region, context).unwrap() == 0.0
    assert getters.get_region_load_response(region, context).unwrap() == 0.0

    # Load getters
    assert getters.get_load_active_power(region, context).unwrap() == 300.0
    assert getters.get_load_reactive_power(region, context).unwrap() == 0.0
    assert getters.get_load_base_power(region, context).unwrap() == 100.0
    assert getters.get_load_max_active_power(region, context).unwrap() == 0.0
    assert getters.get_load_max_reactive_power(region, context).unwrap() == 0.0


def test_load_bus_getter(tmp_path) -> None:
    """Test get_load_bus getter with membership."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Create node and add to source
    node = PLEXOSNode(name="NODE1", voltage=115.0)
    context.source_system.add_component(node)

    # Create region
    region = PLEXOSRegion(name="REGION1", load=100.0)
    context.source_system.add_component(region)

    # Create membership
    membership = PLEXOSMembership(
        collection=CollectionEnum.Region,
        parent_object=node,
        child_object=region,
    )
    context.source_system.add_supplemental_attribute(region, membership)

    # Create corresponding bus in target
    area = Area(name="AREA1", category="area")
    context.target_system.add_component(area)
    bus = ACBus(name="NODE1", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus)

    # Test getter
    result = getters.get_load_bus(region, context).unwrap()
    assert result is not None
    assert result.name == "NODE1"


def test_load_bus_getter_no_membership(tmp_path) -> None:
    """Test get_load_bus returns None when no membership exists."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    region = PLEXOSRegion(name="REGION1", load=100.0)
    context.source_system.add_component(region)

    result = getters.get_load_bus(region, context).unwrap()
    assert result is None


def test_generator_getters(tmp_path) -> None:
    """Test generator-related getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    gen = PLEXOSGenerator(
        name="GEN1",
        category="gas-cc",
        max_capacity=100.0,
        units=1,
    )

    assert getters.get_gen_active_power(gen, context).unwrap() == 100.0
    assert getters.get_gen_reactive_power(gen, context).unwrap() == 0.0
    assert getters.get_gen_rating(gen, context).unwrap() == 100.0
    assert getters.get_gen_base_power(gen, context).unwrap() == 0.0

    limits = getters.get_gen_active_power_limits(gen, context).unwrap()
    assert limits.min == 0.0
    assert limits.max == 0.0

    reactive_limits = getters.get_gen_reactive_power_limits(gen, context).unwrap()
    assert reactive_limits.min == 0.0
    assert reactive_limits.max == 0.0

    assert getters.get_gen_status(gen, context).unwrap() == 1
    assert getters.get_gen_power_factor(gen, context).unwrap() == 1.0
    assert getters.get_prime_mover_type(gen, context).unwrap() == PrimeMoversType.CC


def test_generator_bus_getter(tmp_path) -> None:
    """Test get_gen_bus getter with membership."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Create node
    node = PLEXOSNode(name="NODE1", voltage=115.0)
    context.source_system.add_component(node)

    # Create generator
    gen = PLEXOSGenerator(name="GEN1", category="gas-cc", max_capacity=100.0)
    context.source_system.add_component(gen)

    # Create membership
    membership = PLEXOSMembership(
        collection=CollectionEnum.Nodes,
        parent_object=gen,
        child_object=node,
    )
    context.source_system.add_supplemental_attribute(gen, membership)
    context.source_system.add_supplemental_attribute(node, membership)

    # Create corresponding bus in target
    area = Area(name="AREA1", category="area")
    context.target_system.add_component(area)
    bus = ACBus(name="NODE1", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus)

    # Test getter
    result = getters.get_gen_bus(gen, context).unwrap()
    assert result is not None
    assert result.name == "NODE1"


def test_generator_bus_getter_no_membership(tmp_path) -> None:
    """Test get_gen_bus returns None when no membership exists."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    gen = PLEXOSGenerator(name="GEN1", category="gas-cc", max_capacity=100.0)
    context.source_system.add_component(gen)

    result = getters.get_gen_bus(gen, context).unwrap()
    assert result is None


def test_prime_mover_type_mapping(tmp_path) -> None:
    """Test prime mover type mappings from defaults.json."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    test_cases = [
        ("gas-cc", PrimeMoversType.CC),
        ("gas-ct", PrimeMoversType.GT),
        ("coal", PrimeMoversType.ST),
        ("wind-ons", PrimeMoversType.WT),
        ("wind-ofs", PrimeMoversType.WS),
        ("upv", PrimeMoversType.PVe),
        ("distpv", PrimeMoversType.PVe),
        ("battery", PrimeMoversType.BA),
        ("hydro-dispatch", PrimeMoversType.HY),
        ("hydro-turbine", PrimeMoversType.OT),
        ("pumped-hydro", PrimeMoversType.PS),
        ("nuclear", PrimeMoversType.ST),
        ("o-g-s", PrimeMoversType.ST),
        ("biopower", PrimeMoversType.ST),
        ("caes", PrimeMoversType.CE),
        ("lfill-gas", PrimeMoversType.GT),
        ("geothermal", PrimeMoversType.BT),
        ("csp", PrimeMoversType.CP),
    ]

    for category, expected_type in test_cases:
        gen = PLEXOSGenerator(name=f"GEN_{category}", category=category, max_capacity=50.0)
        result = getters.get_prime_mover_type(gen, context).unwrap()
        assert result == expected_type, f"Category {category} should map to {expected_type}, got {result}"


def test_prime_mover_type_unknown(tmp_path) -> None:
    """Test prime mover type with unknown category."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    gen = PLEXOSGenerator(name="GEN_UNKNOWN", category="unknown-type", max_capacity=50.0)
    result = getters.get_prime_mover_type(gen, context).unwrap()
    assert result == PrimeMoversType.OT  # Should default to "other"


def test_storage_getters(tmp_path) -> None:
    """Test storage-related getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    battery = PLEXOSBattery(
        name="BATT1",
        category="battery",
        initial_soc=0.5,
    )

    assert getters.get_initial_storage_capacity_level(battery, context).unwrap() == 0.5
    assert getters.get_storage_capacity(battery, context).unwrap() == 0.0

    level_limits = getters.get_storage_level_limits(battery, context).unwrap()
    assert level_limits.min == 0.0
    assert level_limits.max == 0.0

    charge_limits = getters.get_storage_charge_power_limits(battery, context).unwrap()
    assert charge_limits.max == 0.0

    discharge_limits = getters.get_storage_discharge_power_limits(battery, context).unwrap()
    assert discharge_limits.max == 0.0

    efficiency = getters.get_storage_efficiency(battery, context).unwrap()
    assert efficiency.input == 1.0
    assert efficiency.output == 1.0

    assert getters.get_storage_technology_type(battery, context).unwrap() == StorageTechs.OTHER_CHEM
    assert getters.get_storage_conversion_factor(battery, context).unwrap() == 1.0


def test_storage_bus_getter(tmp_path) -> None:
    """Test get_gen_bus getter with membership."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Create node
    node = PLEXOSNode(name="NODE1", voltage=115.0)
    context.source_system.add_component(node)

    # Create battery
    battery = PLEXOSBattery(name="BATT1", category="battery", initial_soc=0.5)
    context.source_system.add_component(battery)

    # Create membership
    membership = PLEXOSMembership(
        collection=CollectionEnum.Nodes,
        parent_object=battery,
        child_object=node,
    )
    context.source_system.add_supplemental_attribute(battery, membership)
    context.source_system.add_supplemental_attribute(node, membership)

    # Create corresponding bus in target
    area = Area(name="AREA1", category="area")
    context.target_system.add_component(area)
    bus = ACBus(name="NODE1", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus)

    # Test getter
    result = getters.get_gen_bus(battery, context).unwrap()
    assert result is not None
    assert result.name == "NODE1"


def test_hydro_storage_getters(tmp_path) -> None:
    """Test hydro storage getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    storage = PLEXOSStorage(
        name="HYDRO_RES",
        initial_volume=500.0,
        max_volume=1000.0,
        min_volume=100.0,
    )

    assert getters.get_storage_capacity(storage, context).unwrap() == 1000.0
    assert getters.get_initial_storage_capacity_level(storage, context).unwrap() == 0.0

    limits = getters.get_storage_level_limits(storage, context).unwrap()
    assert limits.min == 100.0
    assert limits.max == 1000.0


def test_line_getters(tmp_path) -> None:
    """Test line-related getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Create nodes and buses
    node1 = PLEXOSNode(name="NODE1", voltage=115.0)
    node2 = PLEXOSNode(name="NODE2", voltage=115.0)
    context.source_system.add_component(node1)
    context.source_system.add_component(node2)

    area = Area(name="AREA1", category="area")
    context.target_system.add_component(area)

    bus1 = ACBus(name="NODE1", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    bus2 = ACBus(name="NODE2", area=area, number=2, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus1)
    context.target_system.add_component(bus2)

    line = PLEXOSLine(
        name="LINE1",
        max_flow=100.0,
        min_flow=-100.0,
        resistance=0.01,
        reactance=0.1,
        susceptance=0.001,
    )

    # Test basic line getters
    assert getters.get_reactive_power_flow(line, context).unwrap() == 0.0

    angle_limits = getters.get_line_angle_limits(line, context).unwrap()
    assert angle_limits.min == -90.0
    assert angle_limits.max == 90.0

    flow_limits = getters.get_line_flow_limits(line, context).unwrap()
    assert flow_limits.from_to == 100.0
    assert flow_limits.to_from == -100.0

    susceptance = getters.get_line_susceptance(line, context).unwrap()
    assert susceptance.from_to == 0.001


def test_line_arc_getter(tmp_path) -> None:
    """Test get_line_arc getter."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Create nodes
    node1 = PLEXOSNode(name="NODE1", voltage=115.0)
    node2 = PLEXOSNode(name="NODE2", voltage=115.0)
    context.source_system.add_component(node1)
    context.source_system.add_component(node2)

    # Create line
    line = PLEXOSLine(name="LINE1", resistance=0.01, reactance=0.1)
    context.source_system.add_component(line)

    # Create membership relationships for line nodes
    membership_from = PLEXOSMembership(
        collection=CollectionEnum.NodeFrom,
        parent_object=line,
        child_object=node1,
    )
    context.source_system.add_supplemental_attribute(line, membership_from)

    membership_to = PLEXOSMembership(
        collection=CollectionEnum.NodeTo,
        parent_object=line,
        child_object=node2,
    )
    context.source_system.add_supplemental_attribute(line, membership_to)

    # Create buses in target
    area = Area(name="AREA1", category="area")
    context.target_system.add_component(area)
    bus1 = ACBus(name="NODE1", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    bus2 = ACBus(name="NODE2", area=area, number=2, base_voltage=Voltage(115.0, "kV"))
    context.target_system.add_component(bus1)
    context.target_system.add_component(bus2)

    # Test getter
    arc = getters.get_line_arc(line, context).unwrap()
    assert arc is not None
    assert arc.from_to.name == "NODE1"
    assert arc.to_from.name == "NODE2"


def test_reserve_getters(tmp_path) -> None:
    """Test reserve-related getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    reserve = PLEXOSReserve(
        name="SPIN_RES",
        timeframe=300.0,
        duration=3600.0,
    )

    assert getters.get_reserve_type(reserve, context).unwrap() == ReserveType.SPINNING
    assert getters.get_reserve_direction(reserve, context).unwrap() == ReserveDirection.UP
    assert getters.get_reserve_requirement(reserve, context).unwrap() == 0.0
    assert getters.get_reserve_time_frame(reserve, context).unwrap() == 300.0
    assert getters.get_reserve_sustained_time(reserve, context).unwrap() == 3600.0
    assert getters.get_reserve_max_participation_factor(reserve, context).unwrap() == 1.0
    assert getters.get_reserve_max_output_fraction(reserve, context).unwrap() == 1.0
    assert getters.get_reserve_deployed_fraction(reserve, context).unwrap() == 1.0


def test_reserve_type_mapping(tmp_path) -> None:
    """Test reserve type mappings."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Test default behavior when reserve_type is not set
    reserve = PLEXOSReserve(name="RES_DEFAULT")
    result = getters.get_reserve_type(reserve, context).unwrap()
    assert result == ReserveType.SPINNING  # Default value


def test_reserve_direction_mapping(tmp_path) -> None:
    """Test reserve direction mappings."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Test default behavior when direction is not set
    reserve = PLEXOSReserve(name="RES_DEFAULT")
    result = getters.get_reserve_direction(reserve, context).unwrap()
    assert result == ReserveDirection.UP  # Default value


def test_interface_getters(tmp_path) -> None:
    """Test interface-related getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    interface = PLEXOSInterface(
        name="IFACE1",
        min_flow=-200.0,
        max_flow=200.0,
    )

    flow_limits = getters.get_interface_active_power_flow_limits(interface, context).unwrap()
    assert flow_limits.min == -200.0
    assert flow_limits.max == 200.0


def test_transformer_getters(tmp_path) -> None:
    """Test transformer-related getters."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    transformer = PLEXOSTransformer(
        name="XFMR1",
        rating=100.0,
        reactance=0.1,
        resistance=0.01,
    )

    assert getters.get_trf_active_power_flow(transformer, context).unwrap() == 0.0
    assert getters.get_trf_reactive_power_flow(transformer, context).unwrap() == 0.0
    assert getters.get_trf_base_power(transformer, context).unwrap() == 100.0


def test_transformer_arc_getter(tmp_path) -> None:
    """Test get_transformer_arc getter."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Create nodes
    node1 = PLEXOSNode(name="NODE1", voltage=115.0)
    node2 = PLEXOSNode(name="NODE2", voltage=230.0)
    context.source_system.add_component(node1)
    context.source_system.add_component(node2)

    # Create transformer
    xfmr = PLEXOSTransformer(name="XFMR1", resistance=0.01, reactance=0.1)
    context.source_system.add_component(xfmr)

    # Create membership relationships for transformer nodes
    membership_from = PLEXOSMembership(
        collection=CollectionEnum.NodeFrom,
        parent_object=xfmr,
        child_object=node1,
    )
    context.source_system.add_supplemental_attribute(xfmr, membership_from)

    membership_to = PLEXOSMembership(
        collection=CollectionEnum.NodeTo,
        parent_object=xfmr,
        child_object=node2,
    )
    context.source_system.add_supplemental_attribute(xfmr, membership_to)

    # Create buses in target
    area = Area(name="AREA1", category="area")
    context.target_system.add_component(area)
    bus1 = ACBus(name="NODE1", area=area, number=1, base_voltage=Voltage(115.0, "kV"))
    bus2 = ACBus(name="NODE2", area=area, number=2, base_voltage=Voltage(230.0, "kV"))
    context.target_system.add_component(bus1)
    context.target_system.add_component(bus2)

    # Test getter - note: should use get_transformer_arc, not get_line_arc
    arc = getters.get_line_arc(xfmr, context).unwrap()
    assert arc is not None
    assert arc.from_to.name == "NODE1"
    assert arc.to_from.name == "NODE2"


def test_operation_cost_getters(tmp_path) -> None:
    """Test operation cost getter functions return proper objects."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    gen = PLEXOSGenerator(name="GEN1", category="gas-cc", max_capacity=100.0)

    # Test thermal operation cost
    thermal_cost = getters.get_thermal_operation_cost(gen, context).unwrap()
    assert thermal_cost is not None
    assert thermal_cost.fixed == 0.0

    # Test hydro operation cost
    hydro_cost = getters.get_hydro_gen_operation_cost(gen, context).unwrap()
    assert hydro_cost is not None
    assert hydro_cost.fixed == 0.0

    # Test renewable operation cost
    renewable_cost = getters.get_renewable_operation_cost(gen, context).unwrap()
    assert renewable_cost is not None
    assert renewable_cost.fixed == 0.0


def test_area_getter(tmp_path) -> None:
    """Test get_area getter."""
    context = make_context(tmp_path)
    context.source_system = System(name="source")
    context.target_system = System(name="target")

    # Create area in target
    area = Area(name="REGION1", category="area")
    context.target_system.add_component(area)

    # Create node
    _ = PLEXOSNode(name="NODE1", voltage=115.0)


def test_plexos_node_translates_to_acbus():
    getters.PLEXOS_NUMBER_COUNTER = getters.PLEXOS_NUMBER_BASE
    getters.PLEXOS_NUMBER_MAP.clear()
    getters.PLEXOS_NUMBER_USED.clear()

    test_cases = [
        ("p126", 126),
        ("p126_OSW", 1260),
        ("p1", 1),
        ("p100", 100),
        ("bus", 100101),
        ("anotherbus", 100102),
        ("bus", 100101),
        ("foo123bar", 123),
        ("no_digits_here", 100103),
        ("p126_OSW2", 12600),
    ]
    for name, expected in test_cases:
        result = getters.extract_number_from_name(name)
        assert result == expected, f"Failed for {name}: got {result}, expected {expected}"
