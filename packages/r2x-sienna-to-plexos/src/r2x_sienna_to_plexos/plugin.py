"""R2X plugin entry point for Sienna to Plexos package."""

from r2x_core.package import Package


def register_plugin() -> Package:
    """Return the Sienna to Plexos plugin package for R2X framework discovery."""

    from r2x_core.plugin import BasePlugin, IOType
    from r2x_sienna_to_plexos.sienna_to_plexos import sienna_to_plexos

    return Package(
        name="r2x-sienna-to-plexos",
        plugins=[
            BasePlugin(
                name="sienna-to-plexos",
                obj=sienna_to_plexos,
                io_type=IOType.BOTH,
            ),
        ],
    )
