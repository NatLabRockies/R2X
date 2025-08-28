from r2x.config_scenario import Scenario
from r2x.parser.handler import BaseParser
from argparse import ArgumentParser
from r2x.api import System
from r2x.plugin_manager import PluginManager


@PluginManager.register_cli("system_update", "{{ cookiecutter.plugin_name }}_system_update")
def cli_arguments(parser: ArgumentParser):
    """CLI arguments for system update."""
    parser.add_argument(
        "--custom-flag",
        action="store_true",
        help="Custom flag for testing",
    )


@PluginManager.register_system_update("{{ cookiecutter.plugin_name }}_system_update")
def update_system(
    config: Scenario,
    system: System,
    parser: BaseParser | None = None,
    custom_flag: bool = False,
) -> System:
    """System update function for {{ cookiecutter.plugin_name }}."""

    return system
