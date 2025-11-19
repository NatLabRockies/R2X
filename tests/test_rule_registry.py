"""Tests for rule registry getter decorator.

This module validates that the getter decorator works correctly with all usage patterns:
1. @getter - without parentheses, uses function name as registry key
2. @getter() - with empty parentheses, uses function name as registry key
3. @getter(name="custom") - with name kwarg, uses custom name as registry key
"""

import pytest


def test_getter_without_parentheses_registers_function():
    """@getter without parentheses registers function with its name."""
    from r2x_sienna_to_plexos.rule_registry import GETTER_REGISTRY, getter

    @getter
    def my_test_getter(ctx, comp):
        return "test"

    assert "my_test_getter" in GETTER_REGISTRY
    assert GETTER_REGISTRY["my_test_getter"] is my_test_getter


def test_getter_with_empty_parentheses_registers_function():
    """@getter() with empty parentheses registers function with its name."""
    from r2x_sienna_to_plexos.rule_registry import GETTER_REGISTRY, getter

    @getter()
    def my_empty_paren_getter(ctx, comp):
        return "test"

    assert "my_empty_paren_getter" in GETTER_REGISTRY
    assert GETTER_REGISTRY["my_empty_paren_getter"] is my_empty_paren_getter


def test_getter_with_custom_name_registers_with_that_name():
    """@getter(name="custom") registers function with custom name."""
    from r2x_sienna_to_plexos.rule_registry import GETTER_REGISTRY, getter

    @getter(name="custom_getter_name")
    def some_function(ctx, comp):
        return "test"

    assert "custom_getter_name" in GETTER_REGISTRY
    assert GETTER_REGISTRY["custom_getter_name"] is some_function


def test_getter_first_arg_with_name_kwarg_raises_error():
    """Passing callable as first arg with name kwarg raises error."""
    from r2x_sienna_to_plexos.rule_registry import getter

    def my_func(ctx, comp):
        return "test"

    with pytest.raises(TypeError, match="Cannot specify 'name' when using @getter without parentheses"):
        getter(my_func, name="custom")


def test_getter_with_parentheses_without_name_uses_function_name():
    """@getter() with parentheses but no name uses function name."""
    from r2x_sienna_to_plexos.rule_registry import GETTER_REGISTRY, getter

    @getter()
    def function_with_parens(ctx, comp):
        return "test"

    assert "function_with_parens" in GETTER_REGISTRY


def test_getter_rejects_non_callable_first_argument():
    """@getter rejects non-callable as first positional argument."""
    from r2x_sienna_to_plexos.rule_registry import getter

    with pytest.raises(TypeError, match="first argument must be callable or None"):
        getter("not_a_function")


def test_getter_function_is_returned_unchanged():
    """@getter returns the function unchanged (no wrapper)."""
    from r2x_sienna_to_plexos.rule_registry import getter

    def original_func(ctx, comp):
        """Original docstring."""
        return "result"

    decorated_func = getter(original_func)

    assert decorated_func is original_func
    assert decorated_func.__doc__ == "Original docstring."
    assert decorated_func(None, None) == "result"


def test_getter_with_empty_parentheses_returns_function_unchanged():
    """@getter() returns the decorated function unchanged."""
    from r2x_sienna_to_plexos.rule_registry import getter

    def original_func_empty_parens(ctx, comp):
        """Original docstring."""
        return "result"

    decorator = getter()
    decorated_func = decorator(original_func_empty_parens)

    assert decorated_func is original_func_empty_parens
    assert decorated_func.__doc__ == "Original docstring."


def test_getter_with_custom_name_returns_function_unchanged():
    """@getter(name="...") returns the decorated function unchanged."""
    from r2x_sienna_to_plexos.rule_registry import getter

    def original_func_with_custom_name(ctx, comp):
        """Original docstring."""
        return "result"

    decorator = getter(name="custom_name_test")
    decorated_func = decorator(original_func_with_custom_name)

    assert decorated_func is original_func_with_custom_name


def test_getter_prevents_duplicate_registration():
    """@getter raises error if same name registered twice."""
    from r2x_sienna_to_plexos.rule_registry import GETTER_REGISTRY, getter

    # Clear registry for this test
    original_entries = GETTER_REGISTRY.copy()
    GETTER_REGISTRY.clear()

    try:

        @getter
        def duplicate_name(ctx, comp):
            return "first"

        with pytest.raises(ValueError, match="Getter 'duplicate_name' already registered"):

            @getter
            def duplicate_name(ctx, comp):
                return "second"

    finally:
        # Restore original registry
        GETTER_REGISTRY.clear()
        GETTER_REGISTRY.update(original_entries)


def test_getter_with_custom_name_prevents_duplicate():
    """@getter(name="...") raises error if same custom name registered twice."""
    from r2x_sienna_to_plexos.rule_registry import GETTER_REGISTRY, getter

    # Clear registry for this test
    original_entries = GETTER_REGISTRY.copy()
    GETTER_REGISTRY.clear()

    try:

        @getter(name="same_custom_name")
        def first_func(ctx, comp):
            return "first"

        with pytest.raises(ValueError, match="Getter 'same_custom_name' already registered"):

            @getter(name="same_custom_name")
            def second_func(ctx, comp):
                return "second"

    finally:
        # Restore original registry
        GETTER_REGISTRY.clear()
        GETTER_REGISTRY.update(original_entries)


def test_getter_callable_with_result_type():
    """@getter decorated function returns Result type correctly."""
    from r2x_sienna_to_plexos.rule_registry import getter

    from r2x_core import Ok

    @getter
    def test_getter_func(ctx, comp):
        return Ok(42)

    result = test_getter_func(None, None)
    assert result.is_ok()
    assert result.unwrap() == 42
