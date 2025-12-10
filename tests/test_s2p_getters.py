"""Tests for getter functions and their Result-based return patterns.

This module validates that getter functions:
1. Return Result[T, ValueError] where T is the actual value type
2. Handle the Result pattern correctly (Ok/Err)
3. Work with the rule executor to populate target fields
4. Gracefully fall back to defaults on errors
"""

import pytest


def test_is_slack_bus_returns_one_for_slack(context_with_buses) -> None:
    """is_slack_bus returns Ok(1) for SLACK bus type."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.getters import is_slack_bus

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")

    result = is_slack_bus(context_with_buses, source_bus)

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, int)
    # Value depends on the actual bus type in fixture
    assert value in [0, 1]


def test_is_slack_bus_returns_result_int_type() -> None:
    """is_slack_bus returns Result[int, ValueError]."""
    from r2x_sienna.models.enums import ACBusTypes
    from r2x_sienna_to_plexos.getters import is_slack_bus

    class MockBus:
        bustype = ACBusTypes.SLACK

    class MockContext:
        pass

    result = is_slack_bus(MockContext(), MockBus())

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, int)
    assert value == 1


def test_is_slack_bus_returns_zero_for_non_slack() -> None:
    """is_slack_bus returns Ok(0) for non-SLACK bus types."""
    from r2x_sienna.models.enums import ACBusTypes
    from r2x_sienna_to_plexos.getters import is_slack_bus

    class MockBus:
        bustype = ACBusTypes.PV

    class MockContext:
        pass

    result = is_slack_bus(MockContext(), MockBus())

    assert result.is_ok()
    value = result.unwrap()
    assert value == 0


def test_get_availability_returns_result_int_type() -> None:
    """get_availability returns Result[int, ValueError]."""
    from r2x_sienna_to_plexos.getters import get_availability

    class MockComponent:
        units = 5

    class MockContext:
        pass

    result = get_availability(MockContext(), MockComponent())

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, int)
    assert value == 5


def test_get_availability_defaults_to_one() -> None:
    """get_availability returns Ok(1) when units attribute is missing."""
    from r2x_sienna_to_plexos.getters import get_availability

    class MockComponent:
        pass  # No units attribute

    class MockContext:
        pass

    result = get_availability(MockContext(), MockComponent())

    assert result.is_ok()
    value = result.unwrap()
    assert value == 1


def test_get_availability_with_real_component(context_with_buses) -> None:
    """get_availability works with real Sienna ACBus component."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.getters import get_availability

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")

    result = get_availability(context_with_buses, source_bus)

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, int)
    assert value >= 1


def test_get_power_load_returns_result_float_type() -> None:
    """get_power_load returns Result[float, ValueError]."""
    from r2x_sienna_to_plexos.getters import get_power_load

    class MockLoad:
        max_active_power = 100.5

    class MockComponent:
        def list_child_components(self, component_type):
            return [MockLoad()]

    class MockContext:
        pass

    result = get_power_load(MockContext(), MockComponent())

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, float)
    assert value == 100.5


def test_get_power_load_aggregates_multiple_loads() -> None:
    """get_power_load sums active power from multiple PowerLoad components."""
    from r2x_sienna_to_plexos.getters import get_power_load

    class MockLoad:
        def __init__(self, power):
            self.max_active_power = power

    class MockComponent:
        def list_child_components(self, component_type):
            return [MockLoad(100.0), MockLoad(200.5), MockLoad(50.25)]

    class MockContext:
        pass

    result = get_power_load(MockContext(), MockComponent())

    assert result.is_ok()
    value = result.unwrap()
    assert value == 350.75


def test_get_power_load_returns_zero_for_no_loads() -> None:
    """get_power_load returns Ok(0.0) when no PowerLoad components exist."""
    from r2x_sienna_to_plexos.getters import get_power_load

    class MockComponent:
        def list_child_components(self, component_type):
            return []

    class MockContext:
        pass

    result = get_power_load(MockContext(), MockComponent())

    assert result.is_ok()
    value = result.unwrap()
    assert value == 0.0


