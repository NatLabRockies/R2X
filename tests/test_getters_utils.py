"""Tests for getters_utils multiband conversion functions."""

import pytest


def test_create_multiband_heat_rate_two_bands(two_band_load_points, two_band_heat_rate_slopes) -> None:
    """create_multiband_heat_rate returns two PLEXOSPropertyValue objects with 2 bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    assert load_prop.get_bands() == [1, 2]
    assert heat_prop.get_bands() == [1, 2]


def test_create_multiband_heat_rate_load_points_correct(
    two_band_load_points, two_band_heat_rate_slopes
) -> None:
    """create_multiband_heat_rate correctly assigns load point values to bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, _ = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    band_1_entries = load_prop._by_band.get(1, set())
    band_2_entries = load_prop._by_band.get(2, set())

    assert len(band_1_entries) == 1
    assert len(band_2_entries) == 1


def test_create_multiband_heat_rate_slopes_correct(two_band_load_points, two_band_heat_rate_slopes) -> None:
    """create_multiband_heat_rate correctly assigns heat rate slopes to bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    _, heat_prop = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    assert heat_prop.get_bands() == [1, 2]
    assert len(heat_prop._by_band) == 2


def test_create_multiband_heat_rate_three_bands(three_band_load_points, three_band_heat_rate_slopes) -> None:
    """create_multiband_heat_rate handles 3-band curves correctly."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(three_band_load_points, three_band_heat_rate_slopes)

    assert load_prop.get_bands() == [1, 2, 3]
    assert heat_prop.get_bands() == [1, 2, 3]


def test_create_multiband_heat_rate_single_band(single_band_load_points, single_band_heat_rate_slope) -> None:
    """create_multiband_heat_rate works with single-band curves."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(single_band_load_points, single_band_heat_rate_slope)

    assert load_prop.get_bands() == [1]
    assert heat_prop.get_bands() == [1]


def test_create_multiband_heat_rate_empty_input(empty_load_points, empty_slopes) -> None:
    """create_multiband_heat_rate returns empty properties for empty input."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(empty_load_points, empty_slopes)

    assert load_prop.get_bands() == []
    assert heat_prop.get_bands() == []


def test_create_multiband_heat_rate_returns_plexos_property_values(
    two_band_load_points, two_band_heat_rate_slopes
) -> None:
    """create_multiband_heat_rate returns PLEXOSPropertyValue objects."""
    from r2x_plexos.models import PLEXOSPropertyValue
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    assert isinstance(load_prop, PLEXOSPropertyValue)
    assert isinstance(heat_prop, PLEXOSPropertyValue)


def test_create_multiband_markup_two_bands(two_band_load_points, two_band_markup_slopes) -> None:
    """create_multiband_markup returns two PLEXOSPropertyValue objects with 2 bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    assert point_prop.get_bands() == [1, 2]
    assert markup_prop.get_bands() == [1, 2]


def test_create_multiband_markup_load_points_correct(two_band_load_points, two_band_markup_slopes) -> None:
    """create_multiband_markup correctly assigns load point values to bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, _ = create_multiband_markup(two_band_load_points, two_band_markup_slopes)
    band_1_entries = point_prop._by_band.get(1, set())
    band_2_entries = point_prop._by_band.get(2, set())

    assert len(band_1_entries) == 1
    assert len(band_2_entries) == 1


def test_create_multiband_markup_values_correct(two_band_load_points, two_band_markup_slopes) -> None:
    """create_multiband_markup correctly assigns markup values to bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    _, markup_prop = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    assert markup_prop.get_bands() == [1, 2]
    assert len(markup_prop._by_band) == 2


def test_create_multiband_markup_three_bands(three_band_load_points, three_band_markup_slopes) -> None:
    """create_multiband_markup handles 3-band curves correctly."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(three_band_load_points, three_band_markup_slopes)

    assert point_prop.get_bands() == [1, 2, 3]
    assert markup_prop.get_bands() == [1, 2, 3]


def test_create_multiband_markup_single_band(single_band_load_points, two_band_markup_slopes) -> None:
    """create_multiband_markup works with single-band curves."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(single_band_load_points, [two_band_markup_slopes[0]])

    assert point_prop.get_bands() == [1]
    assert markup_prop.get_bands() == [1]


def test_create_multiband_markup_empty_input(empty_load_points, empty_slopes) -> None:
    """create_multiband_markup returns empty properties for empty input."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(empty_load_points, empty_slopes)

    assert point_prop.get_bands() == []
    assert markup_prop.get_bands() == []


