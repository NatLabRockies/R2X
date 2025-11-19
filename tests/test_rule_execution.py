"""Tests for rule-based component translation using functional dispatcher."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_sienna_to_plexos.translation import Rule, TranslationContext


def test_convert_rule_single_component(context_with_buses: TranslationContext, rule_simple: Rule):
    """convert_rule applies a rule to all matching source components."""
    from r2x_sienna_to_plexos import apply_single_rule

    result = apply_single_rule(rule_simple, context_with_buses)

    assert result
    assert result.unwrap()[0] == 3  # We have 3 buses


def test_convert_rule_adds_components_to_target_system(
    context_with_buses: TranslationContext, rule_simple: Rule
):
    from r2x_plexos.models import PLEXOSNode
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos import apply_single_rule
    from r2x_sienna_to_plexos.rule_utils import _iter_system_components

    apply_single_rule(rule_simple, context_with_buses)

    target_nodes = list(_iter_system_components(context_with_buses.target_system, PLEXOSNode))
    assert len(target_nodes) == 3

    source_names = set(bus.name for bus in _iter_system_components(context_with_buses.source_system, ACBus))
    target_names = {node.name for node in target_nodes}
    assert source_names == target_names


def test_convert_rule_returns_counts(context_with_buses: TranslationContext, rule_simple: Rule):
    """convert_rule returns (converted_count, skipped_count) tuple."""
    from r2x_sienna_to_plexos import apply_single_rule

    result = apply_single_rule(rule_simple, context_with_buses).unwrap_or_raise()

    assert isinstance(result, tuple)
    assert len(result) == 2
    converted, skipped = result
    assert isinstance(converted, int)
    assert isinstance(skipped, int)


def test_convert_component_raises_on_multifield_without_getter(
    context_with_buses: TranslationContext,
):
    """Rule creation raises error for multi-field mapping without getter."""
    from r2x_sienna_to_plexos.translation import Rule

    # Error is raised during Rule creation via __post_init__, not during conversion
    with pytest.raises(ValueError, match="Multi-field mapping.*requires a getter"):
        Rule(
            source_type="ACBus",
            target_type="PLEXOSNode",
            version=1,
            field_map={
                "name": "name",
                "x": ["field1", "field2"],
            },
            getters={},
        )


def test_build_target_kwargs_extracts_all_fields(context_with_buses: TranslationContext, rule_simple: Rule):
    """build_target_kwargs returns dict with all target fields."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.rule_utils import _build_target_fields

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")

    kwargs = _build_target_fields(rule_simple, source_bus, context_with_buses).unwrap_or_raise()

    assert isinstance(kwargs, dict)
    assert "name" in kwargs
    assert "uuid" in kwargs
    assert kwargs["name"] == source_bus.name
    assert kwargs["uuid"] == source_bus.uuid


def test_build_target_kwargs_applies_getters(context_with_buses: TranslationContext):
    """build_target_kwargs calls getter functions."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos import Rule
    from r2x_sienna_to_plexos.rule_utils import _build_target_fields

    def test_getter(ctx, component):
        from r2x_core import Ok

        return Ok(42.0)

    rule = Rule(
        source_type="ACBus",
        target_type="PLEXOSNode",
        version=1,
        field_map={
            "name": "name",
            "computed": ["base_voltage"],
        },
        getters={
            "computed": test_getter,
        },
    )

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")
    kwargs = _build_target_fields(rule, source_bus, context_with_buses).unwrap_or_raise()

    assert kwargs["computed"] == 42.0


def test_build_target_kwargs_applies_defaults(context_with_buses: TranslationContext):
    """build_target_kwargs uses default when field is missing."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.rule_utils import _build_target_fields
    from r2x_sienna_to_plexos.translation import Rule

    rule = Rule(
        source_type="ACBus",
        target_type="PLEXOSNode",
        version=1,
        field_map={
            "name": "name",
            "y": "nonexistent_field",
        },
        defaults={
            "y": 99,
        },
    )

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")
    kwargs = _build_target_fields(rule, source_bus, context_with_buses).unwrap_or_raise()

    assert kwargs["y"] == 99


