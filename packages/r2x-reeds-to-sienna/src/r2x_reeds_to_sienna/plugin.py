"""Entry point for plugin system."""

from r2x_core import PluginManifest, PluginSpec

from .translation import perform_translation

manifest = PluginManifest(package="r2x-reeds-to-sienna")

manifest.add(
    PluginSpec.translation(
        name="r2x_reeds_to_sienna.translation",
        entry=perform_translation,
        description="Translate ReEDS system to Sienna system.",
    )
)