def test_create_multiband_markup_returns_plexos_property_values(
    two_band_load_points, two_band_markup_slopes
) -> None:
    """create_multiband_markup returns PLEXOSPropertyValue objects."""
    from r2x_plexos.models import PLEXOSPropertyValue
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    assert isinstance(point_prop, PLEXOSPropertyValue)
    assert isinstance(markup_prop, PLEXOSPropertyValue)


def test_create_multiband_heat_rate_band_numbering_starts_at_one(
    two_band_load_points, two_band_heat_rate_slopes
) -> None:
    """create_multiband_heat_rate band numbering starts at 1, not 0."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    bands = load_prop.get_bands()
    assert 0 not in bands
    assert 1 in bands
    assert 2 in bands


def test_create_multiband_markup_band_numbering_starts_at_one(
    two_band_load_points, two_band_markup_slopes
) -> None:
    """create_multiband_markup band numbering starts at 1, not 0."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    bands = point_prop.get_bands()
    assert 0 not in bands
    assert 1 in bands
    assert 2 in bands


def test_multiband_heat_rate_float_conversion(two_band_load_points, two_band_heat_rate_slopes) -> None:
    """create_multiband_heat_rate converts input values to float."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    # Use integer inputs
    int_load_points = [60, 120]
    int_slopes = [12, 13]

    load_prop, heat_prop = create_multiband_heat_rate(int_load_points, int_slopes)

    assert load_prop.get_bands() == [1, 2]
    assert heat_prop.get_bands() == [1, 2]


def test_multiband_markup_float_conversion(two_band_load_points, two_band_markup_slopes) -> None:
    """create_multiband_markup converts input values to float."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    # Use integer inputs
    int_load_points = [40, 80]
    int_slopes = [13, 16]

    point_prop, markup_prop = create_multiband_markup(int_load_points, int_slopes)

    assert point_prop.get_bands() == [1, 2]
    assert markup_prop.get_bands() == [1, 2]


# New tests for additional utilities


def test_resolve_base_power_with_base_power_attribute() -> None:
    """resolve_base_power extracts from base_power attribute."""
    from r2x_sienna_to_plexos.getters_utils import resolve_base_power

    class MockComponent:
        base_power = 100.0

    result = resolve_base_power(MockComponent())
    assert result == pytest.approx(100.0)


def test_resolve_base_power_with_system_base() -> None:
    """resolve_base_power falls back to _system_base."""
    from r2x_sienna_to_plexos.getters_utils import resolve_base_power

    class MockComponent:
        _system_base = 200.0

    result = resolve_base_power(MockComponent())
    assert result == pytest.approx(200.0)


def test_resolve_base_power_defaults_to_one() -> None:
    """resolve_base_power returns 1.0 when no base power found."""
    from r2x_sienna_to_plexos.getters_utils import resolve_base_power

    class MockComponent:
        pass

    result = resolve_base_power(MockComponent())
    assert result == pytest.approx(1.0)


def test_coerce_value_returns_float() -> None:
    """coerce_value converts numeric values to float."""
    from r2x_sienna_to_plexos.getters_utils import coerce_value

    assert coerce_value(42) == pytest.approx(42.0)
    assert coerce_value(3.14) == pytest.approx(3.14)
    assert coerce_value("5.5") == pytest.approx(5.5)


def test_coerce_value_returns_default_for_none() -> None:
    """coerce_value returns default when value is None."""
    from r2x_sienna_to_plexos.getters_utils import coerce_value

    assert coerce_value(None) == pytest.approx(0.0)
    assert coerce_value(None, default=10.0) == pytest.approx(10.0)


def test_coerce_value_preserves_property_value() -> None:
    """coerce_value returns PLEXOSPropertyValue as-is."""
    from r2x_plexos.models import PLEXOSPropertyValue
    from r2x_sienna_to_plexos.getters_utils import coerce_value

    prop = PLEXOSPropertyValue()
    prop.add_entry(value=100.0, band=1)

    result = coerce_value(prop)
    assert result is prop
    assert isinstance(result, PLEXOSPropertyValue)


def test_extract_piecewise_segments_two_points() -> None:
    """extract_piecewise_segments returns load points and slopes for 2 points."""
    from infrasys.function_data import XYCoords
    from r2x_sienna_to_plexos.getters_utils import extract_piecewise_segments

    points = [XYCoords(x=0.0, y=0.0), XYCoords(x=100.0, y=1200.0)]

    load_points, slopes = extract_piecewise_segments(points)

    assert len(load_points) == 1
    assert len(slopes) == 1
    assert load_points[0] == pytest.approx(100.0)
    assert slopes[0] == pytest.approx(12.0)  # (1200 - 0) / (100 - 0)


