"""Augment results from CEM with PCM defaults."""

from argparse import ArgumentParser, _ArgumentGroup
from operator import attrgetter

from loguru import logger

from r2x.api import System
from r2x.config_scenario import Scenario
from r2x.models import Generator
from r2x.parser.handler import BaseParser
from r2x.plugin_manager import PluginManager
from r2x.units import get_magnitude
from r2x.utils import read_json


@PluginManager.register_cli("system_update", "pcm_defaults")
def cli_arguments(parser: ArgumentParser | _ArgumentGroup):
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--pcm-defaults-fpath",
        help="File containing the defaults",
    )
    parser.add_argument(
        "--pcm-defaults-override",
        action="store_true",
        help="Override all PCM default properties.",
    )


@PluginManager.register_system_update("pcm_defaults")
def update_system(
    config: Scenario,
    parser: BaseParser | None,
    system: System,
    pcm_defaults_fpath: str | None = None,
    pcm_defaults_override: bool = False,
) -> System:
    """Augment data model using PCM defaults dictionary.

    Parameters
    ----------
    config
        Scenario configuration class
    system
        InfraSys system
    pcm_defaults_path
        Path for json file containing the PCM defaults.
    pcm_defaults_override: bool. Default False.
        Flag to override all the PCM related fields with the JSON values.

    Returns
    -------
        System

    Notes
    -----
    The current implementation of this plugin matches the :class:`Component` category field
    """
    logger.info("Augmenting generators attributes with PCM defaults.")
    assert config.input_config
    pcm_defaults_fpath = pcm_defaults_fpath or config.input_config.defaults["pcm_defaults_fpath"]
    assert pcm_defaults_fpath
    logger.debug("Using {}", pcm_defaults_fpath)
    pcm_defaults: dict = read_json(pcm_defaults_fpath)

    needs_multiplication = {"start_cost_per_MW", "ramp_limits"}

    # We first override the fields that are required for `needs_multiplication` to work correctly.
    fields_weight = {"active_power_limits": 1}

    # NOTE: Matching names provides the order that we do the mapping for. First
    # we try to find the name of the generator, if not we rely on reeds category
    # category and finally if we did not find a match the broader category
    for component in system.get_components(Generator):
        pcm_values = (
            pcm_defaults.get(component.name)
            or pcm_defaults.get(attrgetter("ext.reeds_tech"))
            or pcm_defaults.get(component.category)
        )
        if not pcm_values:
            msg = "Could not find a matching category for {}. "
            msg += "Skipping generator from pcm_defaults plugin."
            logger.debug(msg, component.label)
            continue

        msg = "Applying PCM defaults to {}"
        logger.debug(msg, component.label)
        fields_to_replace = (
            [
                key
                for key, value in component.model_dump().items()
                if value is None
                if key in pcm_values.keys()
            ]
            if not pcm_defaults_override
            else [key for key in pcm_values.keys() if key in type(component).model_fields]
        )
        for field in sorted(
            fields_to_replace, key=lambda x: fields_weight[x] if x in fields_weight else -999
        ):
            value = pcm_values[field]
            if _check_if_null(value):
                continue
            if field in needs_multiplication:
                value = _multiply_value(get_magnitude(component.base_power or component.active_power), value)
            # NOTE: We need to move this to the operation cost instead.
            if field == "start_cost_per_MW":
                field = "startup_cost"
            setattr(component, field, value)
    return system


def _multiply_value(base, val):
    if isinstance(val, dict):
        return {k: base * v for k, v in val.items()}
    return base * val


def _check_if_null(val):
    if isinstance(val, dict):
        return all(not v for v in val.values())
    return val is None
