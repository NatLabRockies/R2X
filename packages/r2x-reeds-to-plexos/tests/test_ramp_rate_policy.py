"""Ramp fallback precedence, warnings, and rule-driven translation preflight."""

import json
from importlib.resources import files
from unittest.mock import Mock

import pytest
from loguru import logger
from r2x_plexos.models import PLEXOSGenerator
from r2x_reeds.models import (
    ReEDSGenerator,
    ReEDSHydroGenerator,
    ReEDSRegion,
    ReEDSStorage,
    ReEDSThermalGenerator,
    ReEDSVariableGenerator,
)
from r2x_reeds_to_plexos import getters
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig
from r2x_reeds_to_plexos.translation import reeds_to_plexos

from r2x_core import PluginContext, Rule, System


@pytest.fixture
def ramp_messages():
    messages = []
    logger.enable("r2x_reeds_to_plexos")
    sink = logger.add(lambda message: messages.append(str(message)), level="WARNING")
    try:
        yield messages
    finally:
        logger.remove(sink)
        logger.disable("r2x_reeds_to_plexos")


@pytest.fixture
def region():
    return ReEDSRegion(name="p1", transmission_region="WECC")


@pytest.fixture
def thermal(region):
    return ReEDSThermalGenerator(
        name="GEN",
        region=region,
        category="thermal",
        technology="unmapped-ramp-test",
        capacity=100.0,
        heat_rate=9.5,
        fuel_type="gas",
    )


@pytest.fixture
def rules():
    return tuple(
        Rule.from_records(json.loads(files("r2x_reeds_to_plexos.config").joinpath("rules.json").read_text()))
    )


def make_context(fallback=1.0, **kwargs):
    return PluginContext(
        config=ReedsToPlexosConfig(missing_ramp_rate_fraction_per_minute=fallback),
        **kwargs,
    )


def ramp_values(generator, context):
    return (
        getters.ramp_rate_up_mw_per_minute(generator, context).unwrap(),
        getters.ramp_rate_down_mw_per_minute(generator, context).unwrap(),
    )


@pytest.mark.parametrize(
    "defaults,fallback,expected,fallback_directions",
    [
        ({"ramp_rate_up": 7.0, "ramp_rate_down": 3.0, "max_ramp_up_percentage": 0.05}, None, (7.0, 3.0), ()),
        ({"max_ramp_up_percentage": 0.05}, None, (5.0, 5.0), ()),
        ({"ramp_rate_up": 7.0, "max_ramp_up_percentage": 0.05}, None, (7.0, 5.0), ()),
        ({"ramp_rate_down": 3.0, "max_ramp_up_percentage": 0.05}, None, (5.0, 3.0), ()),
        ({}, 1.0, (100.0, 100.0), ("up", "down")),
        ({}, 0.2, (20.0, 20.0), ("up", "down")),
        ({}, 0.0, (0.0, 0.0), ("up", "down")),
        ({}, 3.0, (300.0, 300.0), ("up", "down")),
        ({"ramp_rate_up": 7.0}, 0.2, (7.0, 20.0), ("down",)),
        ({"ramp_rate_down": 3.0}, 0.2, (20.0, 3.0), ("up",)),
    ],
)
def test_ramp_default_precedence_and_fallback_warning(
    thermal, monkeypatch, ramp_messages, defaults, fallback, expected, fallback_directions
):
    monkeypatch.setattr(getters, "_get_defaults", lambda _tech, key: defaults.get(key, 0.0))
    before = thermal.model_dump()

    assert ramp_values(thermal, make_context(fallback)) == pytest.approx(expected)
    assert thermal.model_dump() == before
    warnings = [message for message in ramp_messages if "using configured fallback" in message]
    assert len(warnings) == bool(fallback_directions)
    if warnings:
        assert "'GEN'" in warnings[0]
        assert "unmapped-ramp-test" in warnings[0]
        assert "capacity=100.0 MW" in warnings[0]
        assert f"{fallback} fraction/min for {', '.join(fallback_directions)}:" in warnings[0]
        assert f"up={expected[0]} MW/min, down={expected[1]} MW/min" in warnings[0]


@pytest.mark.parametrize("source_rate", [0.0, 0.08, 3.0])
def test_explicit_source_rate_including_zero_bypasses_all_defaults(
    thermal, monkeypatch, ramp_messages, source_rate
):
    thermal.ramp_rate = source_rate
    defaults = Mock(side_effect=AssertionError("Source rate must bypass defaults"))
    monkeypatch.setattr(getters, "_get_defaults", defaults)

    assert ramp_values(thermal, make_context(None)) == pytest.approx((source_rate * 100.0,) * 2)
    defaults.assert_not_called()
    assert not ramp_messages


