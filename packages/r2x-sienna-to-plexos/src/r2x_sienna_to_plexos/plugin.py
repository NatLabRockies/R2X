"""R2X plugin entry point for the Sienna to Plexos package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from r2x_core import PluginManifest


def register_plugin() -> PluginManifest:
    """Return the Sienna to Plexos plugin manifest for discovery."""
    from r2x_core import PluginManifest

    manifest = PluginManifest(package="r2x_sienna_to_plexos")
    # manifest.add(
    #     PluginSpec.function(
    #         name="sienna-to-plexos",
    #         entry=sienna_to_plexos,
    #         description="Translate a Sienna system into PLEXOS data using the packaged rule set.",
    #     )
    # )
    return manifest
