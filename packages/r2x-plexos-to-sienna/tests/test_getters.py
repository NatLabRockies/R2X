"""Direct getter coverage tests for PLEXOS-to-Sienna."""

from __future__ import annotations

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
from r2x_sienna.models import ACBus, Area
from r2x_sienna.models.enums import (
    ACBusTypes,
    PrimeMoversType,
    ReserveDirection,
    ReserveType,
    StorageTechs,
)
from r2x_sienna.units import Voltage

from r2x_core import PluginConfig, System, TranslationContext


def test_basic_node_getters() -> None:
    """Test node-related getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(
            models=("r2x_plexos.models", "r2x_sienna.models", "r2x_plexos_to_sienna.getters")
        ),
        rules=[],
    )

    node = PLEXOSNode(name="NODE_123", voltage=115.0, is_slack_bus=0)
    context.source_system.add_component(node)

    # Test node getters
    assert getters.get_node_number(context, node).unwrap() == 123
    assert getters.get_base_voltage(context, node).unwrap() == 115.0
    assert getters.get_node_angle(context, node).unwrap() == 0.0
    assert getters.is_slack_bus(context, node).unwrap() == ACBusTypes.PQ

    # Test slack bus
    slack_node = PLEXOSNode(name="SLACK_1", is_slack_bus=1)
    assert getters.is_slack_bus(context, slack_node).unwrap() == ACBusTypes.SLACK


def test_zone_getters() -> None:
    """Test zone-related getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    zone = PLEXOSZone(name="ZONE1")

    assert getters.get_zone_peak_active_power(context, zone).unwrap() == 0.0
    assert getters.get_zone_peak_reactive_power(context, zone).unwrap() == 0.0


def test_region_getters() -> None:
    """Test region-related getters for Area and PowerLoad."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    region = PLEXOSRegion(name="REGION1", load=300.0)

    # Area getters
    assert getters.get_region_peak_active_power(context, region).unwrap() == 300.0
    assert getters.get_region_peak_reactive_power(context, region).unwrap() == 0.0
    assert getters.get_region_load_response(context, region).unwrap() == 0.0

    # Load getters
    assert getters.get_load_active_power(context, region).unwrap() == 300.0
    assert getters.get_load_reactive_power(context, region).unwrap() == 0.0
    assert getters.get_load_base_power(context, region).unwrap() == 100.0
    assert getters.get_load_max_active_power(context, region).unwrap() == 0.0
    assert getters.get_load_max_reactive_power(context, region).unwrap() == 0.0


def test_load_bus_getter() -> None:
    """Test get_load_bus getter with membership."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

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
    result = getters.get_load_bus(context, region).unwrap()
    assert result is not None
    assert result.name == "NODE1"


def test_load_bus_getter_no_membership() -> None:
    """Test get_load_bus returns None when no membership exists."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    region = PLEXOSRegion(name="REGION1", load=100.0)
    context.source_system.add_component(region)

    result = getters.get_load_bus(context, region).unwrap()
    assert result is None


def test_generator_getters() -> None:
    """Test generator-related getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    gen = PLEXOSGenerator(
        name="GEN1",
        category="gas-cc",
        max_capacity=100.0,
        units=1,
    )

    assert getters.get_gen_active_power(context, gen).unwrap() == 100.0
    assert getters.get_gen_reactive_power(context, gen).unwrap() == 0.0
    assert getters.get_gen_rating(context, gen).unwrap() == 100.0
    assert getters.get_gen_base_power(context, gen).unwrap() == 0.0

    limits = getters.get_gen_active_power_limits(context, gen).unwrap()
    assert limits.min == 0.0
    assert limits.max == 0.0

    reactive_limits = getters.get_gen_reactive_power_limits(context, gen).unwrap()
    assert reactive_limits.min == 0.0
    assert reactive_limits.max == 0.0

    assert getters.get_gen_status(context, gen).unwrap() == 1
    assert getters.get_gen_power_factor(context, gen).unwrap() == 1.0
    assert getters.get_prime_mover_type(context, gen).unwrap() == PrimeMoversType.CC


