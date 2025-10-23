"""Utility functions for R2X (compatibility layer for legacy tests)."""

import json
from enum import Enum
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    """Load JSON file into dictionary.

    Parameters
    ----------
    path : str | Path
        Path to JSON file

    Returns
    -------
    dict[str, Any]
        Dictionary loaded from JSON

    Notes
    -----
    This function is provided for backwards compatibility with legacy tests.
    """
    with open(path) as f:
        data: dict[str, Any] = json.load(f)
        return data


def get_enum_from_string(enum_class: type[Enum], value: str) -> Enum:
    """Get enum member from string value.

    Parameters
    ----------
    enum_class : type[Enum]
        Enum class to search
    value : str
        String value to find

    Returns
    -------
    Enum
        Enum member matching the value

    Raises
    ------
    ValueError
        If value is not found in enum

    Notes
    -----
    This function is provided for backwards compatibility with legacy tests.
    """
    try:
        return enum_class[value]
    except KeyError:
        # Try matching by value instead of name
        for member in enum_class:
            if member.value == value:
                return member
        msg = f"'{value}' is not a valid {enum_class.__name__}"
        raise ValueError(msg) from None
