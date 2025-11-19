def test_rule_equality_by_metadata():
    """Rules are equal if they have same source_type, target_type, and version."""
    from r2x_core import Rule

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
        field_map={"name": "name", "extra": "extra"},  # Different field_map
    )
    # Should be equal because metadata is the same
    assert rule1 == rule2


def test_rule_inequality_different_version():
    """Rules are not equal if versions differ."""
    from r2x_core import Rule

    rule1 = Rule(
        source_type="Bus",
        target_type="Node",
        version=1,
        field_map={"name": "name"},
    )
    rule2 = Rule(
        source_type="Bus",
        target_type="Node",
        version=2,
        field_map={"name": "name"},
    )
    assert rule1 != rule2


def test_rule_hashable():
    """Rules can be used in sets based on their metadata."""
    from r2x_core import Rule

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
        field_map={"name": "name"},
    )
    rule_set = {rule1, rule2}
    # Both should hash the same, so set has only 1 element
    assert len(rule_set) == 1
