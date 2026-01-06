"""Entry point for plugin system."""

from r2x_core import PluginManifest, PluginSpec

from .translation import ReedsToSiennaTranslation

manifest = PluginManifest(package="r2x-reeds-to-sienna")

manifest.add(
    PluginSpec.translation(
        name="r2x-reeds-to-sienna.translation",
        entry=ReedsToSiennaTranslation,
        description="Translate ReEDS system to Sienna system.",
    )
)
