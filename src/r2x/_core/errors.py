"""Error formatting utilities for rich, actionable error messages."""

import difflib
from typing import Any


def format_validation_error(
    message: str,
    component_name: str | None = None,
    component_type: str | None = None,
    expected: Any = None,
    actual: Any = None,
    suggestion: str | None = None,
) -> str:
    """Format a rich validation error message.

    Parameters
    ----------
    message : str
        Main error message
    component_name : str | None
        Name of the component that failed validation
    component_type : str | None
        Type of the component
    expected : Any | None
        Expected value or condition
    actual : Any | None
        Actual value found
    suggestion : str | None
        Helpful suggestion for fixing the error

    Returns
    -------
    str
        Formatted error message with context

    Examples
    --------
    >>> error = format_validation_error(
    ...     "Invalid capacity",
    ...     component_name="Coal_Plant_1",
    ...     expected="> 0",
    ...     actual="0",
    ...     suggestion="Check max_capacity property"
    ... )
    """
    parts = [message]

    if component_name:
        parts.append(f"  Component: {component_name}")
    if component_type:
        parts.append(f"  Type: {component_type}")
    if expected is not None:
        parts.append(f"  Expected: {expected}")
    if actual is not None:
        parts.append(f"  Got: {actual}")
    if suggestion:
        parts.append(f"  Suggestion: {suggestion}")

    return "\n".join(parts)


def format_mapping_error(
    category: str,
    available_categories: list[str] | None = None,
    suggestion: str | None = None,
) -> str:
    """Format a category mapping error with helpful suggestions.

    Parameters
    ----------
    category : str
        The unknown category that caused the error
    available_categories : list[str] | None
        List of valid categories
    suggestion : str | None
        Suggested category (e.g., from fuzzy matching)

    Returns
    -------
    str
        Formatted error message with available options

    Examples
    --------
    >>> error = format_mapping_error(
    ...     "CoalPlant",
    ...     available_categories=["Coal", "Gas", "Nuclear"],
    ...     suggestion="Coal"
    ... )
    """
    parts = [f"No mapping found for category: '{category}'"]

    if available_categories:
        shown = available_categories[:10]
        parts.append(f"  Available categories: {', '.join(shown)}")
        if len(available_categories) > 10:
            parts.append(f"  ... and {len(available_categories) - 10} more")

    if suggestion:
        parts.append(f"  Did you mean '{suggestion}'?")

    return "\n".join(parts)


def format_translation_error(
    message: str,
    component_name: str | None = None,
    source_type: str | None = None,
    target_type: str | None = None,
    details: str | None = None,
) -> str:
    """Format a translation error with context.

    Parameters
    ----------
    message : str
        Main error message
    component_name : str | None
        Name of component that failed to translate
    source_type : str | None
        Source component type
    target_type : str | None
        Target component type
    details : str | None
        Additional error details

    Returns
    -------
    str
        Formatted error message
    """
    parts = [message]

    if component_name:
        parts.append(f"  Component: {component_name}")
    if source_type:
        parts.append(f"  Source Type: {source_type}")
    if target_type:
        parts.append(f"  Target Type: {target_type}")
    if details:
        parts.append(f"  Details: {details}")

    return "\n".join(parts)


def find_closest_match(target: str, candidates: list[str], cutoff: float = 0.6) -> str | None:
    """Find closest matching string using fuzzy matching.

    Parameters
    ----------
    target : str
        String to find a match for
    candidates : list[str]
        List of candidate strings
    cutoff : float
        Minimum similarity ratio (0-1)

    Returns
    -------
    str | None
        Closest match if similarity > cutoff, else None
    """
    if not candidates:
        return None

    matches = difflib.get_close_matches(target, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None
