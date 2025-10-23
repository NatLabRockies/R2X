"""Tests for common utility functions."""

from r2x.common.utils import create_unit_value, get_object_id


def test_create_unit_value():
    """Test creating unit value dictionary."""
    result = create_unit_value(100.0, "MW")
    assert isinstance(result, dict)
    assert result["value"] == 100.0
    assert result["unit"] == "MW"


def test_create_unit_value_different_units():
    """Test creating unit values with different units."""
    mw_result = create_unit_value(50.0, "MW")
    assert mw_result == {"value": 50.0, "unit": "MW"}

    kv_result = create_unit_value(230.0, "kV")
    assert kv_result == {"value": 230.0, "unit": "kV"}

    mvar_result = create_unit_value(25.5, "MVAr")
    assert mvar_result == {"value": 25.5, "unit": "MVAr"}


def test_get_object_id_with_attribute():
    """Test extracting object_id from object with object_id attribute."""

    class MockComponent:
        def __init__(self, object_id):
            self.object_id = object_id

    component = MockComponent(42)
    result = get_object_id(component)
    assert result == 42


def test_get_object_id_with_ext_dict():
    """Test extracting object_id from ext dictionary."""

    class MockComponent:
        def __init__(self, object_id):
            self.ext = {"object_id": object_id}

    component = MockComponent(123)
    result = get_object_id(component)
    assert result == 123


def test_get_object_id_none():
    """Test get_object_id returns None when not found."""

    class MockComponent:
        pass

    component = MockComponent()
    result = get_object_id(component)
    assert result is None


def test_get_object_id_prefers_attribute():
    """Test that attribute is preferred over ext dict."""

    class MockComponent:
        def __init__(self):
            self.object_id = 42
            self.ext = {"object_id": 100}

    component = MockComponent()
    result = get_object_id(component)
    assert result == 42
