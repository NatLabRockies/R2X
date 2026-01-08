"""Entry point for plugin system."""

from r2x_core import PluginManifest, PluginSpec

from .plugin_config import PlexosToSiennaConfig
from .translation import PlexosToSiennaTranslation

manifest = PluginManifest(package="r2x-plexos-to-sienna")

manifest.add(
    PluginSpec.translation(
        name="r2x-plexos-to-sienna.translation",
        entry=PlexosToSiennaTranslation,
        config=PlexosToSiennaConfig,
        method="run",
        description="Translate Plexos system to Sienna system.",
    )
)
