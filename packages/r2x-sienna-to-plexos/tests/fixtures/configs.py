from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from r2x_sienna_to_plexos import SiennaToPlexosConfig


@pytest.fixture
def config_empty() -> "SiennaToPlexosConfig":
    """Empty configuration with default settings.

    Returns
    -------
    SiennaToPlexosConfig
        Configuration with no active versions specified (defaults to version 1)
    """
    from r2x_sienna_to_plexos.plugin_config import SiennaToPlexosConfig

    return SiennaToPlexosConfig(models=["r2x_sienna.models", "r2x_plexos.models"])
