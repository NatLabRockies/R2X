import pytest


def test_context_creation(context):
    """Create context and verify all required fields are present."""
    ctx = context

    assert ctx.source_system is not None
    assert ctx.target_system is not None
    assert ctx.config is not None
    assert len(ctx.rules) > 0


def test_context_with_empty_rules(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
):
    """Create context with empty rules list."""

    from r2x_sienna_to_plexos import TranslationContext

    ctx = TranslationContext(
        source_system=sienna_system_empty,
        target_system=plexos_system_empty,
        config=config_empty,
        rules=[],
    )

    assert len(ctx.rules) == 0
    assert ctx.source_system is sienna_system_empty
    assert ctx.target_system is plexos_system_empty


def test_context_rejects_duplicate_rules(
    sienna_system_empty,
    plexos_system_empty,
    config_empty,
):
    """Creating context with duplicate rule keys raises ValueError."""
    from r2x_sienna_to_plexos import Rule, TranslationContext

    rule1 = Rule(
        source_type="Bus",
        target_type="Node",
        version=1,
        field_map={"name": "name"},
    )
    rule2 = Rule(
        source_type="Bus",
        target_type="Node",
        version=1,
        field_map={"name": "name", "extra": "extra"},
    )
    with pytest.raises(ValueError, match="Duplicate rule key"):
        TranslationContext(
            source_system=sienna_system_empty,
            target_system=plexos_system_empty,
            config=config_empty,
            rules=[rule1, rule2],
        )


def test_context_is_frozen(context):
    """Verify context is frozen (immutable)."""
    with pytest.raises(AttributeError):
        context.rules = []


def test_context_sienna_system_immutable(context):
    """Verify sienna_system cannot be modified."""
    with pytest.raises(AttributeError):
        context.sienna_system = None


def test_context_config_immutable(context):
    """Verify config cannot be modified."""
    with pytest.raises(AttributeError):
        context.config = None
