"""R2X plugin entry point for the Sienna to Plexos package."""

from r2x_core import PluginManifest, PluginSpec

from .translation import perform_translation

manifest = PluginManifest(package="r2x-sienna-to-plexos")

manifest.add(
    PluginSpec.translation(
        name="r2x_sienna_to_plexos.translation",
        entry=perform_translation,
        description="Translate Sienna system to PLEXOS system.",
    )
)
