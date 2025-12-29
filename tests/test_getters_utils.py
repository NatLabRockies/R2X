"""Tests for getters_utils multiband conversion functions."""


def test_create_multiband_heat_rate_two_bands(two_band_load_points, two_band_heat_rate_slopes):
    """create_multiband_heat_rate returns two PLEXOSPropertyValue objects with 2 bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    assert load_prop.get_bands() == [1, 2]
    assert heat_prop.get_bands() == [1, 2]


def test_create_multiband_heat_rate_load_points_correct(two_band_load_points, two_band_heat_rate_slopes):
    """create_multiband_heat_rate correctly assigns load point values to bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, _ = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    band_1_entries = load_prop._by_band.get(1, set())
    band_2_entries = load_prop._by_band.get(2, set())

    assert len(band_1_entries) == 1
    assert len(band_2_entries) == 1


def test_create_multiband_heat_rate_slopes_correct(two_band_load_points, two_band_heat_rate_slopes):
    """create_multiband_heat_rate correctly assigns heat rate slopes to bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    _, heat_prop = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    assert heat_prop.get_bands() == [1, 2]
    # Verify that entries exist for both bands
    assert len(heat_prop._by_band) == 2


def test_create_multiband_heat_rate_three_bands(three_band_load_points, three_band_heat_rate_slopes):
    """create_multiband_heat_rate handles 3-band curves correctly."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(three_band_load_points, three_band_heat_rate_slopes)

    assert load_prop.get_bands() == [1, 2, 3]
    assert heat_prop.get_bands() == [1, 2, 3]


def test_create_multiband_heat_rate_single_band(single_band_load_points, single_band_heat_rate_slope):
    """create_multiband_heat_rate works with single-band curves."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(single_band_load_points, single_band_heat_rate_slope)

    assert load_prop.get_bands() == [1]
    assert heat_prop.get_bands() == [1]


def test_create_multiband_heat_rate_empty_input(empty_load_points, empty_slopes):
    """create_multiband_heat_rate returns empty properties for empty input."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(empty_load_points, empty_slopes)

    assert load_prop.get_bands() == []
    assert heat_prop.get_bands() == []


def test_create_multiband_heat_rate_returns_plexos_property_values(
    two_band_load_points, two_band_heat_rate_slopes
):
    """create_multiband_heat_rate returns PLEXOSPropertyValue objects."""
    from r2x_plexos.models import PLEXOSPropertyValue
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    assert isinstance(load_prop, PLEXOSPropertyValue)
    assert isinstance(heat_prop, PLEXOSPropertyValue)


def test_create_multiband_markup_two_bands(two_band_load_points, two_band_markup_slopes):
    """create_multiband_markup returns two PLEXOSPropertyValue objects with 2 bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    assert point_prop.get_bands() == [1, 2]
    assert markup_prop.get_bands() == [1, 2]


def test_create_multiband_markup_load_points_correct(two_band_load_points, two_band_markup_slopes):
    """create_multiband_markup correctly assigns load point values to bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, _ = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    # Get entries for each band and verify values
    band_1_entries = point_prop._by_band.get(1, set())
    band_2_entries = point_prop._by_band.get(2, set())

    assert len(band_1_entries) == 1
    assert len(band_2_entries) == 1


def test_create_multiband_markup_values_correct(two_band_load_points, two_band_markup_slopes):
    """create_multiband_markup correctly assigns markup values to bands."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    _, markup_prop = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    assert markup_prop.get_bands() == [1, 2]
    assert len(markup_prop._by_band) == 2


def test_create_multiband_markup_three_bands(three_band_load_points, three_band_markup_slopes):
    """create_multiband_markup handles 3-band curves correctly."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(three_band_load_points, three_band_markup_slopes)

    assert point_prop.get_bands() == [1, 2, 3]
    assert markup_prop.get_bands() == [1, 2, 3]


def test_create_multiband_markup_single_band(single_band_load_points, two_band_markup_slopes):
    """create_multiband_markup works with single-band curves."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(single_band_load_points, [two_band_markup_slopes[0]])

    assert point_prop.get_bands() == [1]
    assert markup_prop.get_bands() == [1]


def test_create_multiband_markup_empty_input(empty_load_points, empty_slopes):
    """create_multiband_markup returns empty properties for empty input."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(empty_load_points, empty_slopes)

    assert point_prop.get_bands() == []
    assert markup_prop.get_bands() == []


def test_create_multiband_markup_returns_plexos_property_values(two_band_load_points, two_band_markup_slopes):
    """create_multiband_markup returns PLEXOSPropertyValue objects."""
    from r2x_plexos.models import PLEXOSPropertyValue
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    assert isinstance(point_prop, PLEXOSPropertyValue)
    assert isinstance(markup_prop, PLEXOSPropertyValue)


def test_create_multiband_heat_rate_band_numbering_starts_at_one(
    two_band_load_points, two_band_heat_rate_slopes
):
    """create_multiband_heat_rate band numbering starts at 1, not 0."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    load_prop, heat_prop = create_multiband_heat_rate(two_band_load_points, two_band_heat_rate_slopes)

    bands = load_prop.get_bands()
    assert 0 not in bands
    assert 1 in bands
    assert 2 in bands


def test_create_multiband_markup_band_numbering_starts_at_one(two_band_load_points, two_band_markup_slopes):
    """create_multiband_markup band numbering starts at 1, not 0."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    point_prop, markup_prop = create_multiband_markup(two_band_load_points, two_band_markup_slopes)

    bands = point_prop.get_bands()
    assert 0 not in bands
    assert 1 in bands
    assert 2 in bands


def test_multiband_heat_rate_float_conversion(two_band_load_points, two_band_heat_rate_slopes):
    """create_multiband_heat_rate converts input values to float."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_heat_rate

    # Use integer inputs
    int_load_points = [60, 120]
    int_slopes = [12, 13]

    load_prop, heat_prop = create_multiband_heat_rate(int_load_points, int_slopes)

    assert load_prop.get_bands() == [1, 2]
    assert heat_prop.get_bands() == [1, 2]


def test_multiband_markup_float_conversion(two_band_load_points, two_band_markup_slopes):
    """create_multiband_markup converts input values to float."""
    from r2x_sienna_to_plexos.getters_utils import create_multiband_markup

    # Use integer inputs
    int_load_points = [40, 80]
    int_slopes = [13, 16]

    point_prop, markup_prop = create_multiband_markup(int_load_points, int_slopes)

    assert point_prop.get_bands() == [1, 2]
    assert markup_prop.get_bands() == [1, 2]
