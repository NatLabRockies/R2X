"""Entry point for plugin system."""

from r2x_core import PluginManifest, PluginSpec

from .translation import perform_translation

manifest = PluginManifest(package="r2x-plexos-to-sienna")

manifest.add(
    PluginSpec.translation(
        name="r2x_plexos_to_sienna.translation",
        entry=perform_translation,
        description="Translate Plexos system to Sienna system.",
    )
)
