"""Validation and persistence of the missing-ramp translation policy."""

import pytest
from pydantic import ValidationError
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig


def test_missing_ramp_default_is_one_fraction_per_minute():
    assert ReedsToPlexosConfig().missing_ramp_rate_fraction_per_minute == 1.0


@pytest.mark.parametrize("value", [None, 0.0, 0.2, 1.0, 3.0])
def test_missing_ramp_configuration_round_trip(value):
    config = ReedsToPlexosConfig(missing_ramp_rate_fraction_per_minute=value)

    assert config.missing_ramp_rate_fraction_per_minute == value
    assert config.model_dump()["missing_ramp_rate_fraction_per_minute"] == value
    restored = ReedsToPlexosConfig.model_validate_json(config.model_dump_json())
    assert restored.missing_ramp_rate_fraction_per_minute == value


@pytest.mark.parametrize("value", [True, False, -0.1, float("nan"), float("inf"), -float("inf"), "invalid"])
def test_invalid_missing_ramp_configuration_is_rejected(value):
    with pytest.raises(ValidationError, match="missing_ramp_rate_fraction_per_minute"):
        ReedsToPlexosConfig(missing_ramp_rate_fraction_per_minute=value)
