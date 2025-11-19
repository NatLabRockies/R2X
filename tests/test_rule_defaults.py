import pytest


@pytest.mark.parametrize(
    "defaults,expected",
    [
        ({}, {}),
        ({"field": "default"}, {"field": "default"}),
        ({"f1": 1, "f2": "default"}, {"f1": 1, "f2": "default"}),
    ],
    ids=["no_defaults", "single_default", "multiple_defaults"],
)
def test_defaults_are_optional(defaults, expected):
    """Defaults are optional and default to empty dict."""
    from r2x_sienna_to_plexos import Rule

    rule = Rule(
        source_type="A",
        target_type="B",
        version=1,
        field_map={"f": "f"},
        defaults=defaults,
    )

    assert rule.defaults == expected