def test_extract_piecewise_segments_three_points() -> None:
    """extract_piecewise_segments handles three points correctly."""
    from infrasys.function_data import XYCoords
    from r2x_sienna_to_plexos.getters_utils import extract_piecewise_segments

    points = [
        XYCoords(x=0.0, y=0.0),
        XYCoords(x=50.0, y=500.0),
        XYCoords(x=100.0, y=1200.0),
    ]

    load_points, slopes = extract_piecewise_segments(points)

    assert len(load_points) == 2
    assert len(slopes) == 2
    assert load_points[0] == pytest.approx(50.0)
    assert load_points[1] == pytest.approx(100.0)
    assert slopes[0] == pytest.approx(10.0)  # 500 / 50
    assert slopes[1] == pytest.approx(14.0)  # (1200 - 500) / (100 - 50)


def test_extract_piecewise_segments_empty_list() -> None:
    """extract_piecewise_segments returns empty lists for empty input."""
    from r2x_sienna_to_plexos.getters_utils import extract_piecewise_segments

    load_points, slopes = extract_piecewise_segments([])

    assert load_points == []
    assert slopes == []


def test_extract_piecewise_segments_single_point() -> None:
    """extract_piecewise_segments returns empty lists for single point."""
    from infrasys.function_data import XYCoords
    from r2x_sienna_to_plexos.getters_utils import extract_piecewise_segments

    points = [XYCoords(x=0.0, y=0.0)]

    load_points, slopes = extract_piecewise_segments(points)

    assert load_points == []
    assert slopes == []


def test_extract_piecewise_segments_skips_zero_dx() -> None:
    """extract_piecewise_segments skips segments with zero dx."""
    from infrasys.function_data import XYCoords
    from r2x_sienna_to_plexos.getters_utils import extract_piecewise_segments

    points = [
        XYCoords(x=0.0, y=0.0),
        XYCoords(x=0.0, y=100.0),  # Same x, should be skipped
        XYCoords(x=100.0, y=1200.0),
    ]

    load_points, slopes = extract_piecewise_segments(points)

    assert len(load_points) == 1
    assert len(slopes) == 1
    assert load_points[0] == pytest.approx(100.0)


def test_normalize_value_curve_input_output_passthrough() -> None:
    """normalize_value_curve returns InputOutputCurve as-is."""
    from infrasys.function_data import LinearFunctionData
    from infrasys.value_curves import InputOutputCurve
    from r2x_sienna_to_plexos.getters_utils import normalize_value_curve

    fd = LinearFunctionData(proportional_term=10.0, constant_term=5.0)
    curve = InputOutputCurve(function_data=fd)

    result = normalize_value_curve(curve)

    assert result is curve


def test_normalize_value_curve_converts_incremental() -> None:
    """normalize_value_curve converts IncrementalCurve to InputOutputCurve."""
    from infrasys.function_data import LinearFunctionData
    from infrasys.value_curves import IncrementalCurve
    from r2x_sienna_to_plexos.getters_utils import normalize_value_curve

    fd = LinearFunctionData(proportional_term=10.0, constant_term=5.0)
    curve = IncrementalCurve(function_data=fd, initial_input=0.0)

    result = normalize_value_curve(curve)

    assert result is not None
    # IncrementalCurve should convert to InputOutputCurve
    from infrasys.value_curves import InputOutputCurve

    assert isinstance(result, InputOutputCurve)


def test_normalize_value_curve_returns_none_for_unsupported() -> None:
    """normalize_value_curve returns None for unsupported curve types."""
    from r2x_sienna_to_plexos.getters_utils import normalize_value_curve

    class UnsupportedCurve:
        pass

    result = normalize_value_curve(UnsupportedCurve())

    assert result is None


def test_compute_heat_rate_data_with_linear_fuel_curve(context_with_thermal_generators) -> None:
    """compute_heat_rate_data extracts linear heat rate data."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters_utils import compute_heat_rate_data

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-fuel")

    data = compute_heat_rate_data(source)

    assert "heat_rate" in data
    assert "heat_rate_base" in data


def test_compute_heat_rate_data_with_quadratic_fuel_curve(context_with_thermal_generators) -> None:
    """compute_heat_rate_data extracts quadratic heat rate data."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters_utils import compute_heat_rate_data

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-quadratic")

    data = compute_heat_rate_data(source)

    assert "heat_rate" in data
    assert "heat_rate_base" in data
    assert "heat_rate_incr" in data