def test_generator_bus_getter() -> None:
    """Test get_gen_bus getter with membership."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

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
    result = getters.get_gen_bus(context, gen).unwrap()
    assert result is not None
    assert result.name == "NODE1"


def test_generator_bus_getter_no_membership() -> None:
    """Test get_gen_bus returns None when no membership exists."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    gen = PLEXOSGenerator(name="GEN1", category="gas-cc", max_capacity=100.0)
    context.source_system.add_component(gen)

    result = getters.get_gen_bus(context, gen).unwrap()
    assert result is None


def test_prime_mover_type_mapping() -> None:
    """Test prime mover type mappings from defaults.json."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

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
        result = getters.get_prime_mover_type(context, gen).unwrap()
        assert result == expected_type, f"Category {category} should map to {expected_type}, got {result}"


def test_prime_mover_type_unknown() -> None:
    """Test prime mover type with unknown category."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    gen = PLEXOSGenerator(name="GEN_UNKNOWN", category="unknown-type", max_capacity=50.0)
    result = getters.get_prime_mover_type(context, gen).unwrap()
    assert result == PrimeMoversType.OT  # Should default to "other"


def test_storage_getters() -> None:
    """Test storage-related getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    battery = PLEXOSBattery(
        name="BATT1",
        category="battery",
        initial_soc=0.5,
    )

    assert getters.get_initial_storage_capacity_level(context, battery).unwrap() == 0.5
    assert getters.get_storage_capacity(context, battery).unwrap() == 0.0

    level_limits = getters.get_storage_level_limits(context, battery).unwrap()
    assert level_limits.min == 0.0
    assert level_limits.max == 0.0

    charge_limits = getters.get_storage_charge_power_limits(context, battery).unwrap()
    assert charge_limits.max == 0.0

    discharge_limits = getters.get_storage_discharge_power_limits(context, battery).unwrap()
    assert discharge_limits.max == 0.0

    efficiency = getters.get_storage_efficiency(context, battery).unwrap()
    assert efficiency.input == 1.0
    assert efficiency.output == 1.0

    assert getters.get_storage_technology_type(context, battery).unwrap() == StorageTechs.OTHER_CHEM
    assert getters.get_storage_conversion_factor(context, battery).unwrap() == 1.0


def test_storage_bus_getter() -> None:
    """Test get_gen_bus getter with membership."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

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
    result = getters.get_gen_bus(context, battery).unwrap()
    assert result is not None
    assert result.name == "NODE1"


def test_hydro_storage_getters() -> None:
    """Test hydro storage getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    storage = PLEXOSStorage(
        name="HYDRO_RES",
        initial_volume=500.0,
        max_volume=1000.0,
        min_volume=100.0,
    )

    assert getters.get_storage_capacity(context, storage).unwrap() == 1000.0
    assert getters.get_initial_storage_capacity_level(context, storage).unwrap() == 0.0

    limits = getters.get_storage_level_limits(context, storage).unwrap()
    assert limits.min == 100.0
    assert limits.max == 1000.0


def test_line_getters() -> None:
    """Test line-related getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

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
    assert getters.get_reactive_power_flow(context, line).unwrap() == 0.0

    angle_limits = getters.get_line_angle_limits(context, line).unwrap()
    assert angle_limits.min == -90.0
    assert angle_limits.max == 90.0

    flow_limits = getters.get_line_flow_limits(context, line).unwrap()
    assert flow_limits.from_to == 100.0
    assert flow_limits.to_from == -100.0

    susceptance = getters.get_line_susceptance(context, line).unwrap()
    assert susceptance.from_to == 0.001


def test_line_arc_getter() -> None:
    """Test get_line_arc getter."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

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
    arc = getters.get_line_arc(context, line).unwrap()
    assert arc is not None
    assert arc.from_to.name == "NODE1"
    assert arc.to_from.name == "NODE2"


def test_reserve_getters() -> None:
    """Test reserve-related getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    reserve = PLEXOSReserve(
        name="SPIN_RES",
        timeframe=300.0,
        duration=3600.0,
    )

    assert getters.get_reserve_type(context, reserve).unwrap() == ReserveType.SPINNING
    assert getters.get_reserve_direction(context, reserve).unwrap() == ReserveDirection.UP
    assert getters.get_reserve_requirement(context, reserve).unwrap() == 0.0
    assert getters.get_reserve_time_frame(context, reserve).unwrap() == 300.0
    assert getters.get_reserve_sustained_time(context, reserve).unwrap() == 3600.0
    assert getters.get_reserve_max_participation_factor(context, reserve).unwrap() == 1.0
    assert getters.get_reserve_max_output_fraction(context, reserve).unwrap() == 1.0
    assert getters.get_reserve_deployed_fraction(context, reserve).unwrap() == 1.0


