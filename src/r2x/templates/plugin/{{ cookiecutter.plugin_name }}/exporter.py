from r2x.plugin_manager import PluginManager

from argparse import ArgumentParser
from r2x.config_models import PlexosConfig


@PluginManager.register_cli("exporter", "{{ cookiecutter.plugin_name }}Exporter")
def cli_arguments(parser: ArgumentParser):
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--master-file",
        required=False,
        help="Custom master file argument",
    )