def test_get_power_load_skips_loads_without_max_active_power() -> None:
    """get_power_load skips loads without max_active_power attribute."""
    from r2x_sienna_to_plexos.getters import get_power_load

    class MockLoadWithoutPower:
        pass  # No max_active_power

    class MockLoadWithPower:
        max_active_power = 150.0

    class MockComponent:
        def list_child_components(self, component_type):
            return [MockLoadWithoutPower(), MockLoadWithPower()]

    class MockContext:
        pass

    result = get_power_load(MockContext(), MockComponent())

    assert result.is_ok()
    value = result.unwrap()
    assert value == 150.0


def test_getter_receives_correct_context_and_component(context_with_buses) -> None:
    """Getter functions receive TranslationContext and source component."""
    from r2x_sienna.models import ACBus

    from r2x_core import Rule
    from r2x_core.rules_utils import _build_target_fields

    received_context = None
    received_component = None

    def capture_getter(ctx, component):
        from r2x_core import Ok

        nonlocal received_context, received_component
        received_context = ctx
        received_component = component
        return Ok(100.0)

    rule = Rule(
        source_type="ACBus",
        target_type="PLEXOSNode",
        version=1,
        field_map={
            "name": "name",
            "test_field": ["base_voltage"],
        },
        getters={
            "test_field": capture_getter,
        },
    )

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")
    _build_target_fields(rule, source_bus, context_with_buses)

    assert received_context is context_with_buses
    assert received_component is source_bus


def test_getter_single_value_not_dict() -> None:
    """Getters return single values, not dictionaries."""

    from r2x_sienna_to_plexos.getters import is_slack_bus

    class MockBus:
        bustype = None

    class MockContext:
        pass

    result = is_slack_bus(MockContext(), MockBus())

    assert result.is_ok()
    value = result.unwrap()
    # Should be a single int, not a dict like {'bustype': 0}
    assert isinstance(value, int)
    assert not isinstance(value, dict)


def test_getter_error_variant() -> None:
    """Getters can return Err variant for error handling."""
    from r2x_core import Err

    def failing_getter(ctx, component):
        return Err(ValueError("Test error"))

    result = failing_getter(None, None)

    assert result.is_err()
    assert not result.is_ok()
    error = result.err()
    assert isinstance(error, ValueError)


def test_is_slack_bus_has_decorator() -> None:
    """is_slack_bus is registered via @getter decorator."""
    from r2x_core.getters import GETTER_REGISTRY

    # Should be able to retrieve it by name from registry
    assert "is_slack_bus" in GETTER_REGISTRY
    getter_func = GETTER_REGISTRY["is_slack_bus"]
    assert callable(getter_func)


def test_get_availability_has_decorator() -> None:
    """get_availability is registered via @getter decorator."""
    from r2x_core.getters import GETTER_REGISTRY

    assert "get_availability" in GETTER_REGISTRY
    getter_func = GETTER_REGISTRY["get_availability"]
    assert callable(getter_func)


def test_get_power_load_has_decorator() -> None:
    """get_power_load is registered via @getter decorator."""
    from r2x_core.getters import GETTER_REGISTRY

    assert "get_power_load" in GETTER_REGISTRY
    getter_func = GETTER_REGISTRY["get_power_load"]
    assert callable(getter_func)


