import pytest
from pint import Quantity
from r2x.exporter.utils import (
    apply_default_value,
    apply_extract_key,
    apply_flatten_key,
    apply_property_map,
    apply_unnest_key,
    apply_valid_properties,
    apply_pint_deconstruction,
    apply_correct_commit,
    get_property_magnitude,
)


@pytest.mark.exporter_utils
def test_apply_correct_commit():
    """Test the apply_correct_commit function."""
    component = {"name": "Gen1", "Commit": False}
    commit_map = {"Commit": {"False": -1}}

    result = apply_correct_commit(component, commit_map)
    assert result == {"name": "Gen1", "Commit": -1}

    # Test when 'Commit' key is True
    component = {"name": "Gen1", "Commit": True}
    result = apply_correct_commit(component, commit_map)
    assert result == component

    # Test when 'Commit' key doesn't exist
    component = {"name": "Gen1"}
    result = apply_correct_commit(component, commit_map)
    assert result == component


@pytest.mark.exporter_utils
def test_apply_property_map():
    """Test the apply_property_map function."""
    component = {"voltage": 230, "current": 10}
    property_map = {"voltage": "v", "current": "i"}

    result = apply_property_map(component, property_map)
    assert result == {"v": 230, "i": 10}

    component = {"voltage": 230, "resistance": 50}
    property_map = {"voltage": "v", "current": "i"}
    result = apply_property_map(component, property_map)
    assert result == {"v": 230, "resistance": 50}

    # Test for empty component
    result = apply_property_map({}, property_map)
    assert result == {}


@pytest.mark.exporter_utils
def test_apply_pint_deconstruction():
    """Test the apply_pint_deconstruction function."""
    component = {"length": Quantity(100, "meters"), "time": Quantity(3600, "seconds")}
    unit_map = {"length": "km", "time": "h"}

    result = apply_pint_deconstruction(component, unit_map)
    assert result["length"] == 0.1  # 100 meters to kilometers
    assert result["time"] == 1  # 3600 seconds to hours

    result = apply_pint_deconstruction(component, {})
    assert result["length"] == 100
    assert result["time"] == 3600


@pytest.mark.exporter_utils
def test_apply_valid_properties():
    """Test the apply_valid_properties function."""
    component = {"voltage": 230, "current": 10, "resistance": 50}
    valid_properties = ["voltage", "current"]

    # Test filtering
    result = apply_valid_properties(component, valid_properties)
    assert result == {"voltage": 230, "current": 10}

    component_with_name = {"voltage": 230, "current": 10, "resistance": 50, "name": "Component A"}
    valid_properties_with_name = ["voltage", "current"]

    result_with_name = apply_valid_properties(component_with_name, valid_properties_with_name, add_name=True)
    assert result_with_name == {"voltage": 230, "current": 10, "name": "Component A"}

    result_empty = apply_valid_properties(component, [])
    assert result_empty == {}


@pytest.mark.exporter_utils
def test_get_property_magnitude():
    """Test the get_property_magnitude function."""
    q1 = Quantity(100, "meters")  # Pint Quantity
    q2 = Quantity(50, "kilograms")  # Pint Quantity
    q3 = 200  # Not a Quantity

    assert get_property_magnitude(q1, "kilometers") == 0.1  # Convert 100 meters to kilometers
    assert get_property_magnitude(q2, "grams") == 50000  # Convert 50 kg to grams

    assert get_property_magnitude(q3) == 200  # No conversion for a non-Quantity
    assert get_property_magnitude(q1) == 100  # Magnitude of Quantity without conversion


def test_apply_unnest_key_basic_functionality():
    # Test basic functionality
    component = {"name": "Example", "config": {"type": "A", "value": 10}, "data": {"content": "Some data"}}
    key_map = {"config": "type", "data": "content"}
    result = apply_unnest_key(component, key_map)

    assert result == {"name": "Example", "config": "A", "data": "Some data"}

    # Test no change when key is not in key_map
    component = {"name": "Example", "value": 42}
    key_map = {"config": "type"}
    result = apply_unnest_key(component, key_map)
    assert result == component

    # Test nested dictionary with no corresponding key in key_map
    component = {"name": "Example", "config": {"type": "A", "value": 10}}
    key_map = {"name": "type"}
    result = apply_unnest_key(component, key_map)
    assert result == component


