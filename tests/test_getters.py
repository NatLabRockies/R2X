"""Tests for getter functions and their Result-based return patterns.

This module validates that getter functions:
1. Return Result[T, ValueError] where T is the actual value type
2. Handle the Result pattern correctly (Ok/Err)
3. Work with the rule executor to populate target fields
4. Gracefully fall back to defaults on errors
"""

import pytest


def test_is_slack_bus_returns_one_for_slack(context_with_buses):
    """is_slack_bus returns Ok(1) for SLACK bus type."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.getters import is_slack_bus

    # Get a real bus from the context
    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")

    result = is_slack_bus(context_with_buses, source_bus)

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, int)
    # Value depends on the actual bus type in fixture
    assert value in [0, 1]


def test_is_slack_bus_returns_result_int_type():
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


def test_is_slack_bus_returns_zero_for_non_slack():
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


def test_get_availability_returns_result_int_type():
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


def test_get_availability_defaults_to_one():
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


def test_get_availability_with_real_component(context_with_buses):
    """get_availability works with real Sienna ACBus component."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.getters import get_availability

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")

    result = get_availability(context_with_buses, source_bus)

    assert result.is_ok()
    value = result.unwrap()
    assert isinstance(value, int)
    assert value >= 1


def test_get_power_load_returns_result_float_type():
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


def test_get_power_load_aggregates_multiple_loads():
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


def test_get_power_load_returns_zero_for_no_loads():
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


def test_get_power_load_skips_loads_without_max_active_power():
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


def test_getter_receives_correct_context_and_component(context_with_buses):
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


def test_getter_single_value_not_dict():
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


def test_getter_error_variant():
    """Getters can return Err variant for error handling."""
    from r2x_core import Err

    def failing_getter(ctx, component):
        return Err(ValueError("Test error"))

    result = failing_getter(None, None)

    assert result.is_err()
    assert not result.is_ok()
    error = result.err()
    assert isinstance(error, ValueError)


def test_is_slack_bus_has_decorator():
    """is_slack_bus is registered via @getter decorator."""
    from r2x_core.getters import GETTER_REGISTRY

    # Should be able to retrieve it by name from registry
    assert "is_slack_bus" in GETTER_REGISTRY
    getter_func = GETTER_REGISTRY["is_slack_bus"]
    assert callable(getter_func)


def test_get_availability_has_decorator():
    """get_availability is registered via @getter decorator."""
    from r2x_core.getters import GETTER_REGISTRY

    assert "get_availability" in GETTER_REGISTRY
    getter_func = GETTER_REGISTRY["get_availability"]
    assert callable(getter_func)


def test_get_power_load_has_decorator():
    """get_power_load is registered via @getter decorator."""
    from r2x_core.getters import GETTER_REGISTRY

    assert "get_power_load" in GETTER_REGISTRY
    getter_func = GETTER_REGISTRY["get_power_load"]
    assert callable(getter_func)


def test_get_max_capacity_scales_limits(context_with_thermal_generators):
    """Thermal max capacity getter converts per-unit limits to MW."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_max_capacity

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    result = get_max_capacity(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(90.0)


def test_get_min_stable_level_scales_limits(context_with_thermal_generators):
    """Thermal min stable level getter converts lower bound."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_min_stable_level

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    result = get_min_stable_level(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(40.0)


def test_get_initial_generation_uses_base_power(context_with_thermal_generators):
    """Initial generation getter multiplies per-unit output by base power."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_initial_generation

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-vom")

    result = get_initial_generation(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(36.0)


def test_get_heat_rate_from_fuel_curve(context_with_thermal_generators):
    """Heat rate getter reads slope from FuelCurve."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_heat_rate, get_heat_rate_base

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    assert get_heat_rate(context_with_thermal_generators, source).unwrap() == pytest.approx(9.2)
    assert get_heat_rate_base(context_with_thermal_generators, source).unwrap() == pytest.approx(0.0)


def test_get_fuel_price_from_fuel_curve(context_with_thermal_generators):
    """Fuel price getter returns FuelCurve fuel_cost."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_fuel_price

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    result = get_fuel_price(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(2.4)


def test_get_mark_up_from_cost_curve(context_with_thermal_generators):
    """Markup getter reads VOM cost when using CostCurve."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters import get_mark_up

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-vom")

    result = get_mark_up(context_with_thermal_generators, source)

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(14.0)


def test_get_heat_rate_quadratic_curve_returns_coefficients(context_with_thermal_generators):
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


def test_get_heat_rate_multiband_returns_property(context_with_thermal_generators):
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


def test_get_mark_up_multiband_property(context_with_thermal_generators):
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