@pytest.mark.parametrize("defaults", [{}, {"ramp_rate_up": 7.0}, {"ramp_rate_down": 3.0}])
def test_strict_getter_failure_identifies_generator_and_missing_direction(
    thermal, monkeypatch, ramp_messages, defaults
):
    monkeypatch.setattr(getters, "_get_defaults", lambda _tech, key: defaults.get(key, 0.0))
    expected_direction = "down" if "ramp_rate_up" in defaults else "up"
    for getter in (getters.ramp_rate_up_mw_per_minute, getters.ramp_rate_down_mw_per_minute):
        result = getter(thermal, make_context(None))
        assert result.is_err()
        message = str(result.unwrap_err())
        assert "'GEN'" in message
        assert "unmapped-ramp-test" in message
        assert f"usable {expected_direction} default" in message
        assert "missing_ramp_rate_fraction_per_minute is null" in message
    assert any("Failed to resolve generator ramp rate" in message for message in ramp_messages)


def test_strict_mode_uses_real_translator_defaults(thermal, ramp_messages):
    thermal.technology = "gas-cc"

    assert ramp_values(thermal, make_context(None)) == pytest.approx((5.0, 5.0))
    assert not ramp_messages


@pytest.mark.parametrize("key", ["ramp_rate_up", "ramp_rate_down", "max_ramp_up_percentage"])
@pytest.mark.parametrize("value", [-0.1, float("nan"), float("inf")])
def test_invalid_numeric_defaults_are_not_replaced_by_fallback(thermal, monkeypatch, key, value):
    monkeypatch.setattr(getters, "_get_defaults", lambda _tech, field: value if field == key else 0.0)

    result = getters.ramp_rate_up_mw_per_minute(thermal, make_context())

    assert result.is_err()
    assert "Invalid default" in str(result.unwrap_err())


def test_direct_getters_warn_once_and_do_not_reuse_stale_values(thermal, ramp_messages):
    context = make_context(0.2)
    assert ramp_values(thermal, context) == (20.0, 20.0)
    assert ramp_values(thermal, context) == (20.0, 20.0)
    thermal.ramp_rate = 0.08
    assert ramp_values(thermal, context) == (8.0, 8.0)

    assert len([message for message in ramp_messages if "using configured fallback" in message]) == 1


@pytest.mark.parametrize(
    "ramp_getter",
    ["ramp_rate_up_mw_per_minute", getters.ramp_rate_up_mw_per_minute],
    ids=["registered-name", "function"],
)
def test_preflight_supports_named_ramp_getters_and_unnamed_callables(thermal, ramp_getter):
    class UnnamedGetter:
        def __call__(self, component, context):
            return getters.ramp_rate_up_mw_per_minute(component, context)

    unrelated_getter = UnnamedGetter()
    assert not hasattr(unrelated_getter, "__name__")
    source = System(name="callable-getters", auto_add_composed_components=True)
    source.add_component(thermal)
    rules = (
        Rule.from_records(
            [
                {
                    "source_type": "ReEDSThermalGenerator",
                    "target_type": "PLEXOSGenerator",
                    "version": 1,
                    "getters": {"max_ramp_up": ramp_getter},
                }
            ]
        )[0],
        Rule(
            source_type="ReEDSThermalGenerator",
            target_type="PLEXOSGenerator",
            version=1,
            getters={"other_field": unrelated_getter},
        ),
    )
    context = make_context(0.2, source_system=source, rules=rules)

    getters.prepare_generator_ramp_rates(context)

    assert ramp_values(thermal, context) == (20.0, 20.0)
    assert f"generator_ramp_rates:{thermal.uuid}" in context.metadata


