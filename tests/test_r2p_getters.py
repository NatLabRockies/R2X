"""Tests for ReEDS-to-PLEXOS getter functions."""

import pytest


def test_forced_outage_rate_percent_converts_to_percentage() -> None:
    """forced_outage_rate_percent converts fraction to percentage."""
    from r2x_reeds_to_plexos.getters import forced_outage_rate_percent

    class MockGenerator:
        forced_outage_rate = 0.05

    class MockContext:
        pass

    result = forced_outage_rate_percent(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(5.0)


def test_forced_outage_rate_percent_handles_none() -> None:
    """forced_outage_rate_percent handles None as zero."""
    from r2x_reeds_to_plexos.getters import forced_outage_rate_percent

    class MockGenerator:
        forced_outage_rate = None

    class MockContext:
        pass

    result = forced_outage_rate_percent(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_min_capacity_factor_percent_converts_to_percentage() -> None:
    """min_capacity_factor_percent converts fraction to percentage."""
    from r2x_reeds_to_plexos.getters import min_capacity_factor_percent

    class MockGenerator:
        min_capacity_factor = 0.30

    class MockContext:
        pass

    result = min_capacity_factor_percent(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(30.0)


def test_line_max_flow_returns_larger_limit() -> None:
    """line_max_flow returns the larger of forward/backward limits."""
    from r2x_reeds_to_plexos.getters import line_max_flow

    class MockLimits:
        from_to = 1000.0
        to_from = 800.0

    class MockLine:
        max_active_power = MockLimits()

    class MockContext:
        pass

    result = line_max_flow(MockContext(), MockLine())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(1000.0)


def test_line_max_flow_handles_none() -> None:
    """line_max_flow returns 0.0 when limits are None."""
    from r2x_reeds_to_plexos.getters import line_max_flow

    class MockLine:
        max_active_power = None

    class MockContext:
        pass

    result = line_max_flow(MockContext(), MockLine())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_line_min_flow_returns_negative_max() -> None:
    """line_min_flow returns negative of maximum absolute flow."""
    from r2x_reeds_to_plexos.getters import line_min_flow

    class MockLimits:
        from_to = 1000.0
        to_from = -800.0

    class MockLine:
        max_active_power = MockLimits()

    class MockContext:
        pass

    result = line_min_flow(MockContext(), MockLine())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(-1000.0)


def test_reserve_timeframe_returns_seconds() -> None:
    """reserve_timeframe returns time frame in seconds."""
    from r2x_reeds_to_plexos.getters import reserve_timeframe

    class MockReserve:
        time_frame = 600.0

    class MockContext:
        pass

    result = reserve_timeframe(MockContext(), MockReserve())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(600.0)


def test_reserve_duration_returns_seconds() -> None:
    """reserve_duration returns duration in seconds."""
    from r2x_reeds_to_plexos.getters import reserve_duration

    class MockReserve:
        duration = 3600.0

    class MockContext:
        pass

    result = reserve_duration(MockContext(), MockReserve())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(3600.0)


def test_reserve_requirement_returns_mw() -> None:
    """reserve_requirement returns requirement in MW."""
    from r2x_reeds_to_plexos.getters import reserve_requirement

    class MockReserve:
        max_requirement = 500.0

    class MockContext:
        pass

    result = reserve_requirement(MockContext(), MockReserve())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(500.0)


def test_ramp_rate_mw_per_hour_converts_from_per_minute() -> None:
    """ramp_rate_mw_per_hour converts MW/min to MW/hour."""
    from r2x_reeds_to_plexos.getters import ramp_rate_mw_per_hour

    class MockGenerator:
        ramp_rate = 10.0

    class MockContext:
        pass

    result = ramp_rate_mw_per_hour(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(600.0)


def test_ramp_rate_mw_per_hour_handles_none() -> None:
    """ramp_rate_mw_per_hour handles None as zero."""
    from r2x_reeds_to_plexos.getters import ramp_rate_mw_per_hour

    class MockGenerator:
        ramp_rate = None

    class MockContext:
        pass

    result = ramp_rate_mw_per_hour(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_min_stable_level_mw_converts_fraction_to_mw() -> None:
    """min_stable_level_mw converts fraction to MW based on capacity."""
    from r2x_reeds_to_plexos.getters import min_stable_level_mw

    class MockGenerator:
        min_stable_level = 0.4
        capacity = 100.0

    class MockContext:
        pass

    result = min_stable_level_mw(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(40.0)


def test_min_stable_level_mw_handles_none() -> None:
    """min_stable_level_mw handles None as zero."""
    from r2x_reeds_to_plexos.getters import min_stable_level_mw

    class MockGenerator:
        min_stable_level = None
        capacity = 100.0

    class MockContext:
        pass

    result = min_stable_level_mw(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_min_up_time_hours_returns_hours() -> None:
    """min_up_time_hours returns minimum up time in hours."""
    from r2x_reeds_to_plexos.getters import min_up_time_hours

    class MockGenerator:
        min_up_time = 4.0

    class MockContext:
        pass

    result = min_up_time_hours(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(4.0)


def test_min_down_time_hours_returns_hours() -> None:
    """min_down_time_hours returns minimum down time in hours."""
    from r2x_reeds_to_plexos.getters import min_down_time_hours

    class MockGenerator:
        min_down_time = 2.0

    class MockContext:
        pass

    result = min_down_time_hours(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(2.0)


def test_vre_category_with_resource_class() -> None:
    """vre_category_with_resource_class combines technology and resource class."""
    from r2x_reeds_to_plexos.getters import vre_category_with_resource_class

    class MockGenerator:
        technology = "WIND"
        resource_class = "CLASS1"

    class MockContext:
        pass

    result = vre_category_with_resource_class(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == "WIND-CLASS1"


def test_vre_category_without_resource_class() -> None:
    """vre_category_with_resource_class returns just technology if no resource class."""
    from r2x_reeds_to_plexos.getters import vre_category_with_resource_class

    class MockGenerator:
        technology = "SOLAR"
        resource_class = None

    class MockContext:
        pass

    result = vre_category_with_resource_class(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == "SOLAR"


def test_supply_curve_cost_getter() -> None:
    """supply_curve_cost_getter returns supply curve cost."""
    from r2x_reeds_to_plexos.getters import supply_curve_cost_getter

    class MockGenerator:
        supply_curve_cost = 1500.0

    class MockContext:
        pass

    result = supply_curve_cost_getter(MockContext(), MockGenerator())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(1500.0)


def test_storage_energy_from_duration_or_explicit_uses_explicit() -> None:
    """storage_energy_from_duration_or_explicit uses explicit energy_capacity if provided."""
    from r2x_reeds_to_plexos.getters import storage_energy_from_duration_or_explicit

    class MockStorage:
        energy_capacity = 1000.0
        capacity = 250.0
        storage_duration = 2.0

    class MockContext:
        pass

    result = storage_energy_from_duration_or_explicit(MockContext(), MockStorage())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(1000.0)


def test_storage_energy_from_duration_or_explicit_calculates() -> None:
    """storage_energy_from_duration_or_explicit calculates from duration and power."""
    from r2x_reeds_to_plexos.getters import storage_energy_from_duration_or_explicit

    class MockStorage:
        energy_capacity = None
        capacity = 250.0
        storage_duration = 4.0

    class MockContext:
        pass

    result = storage_energy_from_duration_or_explicit(MockContext(), MockStorage())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(1000.0)


def test_storage_capital_cost_power() -> None:
    """storage_capital_cost_power returns power-based capital cost."""
    from r2x_reeds_to_plexos.getters import storage_capital_cost_power

    class MockStorage:
        capital_cost = 5000.0

    class MockContext:
        pass

    result = storage_capital_cost_power(MockContext(), MockStorage())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(5000.0)


def test_storage_fom_cost_power() -> None:
    """storage_fom_cost_power returns power-based FOM cost."""
    from r2x_reeds_to_plexos.getters import storage_fom_cost_power

    class MockStorage:
        fom_cost = 50.0

    class MockContext:
        pass

    result = storage_fom_cost_power(MockContext(), MockStorage())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(50.0)


def test_hydro_min_flow() -> None:
    """hydro_min_flow extracts minimum flow from flow_range."""
    from r2x_reeds_to_plexos.getters import hydro_min_flow

    class MockFlowRange:
        min = 10.0
        max = 100.0

    class MockHydro:
        flow_range = MockFlowRange()

    class MockContext:
        pass

    result = hydro_min_flow(MockContext(), MockHydro())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(10.0)


def test_hydro_ramp_rate_mw_per_hour() -> None:
    """hydro_ramp_rate_mw_per_hour converts MW/min to MW/hour."""
    from r2x_reeds_to_plexos.getters import hydro_ramp_rate_mw_per_hour

    class MockHydro:
        ramp_rate = 5.0

    class MockContext:
        pass

    result = hydro_ramp_rate_mw_per_hour(MockContext(), MockHydro())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(300.0)


def test_hydro_must_run_flag_non_dispatchable() -> None:
    """hydro_must_run_flag returns 1 for non-dispatchable hydro."""
    from r2x_reeds_to_plexos.getters import hydro_must_run_flag

    class MockHydro:
        is_dispatchable = False

    class MockContext:
        pass

    result = hydro_must_run_flag(MockContext(), MockHydro())

    assert result.is_ok()
    assert result.unwrap() == 1


def test_hydro_must_run_flag_dispatchable() -> None:
    """hydro_must_run_flag returns 0 for dispatchable hydro."""
    from r2x_reeds_to_plexos.getters import hydro_must_run_flag

    class MockHydro:
        is_dispatchable = True

    class MockContext:
        pass

    result = hydro_must_run_flag(MockContext(), MockHydro())

    assert result.is_ok()
    assert result.unwrap() == 0


def test_consuming_tech_load_mw() -> None:
    """consuming_tech_load_mw returns consumption capacity."""
    from r2x_reeds_to_plexos.getters import consuming_tech_load_mw

    class MockTech:
        capacity = 150.0

    class MockContext:
        pass

    result = consuming_tech_load_mw(MockContext(), MockTech())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(150.0)


def test_consuming_tech_efficiency_to_heat_rate() -> None:
    """consuming_tech_efficiency_to_heat_rate converts efficiency to heat rate."""
    from r2x_reeds_to_plexos.getters import consuming_tech_efficiency_to_heat_rate

    class MockTech:
        electricity_efficiency = 0.8

    class MockContext:
        pass

    result = consuming_tech_efficiency_to_heat_rate(MockContext(), MockTech())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(1.25)


def test_consuming_tech_efficiency_to_heat_rate_handles_zero() -> None:
    """consuming_tech_efficiency_to_heat_rate handles zero efficiency."""
    from r2x_reeds_to_plexos.getters import consuming_tech_efficiency_to_heat_rate

    class MockTech:
        electricity_efficiency = 0.0

    class MockContext:
        pass

    result = consuming_tech_efficiency_to_heat_rate(MockContext(), MockTech())

    assert result.is_ok()
    assert result.unwrap() == pytest.approx(0.0)


def test_reeds_membership_parent_component() -> None:
    """reeds_membership_parent_component returns component itself."""
    from r2x_reeds_to_plexos.getters import reeds_membership_parent_component

    class MockComponent:
        name = "test"

    class MockContext:
        pass

    component = MockComponent()
    result = reeds_membership_parent_component(MockContext(), component)

    assert result.is_ok()
    assert result.unwrap() is component


def test_reeds_membership_collection_nodes() -> None:
    """reeds_membership_collection_nodes returns CollectionEnum.Nodes."""
    from plexosdb import CollectionEnum
    from r2x_reeds_to_plexos.getters import reeds_membership_collection_nodes

    class MockContext:
        pass

    result = reeds_membership_collection_nodes(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.Nodes


def test_reeds_membership_collection_node_from() -> None:
    """reeds_membership_collection_node_from returns CollectionEnum.NodeFrom."""
    from plexosdb import CollectionEnum
    from r2x_reeds_to_plexos.getters import reeds_membership_collection_node_from

    class MockContext:
        pass

    result = reeds_membership_collection_node_from(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.NodeFrom


def test_reeds_membership_collection_node_to() -> None:
    """reeds_membership_collection_node_to returns CollectionEnum.NodeTo."""
    from plexosdb import CollectionEnum
    from r2x_reeds_to_plexos.getters import reeds_membership_collection_node_to

    class MockContext:
        pass

    result = reeds_membership_collection_node_to(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.NodeTo


def test_reeds_membership_collection_region() -> None:
    """reeds_membership_collection_region returns CollectionEnum.Region."""
    from plexosdb import CollectionEnum
    from r2x_reeds_to_plexos.getters import reeds_membership_collection_region

    class MockContext:
        pass

    result = reeds_membership_collection_region(MockContext(), None)

    assert result.is_ok()
    assert result.unwrap() == CollectionEnum.Region


def test_reeds_getters_registered() -> None:
    """Verify all ReEDS getters are registered."""
    from r2x_core.getters import GETTER_REGISTRY

    expected_getters = [
        "forced_outage_rate_percent",
        "min_capacity_factor_percent",
        "line_min_flow",
        "reserve_timeframe",
        "reserve_duration",
        "reserve_requirement",
        "ramp_rate_mw_per_hour",
        "min_stable_level_mw",
        "min_up_time_hours",
        "min_down_time_hours",
    ]

    for getter_name in expected_getters:
        assert getter_name in GETTER_REGISTRY, f"{getter_name} not registered"