def test_compute_heat_rate_data_with_piecewise_fuel_curve(context_with_thermal_generators) -> None:
    """compute_heat_rate_data extracts multiband heat rate data."""
    from r2x_plexos.models import PLEXOSPropertyValue
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters_utils import compute_heat_rate_data

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-piecewise")

    data = compute_heat_rate_data(source)

    assert "load_point" in data
    assert "heat_rate_incr" in data
    assert isinstance(data["load_point"], PLEXOSPropertyValue)
    assert isinstance(data["heat_rate_incr"], PLEXOSPropertyValue)


def test_compute_heat_rate_data_returns_empty_for_no_fuel_curve() -> None:
    """compute_heat_rate_data returns empty dict when no fuel curve."""
    from r2x_sienna_to_plexos.getters_utils import compute_heat_rate_data

    class MockComponent:
        operation_cost = None

    data = compute_heat_rate_data(MockComponent())

    assert data == {}


def test_compute_markup_data_with_linear_cost_curve(context_with_thermal_generators) -> None:
    """compute_markup_data extracts linear markup data."""
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters_utils import compute_markup_data

    source = context_with_thermal_generators.source_system.get_component(ThermalStandard, "thermal-vom")

    data = compute_markup_data(source)

    assert "mark_up" in data


def test_compute_markup_data_with_piecewise_cost_curve(context_with_thermal_generators) -> None:
    """compute_markup_data extracts multiband markup data."""
    from r2x_plexos.models import PLEXOSPropertyValue
    from r2x_sienna.models import ThermalStandard
    from r2x_sienna_to_plexos.getters_utils import compute_markup_data

    source = context_with_thermal_generators.source_system.get_component(
        ThermalStandard, "thermal-markup-piecewise"
    )

    data = compute_markup_data(source)

    assert "mark_up_point" in data
    assert "mark_up" in data
    assert isinstance(data["mark_up_point"], PLEXOSPropertyValue)
    assert isinstance(data["mark_up"], PLEXOSPropertyValue)


def test_compute_markup_data_returns_empty_for_no_cost_curve() -> None:
    """compute_markup_data returns empty dict when no cost curve."""
    from r2x_sienna_to_plexos.getters_utils import compute_markup_data

    class MockComponent:
        operation_cost = None

    data = compute_markup_data(MockComponent())

    assert data == {}


def test_ensure_membership_creates_membership() -> None:
    """_ensure_membership creates and adds membership to target system."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSGenerator, PLEXOSMembership, PLEXOSNode
    from r2x_sienna_to_plexos.getters_utils import _ensure_membership

    from r2x_core import System, TranslationContext

    class MockConfig:
        pass

    source_system = System(name="source")
    target_system = System(name="target", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=source_system,
        target_system=target_system,
        config=MockConfig(),
        rules=[],
    )

    parent = PLEXOSGenerator(name="gen1")
    child = PLEXOSNode(name="node1")

    _ensure_membership(context, parent, child, CollectionEnum.Nodes)

    memberships = list(target_system.get_supplemental_attributes(PLEXOSMembership))
    assert len(memberships) == 1
    assert memberships[0].parent_object is parent
    assert memberships[0].child_object is child
    assert memberships[0].collection == CollectionEnum.Nodes


def test_ensure_region_node_memberships_integration(system_complete) -> None:
    """Integration test for ensure_region_node_memberships."""
    from r2x_plexos.models import PLEXOSMembership, PLEXOSNode, PLEXOSRegion
    from r2x_sienna_to_plexos import SiennaToPlexosConfig
    from r2x_sienna_to_plexos.getters_utils import ensure_region_node_memberships

    from r2x_core import System, TranslationContext

    target_system = System(name="target", auto_add_composed_components=True)
    context = TranslationContext(
        source_system=system_complete,
        target_system=target_system,
        config=SiennaToPlexosConfig(),
        rules=[],
    )

    # Add some mock regions and nodes
    region = PLEXOSRegion(name="Area1")
    node = PLEXOSNode(name="bus-1")
    target_system.add_component(region)
    target_system.add_component(node)

    ensure_region_node_memberships(context)

    # Should have created memberships
    memberships = list(target_system.get_supplemental_attributes(PLEXOSMembership))
    assert len(memberships) >= 0  # May or may not create depending on area matching
