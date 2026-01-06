"""R2X plugin entry point for the Sienna to Plexos package."""

from r2x_core import PluginManifest, PluginSpec

from .config import SiennaToPlexosConfig
from .translation import SiennaToPlexosTranslation

manifest = PluginManifest(package="r2x-sienna-to-plexos")

manifest.add(
    PluginSpec.translation(
        name="r2x-sienna-to-plexos.translation",
        entry=SiennaToPlexosTranslation,
        config=SiennaToPlexosConfig,
        description="Translate Sienna system to PLEXOS system.",
    )
)
