"""Helper functions for the exporters."""

from typing import Any
from collections.abc import Callable
from r2x.enums import ReserveType, ReserveDirection
import pint
from infrasys.base_quantity import BaseQuantity


def get_reserve_type(
    reserve_type: ReserveType, reserve_direction: ReserveDirection, reserve_types: dict[str, dict[str, str]]
) -> str:
    """Return the reserve type from a mapping.

    If not found, return default reserve type
    """
    for key, value in reserve_types.items():
        if value["type"] == reserve_type and value["direction"] == reserve_direction:
            return key
    return get_reserve_type(
        ReserveType[reserve_types["default"]["type"]],
        ReserveDirection[reserve_types["default"]["direction"]],
        reserve_types,
    )


def compose(
    *functions: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """
    Compose multiple functions, applying them sequentially to the input data.

    Parameters
    ----------
    functions : Callable[[Dict[str, Any]], Dict[str, Any]]
        Functions that transform a dictionary.

    Returns
    -------
    Callable[[Dict[str, Any]], Dict[str, Any]]
        A function that sequentially applies the provided functions to a dictionary.
    """

    def apply_all(data: dict[str, Any]) -> dict[str, Any]:
        for func in functions:
            data = func(data)
        return data

    return apply_all


def modify_components(
    *transform_functions: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Apply multiple transformations to components."""
    return compose(*transform_functions)


def apply_property_map(component: dict[str, Any], property_map: dict[str, str]) -> dict[str, Any]:
    """Apply a key mapping to component keys.

    For each key in the `component` dictionary, if the key exists in the `property_map`,
    it will be replaced by the corresponding mapped key. Otherwise, the original key is used.

    Parameters
    ----------
    component : dict[str, Any]
        The original dictionary where keys represent component properties.
    property_map : dict[str, str]
        A dictionary mapping old property names to new property names.

    Returns
    -------
    dict[str, Any]
        A new dictionary where the keys have been remapped according to `property_map`.

    Examples
    --------
    >>> component = {"voltage": 230, "current": 10}
    >>> property_map = {"voltage": "v", "current": "i"}
    >>> apply_property_map(component, property_map)
    {'v': 230, 'i': 10}

    >>> component = {"voltage": 230, "resistance": 50}
    >>> property_map = {"voltage": "v", "current": "i"}
    >>> apply_property_map(component, property_map)
    {'v': 230, 'resistance': 50}
    """
    return {property_map.get(key, key): value for key, value in component.items()}


def apply_pint_deconstruction(component: dict[str, Any], unit_map: dict[str, str]) -> dict[str, Any]:
    """Get property magnitude from a pint Quantity.

    If unit_map is passed, convert to units specified

    Parameters
    ----------
    component: dict[str, Any]
        Dictionary representation of component. Typically created with `.model_dump()`
    unit_map: dict[str, str]
        Map to convert property to a desired units. Optional.
    """
    return {
        property: get_property_magnitude(property_value, to_unit=unit_map.get(property, None))
        for property, property_value in component.items()
    }


def apply_valid_properties(
    component: dict[str, Any], valid_properties: list[str], add_name: bool = False
) -> dict[str, Any]:
    """Filter a component dictionary to only include keys that are in the valid properties list.

    Parameters
    ----------
    component : dict of str to Any
        A dictionary representing the component with properties as keys.
    valid_properties : list of str
        A list of valid property names. Only keys present in this list will be kept in the output.

    Returns
    -------
    dict
        A new dictionary with only the properties from `valid_properties`.

    Examples
    --------
    >>> component = {"voltage": 230, "current": 10, "resistance": 50}
    >>> valid_properties = ["voltage", "current"]
    >>> apply_valid_properties(component, valid_properties)
    {'voltage': 230, 'current': 10}
    """
    if add_name:
        default_properties = ["name"]
        return {
            key: value
            for key, value in component.items()
            if key in valid_properties or key in default_properties
        }
    return {key: value for key, value in component.items() if key in valid_properties}


def apply_unnest_key(component: dict[str, Any], key_map: dict[str, Any]) -> dict[str, Any]:
    """Unnest specific nested dictionary values based on a provided key map.

    This function processes a dictionary, potentially containing nested dictionaries,
    and unnests specific values based on a provided key map. For each key in the input
    dictionary that has a corresponding entry in the key map, if the value is a dictionary,
    it extracts the value using the mapped key.

    Parameters
    ----------
    component : dict[str, Any]
        The input dictionary to process.
    key_map : dict[str, Any]
        A dictionary mapping keys in the input dictionary to keys in nested dictionaries.

    Returns
    -------
    dict[str, Any]
        A new dictionary with unnested values based on the key map.

    Examples
    --------
    >>> component = {
    ...     "name": "Example",
    ...     "config": {"type": "A", "value": 10},
    ...     "data": {"content": "Some data"},
    ... }
    >>> key_map = {"config": "type", "data": "content"}
    >>> apply_unnest_key(component, key_map)
    {'name': 'Example', 'config': 'A', 'data': 'Some data'}

    Notes
    -----
    - If a key in the input dictionary is not in the key map, its value remains unchanged.
    - If a key is in the key map but the corresponding value in the input dictionary
      is not a dictionary, the value remains unchanged.
    - If a key is in the key map and the corresponding value is a dictionary, but the
      mapped key is not in this nested dictionary, the result for this key will be None.
    """
    if not key_map:
        return component
    return {
        key: value if not isinstance(value, dict) else value.get(key_map.get(key), value)
        for key, value in component.items()
    }


def apply_default_value(component: dict[str, Any], default_value_map: dict[str, Any]) -> dict[str, Any]:
    """Unnest specific nested dictionary values based on a provided key map.

    This function iterates over a dictionary (`component`) and applies default values
    to its missing or `None` values using a `default_value_map`. For each key in
    `default_value_map`, if the key is not present in `component` or has a `None` value,
    it will be assigned the corresponding default value from `default_value_map`.

    Parameters
    ----------
    component : dict[str, Any]
        The input dictionary to process.
    default_value_map : dict[str, Any]
        A dictionary specifying default values. Each key in this dictionary corresponds
        to a key in `component`, and the associated value is the default value to apply
        if the key is missing or `None` in `component`.

    Returns
    -------
    dict[str, Any]
        A new dictionary with unnested values based on the key map.

    Examples
    --------
    >>> component = {"name": "example", "year": None}
    >>> default_value_map = {"year": 2024, "month": "M10"}
    >>> apply_default_value(component, default_value_map)
    {'name': 'example', 'year': 2024, 'month': 'M10'}

    >>> component = {"name": "example", "year": 2023}
    >>> default_value_map = {"year": 2024, "month": "M10"}
    >>> apply_default_value(component, default_value_map)
    {'name': 'example', 'year': 2023, 'month': 'M10'}
    """
    if not default_value_map:
        return component
    for key in default_value_map:
        if key not in component:
            component[key] = default_value_map[key]
        if component.get(key, None) is None:
            component[key] = default_value_map[key]
    return component


def get_property_magnitude(property_value, to_unit: str | None = None) -> Any:
    """Return magnitude with the given units for a pint Quantity.

    Parameters
    ----------
    property_name

    property_value
        pint.Quantity to extract magnitude from
    to_unit
        String that contains the unit conversion desired. Unit must be compatible.

    Returns
    -------
    float
        Magnitude representation of the `pint.Quantity` or original value.
    """
    if not isinstance(property_value, pint.Quantity | BaseQuantity):
        return property_value
    if to_unit:
        unit = to_unit.replace("$", "usd")  # Dollars are named usd on pint
        property_value = property_value.to(unit)
    return property_value.magnitude


def apply_flatten_key(d: dict[str, Any], keys_to_flatten: set[str]) -> dict[str, Any]:
    """Flatten the specified keys in a dictionary by merging their sub-keys into the main dictionary
    with the key's name prefixed to each sub-key.

    Parameters
    ----------
    d : dict
        The input dictionary, where some values are dictionaries to be flattened.
    keys_to_flatten : list of str
        The keys in the dictionary `d` to be flattened if they contain sub-keys.

    Returns
    -------
    dict
        A new dictionary with the selected keys flattened. Other keys remain unchanged.

    Examples
    --------
    >>> d = {"x": {"min": 1, "max": 2}, "y": {"min": 5, "max": 10}, "z": 42}
    >>> flatten_selected_keys(d, ["x"])
    {'x_min': 1, 'x_max': 2, 'y': {'min': 5, 'max': 10}, 'z': 42}

    >>> flatten_selected_keys(d, ["y"])
    {'x': {'min': 1, 'max': 2}, 'y_min': 5, 'y_max': 10, 'z': 42}
    """
    flattened_dict = {}

    for key, value in d.items():
        if key in keys_to_flatten and isinstance(value, dict):
            for inner_key, inner_value in value.items():
                flattened_dict[f"{key}_{inner_key}"] = inner_value
        else:
            flattened_dict[key] = value

    return flattened_dict


def apply_extract_key(d: dict[str, Any], key: str, keys_to_extract: set[str]) -> dict[str, Any]:
    """Extract keys from a nested dictionary and put them in the first level if specific conditions are met.

    Parameters
    ----------
    d : dict
        The input dictionary that may contain nested dictionaries.
    key : str
        The key in the input dictionary whose value should be a nested dictionary.
    keys_to_extract : set[str]
        The set of keys to extract from the nested dictionary.

    Returns
    -------
    dict
        If conditions are met: a new dictionary containing all original key-value pairs
        plus the extracted key-value pairs at the top level.
        If conditions are not met: returns the input dictionary unchanged.

    Notes
    -----
    The function will return the input dictionary unchanged if any of these conditions are met:
    - The specified key is not in the input dictionary
    - Any of keys_to_extract already exist in the top level of input dictionary
    - None of keys_to_extract exist in the nested dictionary

    Examples
    --------
    >>> component = {"name": "Gen01", "rating": {"up": 100, "down": -100}}
    >>> apply_extract_key(component, "rating", {"up"})
    {'name': 'Gen01', 'rating': {'up': 100, 'down': -100}, 'up': 100}

    >>> # Returns unchanged when extracted key already exists at top level
    >>> d = {"name": "Gen01", "rating": {"up": 100}, "up": 50}
    >>> apply_extract_key(d, "rating", {"up"})
    {'name': 'Gen01', 'rating': {'up': 100}, 'up': 50}

    >>> # Returns unchanged when no keys_to_extract exist in nested dict
    >>> apply_extract_key(component, "rating", {"middle"})
    {'name': 'Gen01', 'rating': {'up': 100, 'down': -100}}
    """
    if key not in d.keys() or any(k in d.keys() for k in keys_to_extract):
        return d

    if not any(k in d[key].keys() for k in keys_to_extract):
        return d

    extracted_keys = {key: value for key, value in d[key].items() if key in keys_to_extract}
    return {**d, **extracted_keys}


def apply_correct_commit(component: dict[str, Any], commit_map: dict[str, dict[str, int]]) -> dict[str, Any]:
    """Set the value of the key to -1 if the specified key exists but is False.

    Parameters
    ----------
    component : dict[str, Any]
        The input dictionary that may contain nested dictionaries.
    commit_map : dict[str, dict[str, int]]
        Nested dictionary mapping the 'Commit' key to its value.

    Returns
    -------
    dict[str, Any]
        The updated dictionary with the modified value of the key 'Commit'

    Examples
    --------
    >>> comp = {"name": "Gen01", "Commit": False}
    >>> commit_map = {"Commit": {"False": -1}}
    >>> apply_correct_commit(comp, commit_map)
    {'name': 'Gen01', 'Commit': -1}
    """
    for key, value_map in commit_map.items():
        if key in component and isinstance(component[key], bool) and not component[key]:
            component[key] = value_map.get("False", component[key])
    return component