def test_apply_unnest_key_edge_cases():
    # Test missing nested key
    component = {"config": {"value": 10}, "data": {"content": "Some data"}}
    key_map = {"config": "type", "data": "content"}
    result = apply_unnest_key(component, key_map)
    assert result == {"config": {"value": 10}, "data": "Some data"}

    # Test empty input
    assert apply_unnest_key({}, {"config": "type"}) == {}

    # Test empty key_map
    component = {"name": "Example", "config": {"type": "A", "value": 10}}
    assert apply_unnest_key(component, {}) == component


# Parameterized tests
@pytest.mark.parametrize(
    "component,key_map,expected",
    [
        ({"a": {"x": 1, "y": 2}, "b": {"z": 3}}, {"a": "x", "b": "z"}, {"a": 1, "b": 3}),
        (
            {"a": 1, "b": {"x": 2, "y": 3}, "c": "test"},
            {"b": "y", "c": "nonexistent"},
            {"a": 1, "b": 3, "c": "test"},
        ),
        ({"a": {"x": {"nested": "value"}}, "b": 2}, {"a": "x", "b": "y"}, {"a": {"nested": "value"}, "b": 2}),
    ],
)
def parameterized_test(component, key_map, expected):
    assert apply_unnest_key(component, key_map) == expected


def test_flatten_selected_keys():
    d1 = {"x": {"min": 1, "max": 2}, "y": {"min": 5, "max": 10}, "z": 42}
    result1 = apply_flatten_key(d1, {"x"})
    expected1 = {"x_min": 1, "x_max": 2, "y": {"min": 5, "max": 10}, "z": 42}
    assert result1 == expected1

    result2 = apply_flatten_key(d1, {"y"})
    expected2 = {"x": {"min": 1, "max": 2}, "y_min": 5, "y_max": 10, "z": 42}
    assert result2 == expected2

    result3 = apply_flatten_key(d1, set())
    expected3 = d1
    assert result3 == expected3

    result4 = apply_flatten_key(d1, {"x", "y"})
    expected4 = {"x_min": 1, "x_max": 2, "y_min": 5, "y_max": 10, "z": 42}
    assert result4 == expected4


def test_apply_default_value():
    component = {"name": "example", "year": None}
    default_value_map = {"year": 2024, "month": "October"}
    result = apply_default_value(component, default_value_map)
    assert result == {"name": "example", "year": 2024, "month": "October"}

    component = {"name": "example"}
    default_value_map = {"year": 2024, "month": "October"}
    result = apply_default_value(component, default_value_map)
    assert result == {"name": "example", "year": 2024, "month": "October"}

    component = {"name": "example", "year": 2023}
    default_value_map = {"year": 2024, "month": "October"}
    result = apply_default_value(component, default_value_map)
    assert result == {"name": "example", "year": 2023, "month": "October"}

    component = {"name": "example", "year": 2023}
    default_value_map = {}
    result = apply_default_value(component, default_value_map)
    assert result == {"name": "example", "year": 2023}

    component = {}
    default_value_map = {"year": 2024, "month": "October"}
    result = apply_default_value(component, default_value_map)
    assert result == {"year": 2024, "month": "October"}


def test_extract_key():
    component = {"name": "example", "ext": {"TestNested": 1.0}}
    result = apply_extract_key(component, key="ext", keys_to_extract={"TestNested"})
    assert result is not None
    assert result.get("TestNested", None) is not None
    assert result["TestNested"] == 1.0

    component = {"name": "example", "ext": {"TestNested": 1.0, "TestNested2": "test"}}
    result = apply_extract_key(component, key="ext", keys_to_extract={"TestNested", "TestNested2"})
    assert result is not None
    assert result.get("TestNested", None) is not None
    assert result["TestNested"] == 1.0
    assert result.get("TestNested2", None) is not None
    assert result["TestNested2"] == "test"

    component = {"name": "example"}
    result = apply_extract_key(component, key="ext", keys_to_extract={"TestNested", "TestNested2"})
    assert result is not None
    assert result == component

    component = {"name": "example", "ext": {"TestNested": 1.0, "TestNested2": "test"}}
    result = apply_extract_key(component, key="ext", keys_to_extract={"Test"})
    assert result is not None
    assert result == component