def test_preflight_obeys_rules_filters_deduplicates_and_caches(
    thermal, region, rules, monkeypatch, ramp_messages
):
    source = System(name="preflight", auto_add_composed_components=True)
    # This thermal object matches both the thermal and generic-import rules.
    thermal.category = "imports"
    selected = [
        thermal,
        ReEDSHydroGenerator(
            name="HYDRO",
            category="hydro",
            technology="unmapped-hydro",
            region=region,
            capacity=100.0,
            is_dispatchable=True,
        ),
        *[
            ReEDSGenerator(
                name=category, category=category, technology="unmapped-generic", region=region, capacity=100.0
            )
            for category in ("reeds-generator", "imports", "exports")
        ],
    ]
    excluded = [
        ReEDSGenerator(
            name="FILTERED", category="not-selected", technology="unmapped", region=region, capacity=100.0
        ),
        ReEDSVariableGenerator(
            name="VARIABLE", category="wind", technology="wind-ons_1", region=region, capacity=100.0
        ),
        ReEDSStorage(
            name="STORAGE",
            category="storage",
            technology="battery_4",
            region=region,
            capacity=100.0,
            storage_duration=4.0,
            round_trip_efficiency=0.9,
        ),
    ]
    for component in [*selected, *excluded]:
        source.add_component(component)
    before = [component.model_dump() for component in [*selected, *excluded]]
    context = make_context(0.2, source_system=source, rules=rules)
    resolver = Mock(wraps=getters._resolve_generator_ramp_rates)
    monkeypatch.setattr(getters, "_resolve_generator_ramp_rates", resolver)

    getters.prepare_generator_ramp_rates(context)

    assert resolver.call_count == len(selected)
    assert {call.args[0].uuid for call in resolver.call_args_list} == {
        component.uuid for component in selected
    }
    for component in selected:
        assert ramp_values(component, context) == (20.0, 20.0)
    assert resolver.call_count == len(selected)
    for component in excluded:
        assert f"generator_ramp_rates:{component.uuid}" not in context.metadata
    assert len([message for message in ramp_messages if "using configured fallback" in message]) == len(
        selected
    )
    assert [component.model_dump() for component in [*selected, *excluded]] == before


def test_actual_translation_resolves_once_and_leaves_source_unchanged(
    thermal, region, monkeypatch, ramp_messages
):
    source = System(name="translate", auto_add_composed_components=True)
    source.add_component(thermal)
    source.add_component(
        ReEDSVariableGenerator(
            name="VARIABLE", category="wind", technology="wind-ons_1", region=region, capacity=100.0
        )
    )
    before = thermal.model_dump()
    resolver = Mock(wraps=getters._resolve_generator_ramp_rates)
    monkeypatch.setattr(getters, "_resolve_generator_ramp_rates", resolver)

    target = reeds_to_plexos(source, config=ReedsToPlexosConfig(missing_ramp_rate_fraction_per_minute=0.2))

    resolver.assert_called_once()
    translated = {component.name: component for component in target.get_components(PLEXOSGenerator)}
    assert set(translated) == {"GEN", "VARIABLE"}
    assert translated["GEN"].max_ramp_up == 20.0
    assert translated["GEN"].max_ramp_down == 20.0
    assert thermal.model_dump() == before
    assert len([message for message in ramp_messages if "using configured fallback" in message]) == 1


def test_strict_translation_excludes_variable_and_fails_before_target_creation(
    thermal, region, monkeypatch, ramp_messages
):
    source = System(name="strict", auto_add_composed_components=True)
    source.add_component(
        ReEDSVariableGenerator(
            name="VARIABLE", category="wind", technology="wind-ons_1", region=region, capacity=100.0
        )
    )
    config = ReedsToPlexosConfig(missing_ramp_rate_fraction_per_minute=None)
    target = reeds_to_plexos(source, config=config)
    assert [component.name for component in target.get_components(PLEXOSGenerator)] == ["VARIABLE"]
    source.add_component(thermal)
    source.add_component(
        ReEDSGenerator(
            name="MISSING_IMPORT",
            category="imports",
            technology="unmapped-import",
            region=region,
            capacity=100.0,
        )
    )
    manager = Mock(side_effect=AssertionError("Target manager must not be constructed"))
    monkeypatch.setattr("r2x_reeds_to_plexos.translation.TimeSeriesManager", manager)

    with pytest.raises(ValueError) as error:
        reeds_to_plexos(source, config=config)

    manager.assert_not_called()
    assert "'GEN'" in str(error.value)
    assert "'MISSING_IMPORT'" in str(error.value)
    assert "Cannot translate generator ramp rates" in str(error.value)
    assert any("Cannot translate generator ramp rates" in message for message in ramp_messages)


@pytest.mark.parametrize("with_source", [False, True])
def test_preflight_requires_source_system_and_rules(with_source):
    context = make_context(source_system=System(name="empty") if with_source else None)

    with pytest.raises(ValueError, match="Translation rules" if with_source else "Source system"):
        getters.prepare_generator_ramp_rates(context)