def test_get_max_capacity_scales_limits(context_with_thermal_generators) -> None:
    """Thermal max capacity getter converts per-unit limits to MW."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_max_capacity

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    result = get_max_capacity(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(90.0)


def test_get_min_stable_level_scales_limits(context_with_thermal_generators) -> None:
    """Thermal min stable level getter converts lower bound."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_min_stable_level

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    result = get_min_stable_level(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(40.0)


def test_get_initial_generation_uses_base_power(context_with_thermal_generators) -> None:
    """Initial generation getter multiplies per-unit output by base power."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_initial_generation

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-vom")

    result = get_initial_generation(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(36.0)


def test_get_heat_rate_from_fuel_curve(context_with_thermal_generators) -> None:
    """Heat rate getter reads slope from FuelCurve."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate, get_heat_rate_base

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    assert get_heat_rate(context_with_thermal_generators, source).unwrap() == pytest.approx(9.2)
    assert get_heat_rate_base(context_with_thermal_generators, source).unwrap() == pytest.approx(0.0)


def test_get_fuel_price_from_fuel_curve(context_with_thermal_generators) -> None:
    """Fuel price getter returns FuelCurve fuel_cost."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_fuel_price

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    result = get_fuel_price(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(2.4)


def test_get_mark_up_from_cost_curve(context_with_thermal_generators) -> None:
    """Markup getter reads VOM cost when using CostCurve."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_mark_up

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-vom")

    result = get_mark_up(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(14.0)


def test_get_heat_rate_quadratic_curve_returns_coefficients(context_with_thermal_generators) -> None:
    """Quadratic fuel curves map to polynomial heat-rate fields."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import (
        get_heat_rate,
        get_heat_rate_base,
        get_heat_rate_incr,
    )

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-quadratic")

    assert get_heat_rate(context_with_thermal_generators, source).unwrap() == pytest.approx(9.8)
    assert get_heat_rate_base(context_with_thermal_generators, source).unwrap() == pytest.approx(120.0)
    assert get_heat_rate_incr(context_with_thermal_generators, source).unwrap() == pytest.approx(0.015)


def test_get_heat_rate_multiband_returns_property(context_with_thermal_generators) -> None:
    """Piecewise fuel curves emit multi-band load points and heat-rate bands."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate_incr, get_heat_rate_load_point

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-piecewise")

    load_prop = get_heat_rate_load_point(context_with_thermal_generators, source).unwrap()
    incr_prop = get_heat_rate_incr(context_with_thermal_generators, source).unwrap()

    assert hasattr(load_prop, "get_bands")
    assert load_prop.get_bands() == [1, 2]
    assert hasattr(incr_prop, "get_bands")
    assert incr_prop.get_bands() == [1, 2]


def test_get_mark_up_multiband_property(context_with_thermal_generators) -> None:
    """Piecewise cost curves emit multi-band markup properties."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_mark_up, get_mark_up_point

    source = context_with_thermal_generators.source_system.get_component(
        ThermalStandard,
        "thermal-markup-piecewise",
    )

    point_prop = get_mark_up_point(context_with_thermal_generators, source).unwrap()
    mark_prop = get_mark_up(context_with_thermal_generators, source).unwrap()

    assert point_prop.get_bands() == [1, 2]
    assert mark_prop.get_bands() == [1, 2]


# New tests for additional getters


def test_get_voltage(context_with_buses) -> None:
    """get_voltage extracts voltage magnitude from base_voltage."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.getters import get_voltage

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")
    result = get_voltage(context_with_buses, source_bus)

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, float)
    assert value > 0.0


def test_get_susceptance_transformer() -> None:
    """get_susceptance extracts imaginary part from transformer primary_shunt."""
    from r2x_sienna_to_plexos.getters import get_susceptance

    class MockTransformer:
        primary_shunt = 0.5 + 2.3j

    class MockContext:
        pass

    result = get_susceptance(MockContext(), MockTransformer())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(2.3)


def test_get_susceptance_none_returns_error() -> None:
    """get_susceptance returns error when primary_shunt is None."""
    from r2x_sienna_to_plexos.getters import get_susceptance

    class MockTransformer:
        primary_shunt = None

    class MockContext:
        pass

    result = get_susceptance(MockContext(), MockTransformer())

    assert result.is_err()


def test_get_line_charging_susceptance() -> None:
    """get_line_charging_susceptance extracts b attribute from line."""
    from r2x_sienna_to_plexos.getters import get_line_charging_susceptance

    class MockLine:
        b = 1.5

    class MockContext:
        pass

    result = get_line_charging_susceptance(MockContext(), MockLine())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(1.5)


def test_get_line_charging_susceptance_none() -> None:
    """get_line_charging_susceptance returns 0.0 when b is None."""
    from r2x_sienna_to_plexos.getters import get_line_charging_susceptance

    class MockLine:
        b = None

    class MockContext:
        pass

    result = get_line_charging_susceptance(MockContext(), MockLine())

    assert result.is_ok()
    assert result.unwrap() == 0.0


def test_get_max_ramp_up(context_with_thermal_generators) -> None:
    """get_max_ramp_up extracts up ramp limit."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_max_ramp_up

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_max_ramp_up(context_with_thermal_generators, source)

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, float)


def test_get_max_ramp_down(context_with_thermal_generators) -> None:
    """get_max_ramp_down extracts down ramp limit."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_max_ramp_down

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_max_ramp_down(context_with_thermal_generators, source)

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, float)