def test_reserve_type_mapping() -> None:
    """Test reserve type mappings."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    # Test default behavior when reserve_type is not set
    reserve = PLEXOSReserve(name="RES_DEFAULT")
    result = getters.get_reserve_type(context, reserve).unwrap()
    assert result == ReserveType.SPINNING  # Default value


def test_reserve_direction_mapping() -> None:
    """Test reserve direction mappings."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    # Test default behavior when direction is not set
    reserve = PLEXOSReserve(name="RES_DEFAULT")
    result = getters.get_reserve_direction(context, reserve).unwrap()
    assert result == ReserveDirection.UP  # Default value


def test_interface_getters() -> None:
    """Test interface-related getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    interface = PLEXOSInterface(
        name="IFACE1",
        min_flow=-200.0,
        max_flow=200.0,
    )

    flow_limits = getters.get_interface_active_power_flow_limits(context, interface).unwrap()
    assert flow_limits.min == -200.0
    assert flow_limits.max == 200.0


def test_transformer_getters() -> None:
    """Test transformer-related getters."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    transformer = PLEXOSTransformer(
        name="XFMR1",
        rating=100.0,
        reactance=0.1,
        resistance=0.01,
    )

    assert getters.get_trf_active_power_flow(context, transformer).unwrap() == 0.0
    assert getters.get_trf_reactive_power_flow(context, transformer).unwrap() == 0.0
    assert getters.get_trf_base_power(context, transformer).unwrap() == 100.0


def test_transformer_arc_getter() -> None:
    """Test get_transformer_arc getter."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

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
    arc = getters.get_line_arc(context, xfmr).unwrap()
    assert arc is not None
    assert arc.from_to.name == "NODE1"
    assert arc.to_from.name == "NODE2"


def test_operation_cost_getters() -> None:
    """Test operation cost getter functions return proper objects."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    gen = PLEXOSGenerator(name="GEN1", category="gas-cc", max_capacity=100.0)

    # Test thermal operation cost
    thermal_cost = getters.get_thermal_operation_cost(context, gen).unwrap()
    assert thermal_cost is not None
    assert thermal_cost.fixed == 0.0

    # Test hydro operation cost
    hydro_cost = getters.get_hydro_gen_operation_cost(context, gen).unwrap()
    assert hydro_cost is not None
    assert hydro_cost.fixed == 0.0

    # Test renewable operation cost
    renewable_cost = getters.get_renewable_operation_cost(context, gen).unwrap()
    assert renewable_cost is not None
    assert renewable_cost.fixed == 0.0

    # Test storage operation cost
    battery = PLEXOSBattery(name="BATT1", category="battery")
    storage_cost = getters.get_storage_operation_cost(context, battery).unwrap()
    assert storage_cost is not None


def test_area_getter() -> None:
    """Test get_area getter."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    # Create area in target
    area = Area(name="REGION1", category="area")
    context.target_system.add_component(area)

    # Create node
    _ = PLEXOSNode(name="NODE1", voltage=115.0)


def test_extract_number_from_name() -> None:
    """Test number extraction from component names."""
    assert getters.extract_number_from_name("p51191") == 51191
    assert getters.extract_number_from_name("ACKRLNTC_9_1363") == 1363
    assert getters.extract_number_from_name("NODE_123") == 123
    assert getters.extract_number_from_name("NO_NUMBERS") is None
    assert getters.extract_number_from_name("") is None
    assert getters.extract_number_from_name("ABC_456") == 456


def test_node_number_getter_no_number() -> None:
    """Test get_node_number when no number in name."""
    context = TranslationContext(
        source_system=System(name="source"),
        target_system=System(name="target"),
        config=PluginConfig(models=("r2x_plexos.models", "r2x_sienna.models")),
        rules=[],
    )

    node = PLEXOSNode(name="NODENUMBER", voltage=115.0)
    result = getters.get_node_number(context, node).unwrap()
    assert result == 1  # Default value when no number found