def test_resolve_component_type_sienna(context_with_buses: TranslationContext):
    """resolve_component_type resolves Sienna component types."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.rule_utils import _resolve_component_type

    result = _resolve_component_type("ACBus", context_with_buses)

    assert result.is_ok()
    assert result.unwrap() == ACBus


def test_resolve_component_type_plexos(context_with_buses: TranslationContext):
    """resolve_component_type resolves PLEXOS component types."""
    from r2x_plexos.models import PLEXOSNode
    from r2x_sienna_to_plexos.rule_utils import _resolve_component_type

    result = _resolve_component_type("PLEXOSNode", context_with_buses)

    assert result.is_ok()
    assert result.unwrap() == PLEXOSNode


def test_resolve_component_type_raises_on_unknown(context_with_buses: TranslationContext):
    """resolve_component_type returns error for unknown type."""
    from r2x_sienna_to_plexos.rule_utils import _resolve_component_type

    result = _resolve_component_type("UnknownComponentType", context_with_buses)

    assert result.is_err()
    assert "not found" in str(result.err())


def test_convert_rule_with_nested_load_getter(context_with_bus_and_load: TranslationContext):
    """convert_rule uses nested field getter to extract load."""
    from r2x_plexos.models import PLEXOSNode
    from r2x_sienna.models import PowerLoad
    from r2x_sienna_to_plexos import Rule, apply_single_rule

    def get_load_from_power_load(ctx, component):
        """Extract and aggregate PowerLoad for a bus."""
        from r2x_core import Ok

        total_load = 0.0
        loads = ctx.source_system.get_components(PowerLoad, filter_func=lambda x: x.bus == component)
        for load in loads:
            total_load += load.max_active_power
        return Ok(total_load)

    rule = Rule(
        source_type="ACBus",
        target_type="PLEXOSNode",
        version=1,
        field_map={
            "name": "name",
            "uuid": "uuid",
            "load": ["bus"],
        },
        getters={
            "load": get_load_from_power_load,
        },
    )

    converted, skipped = apply_single_rule(rule, context_with_bus_and_load).unwrap_or_raise()

    assert converted > 0
    assert skipped == 0

    nodes = list(context_with_bus_and_load.target_system.get_components(PLEXOSNode))
    assert len(nodes) > 0


def test_getter_receives_correct_context_and_component(
    context_with_buses: TranslationContext,
):
    """Getter function receives correct context and component."""
    from r2x_sienna.models import ACBus
    from r2x_sienna_to_plexos.rule_utils import _build_target_fields
    from r2x_sienna_to_plexos.translation import Rule

    received_context = None
    received_component = None

    def capture_getter(ctx, component):
        from r2x_core import Ok

        nonlocal received_context, received_component
        received_context = ctx
        received_component = component
        return Ok(100.0)  # Return a valid Load value

    rule = Rule(
        source_type="ACBus",
        target_type="PLEXOSNode",
        version=1,
        field_map={
            "name": "name",
            "Load": ["base_voltage"],
        },
        getters={
            "Load": capture_getter,
        },
    )

    source_bus = context_with_buses.source_system.get_component(ACBus, "bus-1")
    _build_target_fields(rule, source_bus, context_with_buses)

    assert received_context == context_with_buses
    assert received_component == source_bus


def test_thermal_standard_rule_populates_generator_fields(context_with_thermal_generators):
    """ThermalStandard conversion populates expected PLEXOS generator values."""
    from r2x_plexos.models import PLEXOSGenerator
    from r2x_sienna_to_plexos import apply_single_rule

    rule = context_with_thermal_generators.get_rule("ThermalStandard", "PLEXOSGenerator", version=1)

    result = apply_single_rule(rule, context_with_thermal_generators)
    assert result.is_ok()
    converted, skipped = result.unwrap()
    assert converted == 5
    assert skipped == 0

    fuel_gen = context_with_thermal_generators.target_system.get_component(PLEXOSGenerator, "thermal-fuel")
    assert fuel_gen.max_capacity == pytest.approx(90.0)
    assert fuel_gen.min_stable_level == pytest.approx(40.0)
    assert fuel_gen.max_ramp_up == pytest.approx(12.0)
    assert fuel_gen.max_ramp_down == pytest.approx(8.0)
    assert fuel_gen.min_up_time == pytest.approx(3.0)
    assert fuel_gen.min_down_time == pytest.approx(1.5)
    assert fuel_gen.initial_generation == pytest.approx(65.0)
    assert fuel_gen.initial_hours_up == pytest.approx(6.0)
    assert fuel_gen.initial_hours_down == pytest.approx(0.0)
    assert fuel_gen.running_cost == pytest.approx(7.5)
    assert fuel_gen.start_cost == pytest.approx(120.0)
    assert fuel_gen.shutdown_cost == pytest.approx(25.0)
    assert fuel_gen.heat_rate == pytest.approx(9.2)
    assert fuel_gen.heat_rate_base == pytest.approx(0.0)
    assert fuel_gen.fuel_price == pytest.approx(2.4)

    vom_gen = context_with_thermal_generators.target_system.get_component(PLEXOSGenerator, "thermal-vom")
    assert vom_gen.max_capacity == pytest.approx(96.0)
    assert vom_gen.min_stable_level == pytest.approx(24.0)
    assert vom_gen.max_ramp_up == pytest.approx(12.0)
    assert vom_gen.max_ramp_down == pytest.approx(8.4)
    assert vom_gen.min_up_time == pytest.approx(4.0)
    assert vom_gen.min_down_time == pytest.approx(2.5)
    assert vom_gen.initial_generation == pytest.approx(36.0)
    assert vom_gen.initial_hours_up == pytest.approx(0.0)
    assert vom_gen.initial_hours_down == pytest.approx(8.0)
    assert vom_gen.mark_up == pytest.approx(14.0)
    assert vom_gen.fuel_price == pytest.approx(0.0)

    piecewise_gen = context_with_thermal_generators.target_system.get_component(
        PLEXOSGenerator,
        "thermal-piecewise",
    )
    load_point_prop = piecewise_gen.get_property_value("load_point")
    heat_rate_prop = piecewise_gen.get_property_value("heat_rate_incr")
    assert load_point_prop.get_bands() == [1, 2]
    assert heat_rate_prop.get_bands() == [1, 2]

    quadratic_gen = context_with_thermal_generators.target_system.get_component(
        PLEXOSGenerator,
        "thermal-quadratic",
    )
    assert quadratic_gen.heat_rate == pytest.approx(9.8)
    assert quadratic_gen.heat_rate_incr == pytest.approx(0.015)
    assert quadratic_gen.heat_rate_base == pytest.approx(120.0)

    markup_piecewise_gen = context_with_thermal_generators.target_system.get_component(
        PLEXOSGenerator,
        "thermal-markup-piecewise",
    )
    mark_up_points = markup_piecewise_gen.get_property_value("mark_up_point")
    mark_up_values = markup_piecewise_gen.get_property_value("mark_up")
    assert mark_up_points.get_bands() == [1, 2]
    assert mark_up_values.get_bands() == [1, 2]
