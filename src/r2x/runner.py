"""Umbrella API for R2X model."""

import inspect
import sys
import shutil
from importlib.resources import files
from pathlib import Path


from loguru import logger

from r2x.exporter.handler import get_exporter
from r2x.plugin_manager import PluginManager

from .api import System
from .config_scenario import Scenario, get_scenario_configuration
from .parser.handler import BaseParser, get_parser_data
from .upgrader import upgrade_handler

from collections.abc import Callable
from typing import TYPE_CHECKING, ParamSpec

if TYPE_CHECKING:
    from polars import DataFrame

pm = PluginManager()


def run_parser(config: Scenario, **kwargs):
    """Call get parser for parser selected.

    The parser gets selected based on `config.input_model`.

    Parameters
    ----------
    config
        Scenario
    upgrader
        Function to upgrade the inputs

    Other Parameters
    ----------------
    kwargs
        Additional key arguments to the parser.

    Raises
    ------
    KeyError
        If parser is not found on parser_list
    """
    # At some point we will read the ReEDS tag and upgrade accordingly.
    # reeds_meta = get_file(fname="meta.csv", config=config).iloc[:1]
    assert config.run_folder
    assert config.input_model
    if getattr(config, "upgrade", None):
        upgrade_handler(config.run_folder)

    plugin = pm.get_plugin(config.input_model)

    parser_class = plugin.parser
    parser_filters = plugin.parser_filters

    filter_funcs: list[Callable[[DataFrame, ParamSpec], DataFrame]] | None = None
    if parser_filters is not None:
        filter_funcs = []
        for filter_func in parser_filters:
            if type(filter_func) is str:
                filter_func_call = pm.get_filter(str(filter_func))
            elif callable(filter_func):
                filter_func_call = filter_func
            else:
                raise TypeError(f"Filter function must be a string or callable, not {type(filter_func)}")
            filter_funcs.append(filter_func_call)

    if not parser_class:
        raise KeyError(f"Parser for {config.input_model} not found")

    parser = get_parser_data(config, parser_class, filter_funcs=filter_funcs, **kwargs)
    system = parser.build_system()

    assert system is not None, "System failed to create"

    return system, parser


def run_plugins(config: Scenario, parser: BaseParser, system: System) -> System:
    """Run selected system modifiers.

    Parameters
    ----------
    config
        Configuration manager
    system
        System

    Returns
    -------
        System
    """
    if not config.plugins:
        return system

    logger.info("Running the following plugins: {}", config.plugins)
    for sysmod_name in config.plugins:
        # Load the system modifier function
        sysmod_func = pm.get_system_modifier(sysmod_name)
        # Inspect the system modifier function for arguments
        sysmod_required_args = inspect.getfullargspec(sysmod_func).args
        # Lookup the required arguments in the config
        sysmod_config_args = {
            key: value for key, value in config.__dict__.items() if key in sysmod_required_args
        }

        # update the system
        system = sysmod_func(config=config, system=system, parser=parser, **sysmod_config_args)

    return system


def run_exporter(config: Scenario, system: System) -> None:
    """Create exporter model."""
    assert config.output_model
    exporter_class = pm.load_exporter(config.output_model)
    if not exporter_class:
        raise KeyError(f"Exporter for {config.output_model} not found")

    get_exporter(config, system, exporter_class)


def run_single_scenario(scenario: Scenario, **kwargs) -> None:
    """Run translation process."""
    logger.info("Running {}", scenario.name)

    if scenario.input_model == "infrasys":
        fname = f"{scenario.run_folder}/{scenario.name}.json"
        system = System.from_json(filename=fname, **kwargs)
    else:
        system, parser = run_parser(scenario, **kwargs)
        system = run_plugins(config=scenario, parser=parser, system=system)

    if getattr(scenario, "inspect", None):
        from IPython import embed

        embed()
        sys.exit(0)

    # Serialize/deserialize the system
    output_fpath = str(scenario.output_folder) + f"/{scenario.name}.json"
    if getattr(scenario, "save", None):
        logger.info("Serialize system to {}", output_fpath)
        system.to_json(output_fpath, overwrite=True)
        system = System.from_json(output_fpath)

    if scenario.output_model == "infrasys":
        logger.info("Serialize system to {}", output_fpath)
        system.to_json(output_fpath, overwrite=True)
        return
    run_exporter(config=scenario, system=system)
    return


def run(cli_args: dict, user_dict: dict | None = None) -> None:
    """Run a translation.

    This function takes the `cli_args` dictionary to create the configuratio and run the translation process.
    If the user specifies multiple scenarios, this function run the translation sequentially with
    no specific order.

    Parameters
    ----------
    cli_args
        Arguments for constructing the scenario.
    user_dict
        Optional, User custom configuration.

    See Also
    --------
        get_config: Get configuration from arguments
        run_single_scenario: Run a single translation scenario

    Notes
    -----
    Currently the scenario should only have a single year to run.
    """
    config_mgr = get_scenario_configuration(cli_args=cli_args, user_dict=user_dict)
    logger.info("Running {} scenarios", len(config_mgr))
    for _, scenario in config_mgr.scenarios.items():
        # NOTE: We can pass multiple years from the CLI. In those cases we want to raise not implemented.
        if hasattr(scenario, "input_config") and isinstance(
            getattr(scenario.input_config, "solve_year", None), list
        ):
            msg = "Multi year runs from the CLI is not yet supported. Use scenarios instead."
            raise NotImplementedError(msg)
        run_single_scenario(scenario)
    return


def init(cli_args: dict) -> None:
    """Copy the default configuration file on the path that the user request.

    If the user does not provide a path, the current path is used.

    Parameters
    ----------
    cli_args
        Arguments from the CLI
    """
    logger.debug("Running init command")
    path = Path(cli_args["path"])

    with files("r2x.defaults") as package_path:  # type: ignore
        file_path = package_path / "user_dict.yaml"
        shutil.copy(file_path, Path(path) / "user_dict.yaml")
    return



def create_plugin_template(plugin_name: str, plugin_path: str) -> None:
    """Generate a new plugin using the Cookiecutter template.

    Args:
        plugin_name: Name of the plugin to create (e.g., "myplugin")
        path: Directory where to create the plugin
    """
    try:
        from cookiecutter.main import cookiecutter
    except ImportError:
        raise ImportError("Cookiecutter is not installed. Please install using 'pip install cookiecutter'.")

    logger.info(f"Creating plugin {plugin_name} in directory {plugin_path}")

    # Path to the template directory
    template_path = Path(__file__).parent / "templates" / "plugin"

    if not template_path.exists():
        raise RuntimeError(
            f"Template directory not found at {template_path}. "
            "Please ensure the template is installed."
        )

    # Run Cookiecutter
    cookiecutter(
        str(template_path.resolve()),
        extra_context={"plugin_name": plugin_name},
        no_input=True,
        output_dir=plugin_path,
        overwrite_if_exists=False,
    )

    plugin_dir = Path(plugin_path) / f"{plugin_name}"
    print(f"Successfully created plugin at {plugin_dir}")
