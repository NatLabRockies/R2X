"""Entry point for plugin system."""

from r2x_core import PluginManifest, PluginSpec

from .plugin_config import ReedsToPlexosConfig
from .translation import ReedsToPlexosTranslation

manifest = PluginManifest(package="r2x-reeds-to-plexos")

manifest.add(
    PluginSpec.translation(
        name="r2x-reeds-to-plexos.translation",
        entry=ReedsToPlexosTranslation,
        config=ReedsToPlexosConfig,
        description="Translate ReEDS system to Plexos system.",
    )
)
