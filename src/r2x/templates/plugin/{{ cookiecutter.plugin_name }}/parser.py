from r2x.plugin_manager import PluginManager

from argparse import ArgumentParser


@PluginManager.register_cli("parser", "{{ cookiecutter.plugin_name }}Parser")
def cli_arguments(parser: ArgumentParser):
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--weather-year",
        type=int,
        dest="weather_year",
        help="Custom weather year argument",
    )