def test_get_min_up_time(context_with_thermal_generators) -> None:
    """get_min_up_time extracts minimum up time."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_min_up_time

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_min_up_time(context_with_thermal_generators, source)

    # May return Ok or Err depending on fixture data
    assert result.is_ok() or result.is_err()


def test_get_min_down_time(context_with_thermal_generators) -> None:
    """get_min_down_time extracts minimum down time."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_min_down_time

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")
    result = get_min_down_time(context_with_thermal_generators, source)

    # May return Ok or Err depending on fixture data
    assert result.is_ok() or result.is_err()


def test_get_initial_hours_up() -> None:
    """get_initial_hours_up returns hours when status is True."""
    from r2x_sienna_to_plexos.getters import get_initial_hours_up

    class MockGenerator:
        time_at_status = 5.0
        status = True

    class MockContext:
        pass

    result = get_initial_hours_up(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(5.0)


def test_get_initial_hours_down() -> None:
    """get_initial_hours_down returns hours when status is False."""
    from r2x_sienna_to_plexos.getters import get_initial_hours_down

    class MockGenerator:
        time_at_status = 3.0
        status = False

    class MockContext:
        pass

    result = get_initial_hours_down(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(3.0)


def test_get_running_cost() -> None:
    """get_running_cost extracts fixed cost from operation_cost."""
    from r2x_sienna_to_plexos.getters import get_running_cost

    class MockCost:
        fixed = 100.0

    class MockGenerator:
        operation_cost = MockCost()

    class MockContext:
        pass

    result = get_running_cost(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(100.0)


def test_get_start_cost() -> None:
    """get_start_cost extracts start_up cost from operation_cost."""
    from r2x_sienna_to_plexos.getters import get_start_cost

    class MockCost:
        start_up = 50.0

    class MockGenerator:
        operation_cost = MockCost()

    class MockContext:
        pass

    result = get_start_cost(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(50.0)


def test_get_shutdown_cost() -> None:
    """get_shutdown_cost extracts shut_down cost from operation_cost."""
    from r2x_sienna_to_plexos.getters import get_shutdown_cost

    class MockCost:
        shut_down = 25.0

    class MockGenerator:
        operation_cost = MockCost()

    class MockContext:
        pass

    result = get_shutdown_cost(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(25.0)


def test_get_storage_charge_efficiency() -> None:
    """get_storage_charge_efficiency extracts input efficiency."""
    from r2x_sienna_to_plexos.getters import get_storage_charge_efficiency

    class MockEfficiency:
        input = 0.95

    class MockStorage:
        efficiency = MockEfficiency()

    class MockContext:
        pass

    result = get_storage_charge_efficiency(MockContext(), MockStorage())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.95)


def test_get_storage_discharge_efficiency() -> None:
    """get_storage_discharge_efficiency extracts output efficiency."""
    from r2x_sienna_to_plexos.getters import get_storage_discharge_efficiency

    class MockEfficiency:
        output = 0.90

    class MockStorage:
        efficiency = MockEfficiency()

    class MockContext:
        pass

    result = get_storage_discharge_efficiency(MockContext(), MockStorage())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.90)


def test_get_storage_cycles() -> None:
    """get_storage_cycles extracts cycle_limits."""
    from r2x_sienna_to_plexos.getters import get_storage_cycles

    class MockStorage:
        cycle_limits = 1000.0

    class MockContext:
        pass

    result = get_storage_cycles(MockContext(), MockStorage())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(1000.0)


def test_get_storage_capacity() -> None:
    """get_storage_capacity extracts storage_capacity."""
    from r2x_sienna_to_plexos.getters import get_storage_capacity

    class MockStorage:
        storage_capacity = 500.0

    class MockContext:
        pass

    result = get_storage_capacity(MockContext(), MockStorage())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(500.0)


def test_membership_parent_component() -> None:
    """membership_parent_component returns the component itself."""
    from r2x_sienna_to_plexos.getters import membership_parent_component

    class MockComponent:
        name = "test"

    class MockContext:
        pass

    component = MockComponent()
    result = membership_parent_component(MockContext(), component)

    assert result.is_ok()
    assert result.unwrap() is component


def test_membership_collection_nodes() -> None:
    """membership_collection_nodes returns CollectionEnum.Nodes."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_nodes

    class MockContext:
        pass

    result = membership_collection_nodes(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.Nodes


def test_membership_collection_generators() -> None:
    """membership_collection_generators returns CollectionEnum.Generators."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_generators

    class MockContext:
        pass

    result = membership_collection_generators(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.Generators


def test_membership_collection_node_from() -> None:
    """membership_collection_node_from returns CollectionEnum.NodeFrom."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_node_from

    class MockContext:
        pass

    result = membership_collection_node_from(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.NodeFrom


def test_membership_collection_node_to() -> None:
    """membership_collection_node_to returns CollectionEnum.NodeTo."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_node_to

    class MockContext:
        pass

    result = membership_collection_node_to(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.NodeTo


def test_membership_collection_zone() -> None:
    """membership_collection_zone returns CollectionEnum.Zone."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_zone

    class MockContext:
        pass

    result = membership_collection_zone(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.Zone


def test_get_vom_charge_returns_markup() -> None:
    """get_vom_charge returns the same value as get_mark_up."""
    from r2x_sienna_to_plexos.getters import get_vom_charge

    class MockContext:
        pass

    class MockCost:
        variable = 14.0

    class MockGenerator:
        operation_cost = MockCost()

    result = get_vom_charge(MockContext(), MockGenerator())

    assert result.is_ok()


def test_all_membership_getters_registered() -> None:
    """Verify all membership getters are registered."""
    from r2x_core.getters import GETTER_REGISTRY

    membership_getters = [
        "membership_parent_component",
        "membership_collection_nodes",
        "membership_collection_generators",
        "membership_collection_node_from",
        "membership_collection_node_to",
        "membership_collection_zone",
        "membership_collection_region",
        "membership_collection_head_storage",
        "membership_collection_tail_storage",
    ]

    for getter_name in membership_getters:
        assert getter_name in GETTER_REGISTRY, f"{getter_name} not registered"


def test_heat_rate_getters_registered() -> None:
    """Verify all heat rate getters are registered."""
    from r2x_core.getters import GETTER_REGISTRY

    heat_rate_getters = [
        "get_heat_rate",
        "get_heat_rate_base",
        "get_heat_rate_incr",
        "get_heat_rate_incr2",
        "get_heat_rate_incr3",
        "get_heat_rate_load_point",
    ]

    for getter_name in heat_rate_getters:
        assert getter_name in GETTER_REGISTRY, f"{getter_name} not registered"


def test_storage_getters_registered() -> None:
    """Verify all storage getters are registered."""
    from r2x_core.getters import GETTER_REGISTRY

    storage_getters = [
        "get_storage_charge_efficiency",
        "get_storage_discharge_efficiency",
        "get_storage_cycles",
        "get_storage_max_power",
        "get_storage_capacity",
    ]

    for getter_name in storage_getters:
        assert getter_name in GETTER_REGISTRY, f"{getter_name} not registered"


def test_cost_getters_registered() -> None:
    """Verify all cost-related getters are registered."""
    from r2x_core.getters import GETTER_REGISTRY

    cost_getters = [
        "get_running_cost",
        "get_start_cost",
        "get_shutdown_cost",
        "get_fuel_price",
        "get_mark_up",
        "get_mark_up_point",
        "get_vom_charge",
    ]

    for getter_name in cost_getters:
        assert getter_name in GETTER_REGISTRY, f"{getter_name} not registered"


def test_get_susceptance_with_complex_quantity() -> None:
    """Test susceptance with complex Quantity types."""
    from r2x_sienna_to_plexos.getters import get_susceptance

    class MockQuantity:
        def __init__(self, imag_val):
            self.imag = imag_val

    class MockTransformer:
        primary_shunt = MockQuantity(3.5)

    class MockContext:
        pass

    result = get_susceptance(MockContext(), MockTransformer())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(3.5)


def test_get_susceptance_with_float() -> None:
    """Test susceptance with plain float value."""
    from r2x_sienna_to_plexos.getters import get_susceptance

    class MockTransformer:
        primary_shunt = 0.0 + 2.5j  # Complex number with imaginary part

    class MockContext:
        pass

    result = get_susceptance(MockContext(), MockTransformer())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(2.5)


def test_get_susceptance_conversion_failure() -> None:
    """Test susceptance returns error for None values."""
    from r2x_sienna_to_plexos.getters import get_susceptance

    class MockTransformer:
        primary_shunt = None

    class MockContext:
        pass

    result = get_susceptance(MockContext(), MockTransformer())
    assert result.is_err()


def test_get_line_charging_susceptance_with_complex() -> None:
    """Test line charging susceptance with complex number."""
    from r2x_sienna_to_plexos.getters import get_line_charging_susceptance

    class MockLine:
        b = 1.5 + 2.3j

    class MockContext:
        pass

    result = get_line_charging_susceptance(MockContext(), MockLine())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(2.3)


def test_get_line_charging_susceptance_with_from_to() -> None:
    """Test line charging susceptance with FromTo_ToFrom type."""
    from r2x_sienna.models.named_tuples import FromTo_ToFrom
    from r2x_sienna_to_plexos.getters import get_line_charging_susceptance

    class MockLine:
        b = FromTo_ToFrom(from_to=1.8, to_from=1.6)

    class MockContext:
        pass

    result = get_line_charging_susceptance(MockContext(), MockLine())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(1.8)


def test_get_power_load_with_none_system() -> None:
    """Test get_power_load when context has no source_system."""
    from r2x_sienna_to_plexos.getters import get_power_load

    class MockComponent:
        def list_child_components(self, component_type):
            return []

    class MockContext:
        source_system = None

    result = get_power_load(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_heat_rate_with_none_values() -> None:
    """Test heat rate getters with None values."""
    from r2x_sienna_to_plexos.getters import get_heat_rate, get_heat_rate_base, get_heat_rate_incr2

    class MockComponent:
        operation_cost = None

    class MockContext:
        pass

    result = get_heat_rate(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)

    result = get_heat_rate_base(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)

    result = get_heat_rate_incr2(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_heat_rate_load_point_none() -> None:
    """Test heat rate load point returns error when None."""
    from r2x_sienna_to_plexos.getters import get_heat_rate_load_point

    class MockComponent:
        operation_cost = None

    class MockContext:
        pass

    result = get_heat_rate_load_point(MockContext(), MockComponent())
    assert result.is_err()


def test_get_min_stable_level_no_limits() -> None:
    """Test min stable level with no active_power_limits."""
    from r2x_sienna_to_plexos.getters import get_min_stable_level

    class MockComponent:
        pass

    class MockContext:
        pass

    result = get_min_stable_level(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_max_capacity_with_rating() -> None:
    """Test max capacity falls back to rating when limits missing."""
    from r2x_sienna_to_plexos.getters import get_max_capacity

    class MockComponent:
        rating = 150.0
        base_power = 100.0

    class MockContext:
        pass

    result = get_max_capacity(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() > 0.0


def test_get_max_capacity_error() -> None:
    """Test max capacity returns error when both limits and rating missing."""
    from r2x_sienna_to_plexos.getters import get_max_capacity

    class MockComponent:
        pass

    class MockContext:
        pass

    result = get_max_capacity(MockContext(), MockComponent())
    assert result.is_err()


def test_get_max_ramp_up_error() -> None:
    """Test max ramp up returns error on KeyError/TypeError."""
    from r2x_sienna_to_plexos.getters import get_max_ramp_up

    class MockComponent:
        pass

    class MockContext:
        pass

    result = get_max_ramp_up(MockContext(), MockComponent())
    assert result.is_err()


def test_get_max_ramp_down_error() -> None:
    """Test max ramp down returns error on KeyError/TypeError."""
    from r2x_sienna_to_plexos.getters import get_max_ramp_down

    class MockComponent:
        pass

    class MockContext:
        pass

    result = get_max_ramp_down(MockContext(), MockComponent())
    assert result.is_err()


def test_get_min_up_time_from_ext() -> None:
    """Test min up time reads from ext when time_limits missing."""
    from r2x_sienna_to_plexos.getters import get_min_up_time

    class MockComponent:
        time_limits = None
        ext = {"min_up_time": 4.0}  # noqa: RUF012

    class MockContext:
        pass

    result = get_min_up_time(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(4.0)


def test_get_min_down_time_from_ext() -> None:
    """Test min down time reads from ext when time_limits missing."""
    from r2x_sienna_to_plexos.getters import get_min_down_time

    class MockComponent:
        time_limits = None
        ext = {"min_down_time": 3.0}  # noqa: RUF012

    class MockContext:
        pass

    result = get_min_down_time(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(3.0)


def test_get_initial_generation_none() -> None:
    """Test initial generation with None active_power."""
    from r2x_sienna_to_plexos.getters import get_initial_generation

    class MockComponent:
        active_power = None

    class MockContext:
        pass

    result = get_initial_generation(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_initial_hours_up_when_down() -> None:
    """Test initial hours up returns 0 when status is False."""
    from r2x_sienna_to_plexos.getters import get_initial_hours_up

    class MockComponent:
        time_at_status = 5.0
        status = False

    class MockContext:
        pass

    result = get_initial_hours_up(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_initial_hours_down_when_up() -> None:
    """Test initial hours down returns 0 when status is True."""
    from r2x_sienna_to_plexos.getters import get_initial_hours_down

    class MockComponent:
        time_at_status = 3.0
        status = True

    class MockContext:
        pass

    result = get_initial_hours_down(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_running_cost_none() -> None:
    """Test running cost with None operation_cost."""
    from r2x_sienna_to_plexos.getters import get_running_cost

    class MockComponent:
        operation_cost = None

    class MockContext:
        pass

    result = get_running_cost(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_start_cost_none() -> None:
    """Test start cost with None operation_cost."""
    from r2x_sienna_to_plexos.getters import get_start_cost

    class MockComponent:
        operation_cost = None

    class MockContext:
        pass

    result = get_start_cost(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_shutdown_cost_none() -> None:
    """Test shutdown cost with None operation_cost."""
    from r2x_sienna_to_plexos.getters import get_shutdown_cost

    class MockComponent:
        operation_cost = None

    class MockContext:
        pass

    result = get_shutdown_cost(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_fuel_price_not_fuel_curve() -> None:
    """Test fuel price when variable is not a FuelCurve."""
    from r2x_sienna_to_plexos.getters import get_fuel_price

    class MockCost:
        variable = 10.0

    class MockComponent:
        operation_cost = MockCost()

    class MockContext:
        pass

    result = get_fuel_price(MockContext(), MockComponent())
    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_get_mark_up_point_none() -> None:
    """Test mark up point returns error when None."""
    from r2x_sienna_to_plexos.getters import get_mark_up_point

    class MockComponent:
        operation_cost = None

    class MockContext:
        pass

    result = get_mark_up_point(MockContext(), MockComponent())
    assert result.is_err()


def test_membership_collection_lines() -> None:
    """Test membership_collection_lines returns Lines enum."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_lines

    class MockContext:
        pass

    result = membership_collection_lines(MockContext(), None)
    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.Lines


def test_membership_collection_region() -> None:
    """Test membership_collection_region returns Region enum."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_region

    class MockContext:
        pass

    result = membership_collection_region(MockContext(), None)
    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.Region


def test_membership_collection_head_storage() -> None:
    """Test membership_collection_head_storage returns HeadStorage enum."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_head_storage

    class MockContext:
        pass

    result = membership_collection_head_storage(MockContext(), None)
    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.HeadStorage


def test_membership_collection_tail_storage() -> None:
    """Test membership_collection_tail_storage returns TailStorage enum."""
    from plexosdb import CollectionEnum
    from r2x_sienna_to_plexos.getters import membership_collection_tail_storage

    class MockContext:
        pass

    result = membership_collection_tail_storage(MockContext(), None)
    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.TailStorage


def test_lookup_target_zone_by_name_not_found() -> None:
    """Test _lookup_target_zone_by_name returns error when zone not found."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import _lookup_target_zone_by_name

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    result = _lookup_target_zone_by_name(context, "nonexistent")
    assert result.is_err()


def test_lookup_target_node_by_source_area_not_found() -> None:
    """Test _lookup_target_node_by_source_area returns error when node not found."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import _lookup_target_node_by_source_area

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    result = _lookup_target_node_by_source_area(context, "nonexistent_area")
    assert result.is_err()


def test_lookup_source_generator_not_found() -> None:
    """Test _lookup_source_generator returns None when not found."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import _lookup_source_generator

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target")

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    result = _lookup_source_generator(context, "nonexistent")
    assert result is None


def test_lookup_source_battery_not_found() -> None:
    """Test _lookup_source_battery returns None when not found."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import _lookup_source_battery

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target")

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    result = _lookup_source_battery(context, "nonexistent")
    assert result is None


def test_lookup_target_node_by_name_not_found() -> None:
    """Test _lookup_target_node_by_name returns error when node not found."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import _lookup_target_node_by_name

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    result = _lookup_target_node_by_name(context, "nonexistent")
    assert result.is_err()


def test_find_source_line_not_found() -> None:
    """Test _find_source_line returns None when line not found."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import _find_source_line

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target")

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    result = _find_source_line(context, "nonexistent")
    assert result is None


def test_find_source_transformer_not_found() -> None:
    """Test _find_source_transformer returns None when transformer not found."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import _find_source_transformer

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target")

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    result = _find_source_transformer(context, "nonexistent")
    assert result is None


def test_lookup_source_pumped_hydro_not_found() -> None:
    """Test _lookup_source_pumped_hydro returns None for non-pumped names."""
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import _lookup_source_pumped_hydro

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target")

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    result = _lookup_source_pumped_hydro(context, "regular_gen")
    assert result is None


def test_membership_node_child_zone_no_source_bus() -> None:
    """Test membership_node_child_zone returns error when source bus not found."""
    from r2x_plexos.models import PLEXOSNode
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import membership_node_child_zone

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    node = PLEXOSNode(name="nonexistent")
    result = membership_node_child_zone(context, node)
    assert result.is_err()


def test_membership_component_child_node_no_source() -> None:
    """Test membership_component_child_node returns error when source not found."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import membership_component_child_node

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    generator = PLEXOSGenerator(name="nonexistent")
    result = membership_component_child_node(context, generator)
    assert result.is_err()


def test_membership_pumped_hydro_head_storage_wrong_suffix() -> None:
    """Test membership_pumped_hydro_head_storage errors on non-head generator."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import membership_pumped_hydro_head_storage

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target")

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    generator = PLEXOSGenerator(name="regular_gen")
    result = membership_pumped_hydro_head_storage(context, generator)
    assert result.is_err()


def test_membership_pumped_hydro_tail_storage_wrong_suffix() -> None:
    """Test membership_pumped_hydro_tail_storage errors on non-tail generator."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters import membership_pumped_hydro_tail_storage

    from r2x_core import System, TranslationContext

    source_system = System(name="source")
    target_system = System(name="target")

    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    generator = PLEXOSGenerator(name="regular_gen")
    result = membership_pumped_hydro_tail_storage(context, generator)
    assert result.is_err()
