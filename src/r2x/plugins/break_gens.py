"""Plugin to dissaggregate and aggregate generators.

This plugin breaks apart generators that are to big in conmparisson with the
WECC database. If the generator is to small after the breakup than the capacity
threshold variable, we drop the genrator entirely.
"""

from __future__ import annotations

# System packages
import re
from argparse import ArgumentParser, _ArgumentGroup
from typing import Any

import numpy as np
import pandas as pd
from infrasys.base_quantity import BaseQuantity

# Local imports
from loguru import logger

from r2x.api import System
from r2x.config_scenario import Scenario
from r2x.models import Emission, Generator
from r2x.models.named_tuples import MinMax
from r2x.parser.handler import BaseParser
from r2x.plugin_manager import PluginManager
from r2x.units import ActivePower, ureg
from r2x.utils import read_json

# Constants
CAPACITY_THRESHOLD = 5  # MW
PROPERTIES_TO_BREAK = [
    "ramp_up",
    "ramp_down",
    "min_rated_capacity",
    "startup_cost",
    "pump_load",
    "storage_capacity",
    "active_power_limits",
    "output_active_power_limits",
    "input_active_power_limits",
]


@PluginManager.register_cli("system_update", "break_gens")
def cli_arguments(parser: ArgumentParser | _ArgumentGroup):
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--capacity-threshold",
        type=int,
        help="Capacity threshold for aggregating generators.",
        default=CAPACITY_THRESHOLD,
    )


@PluginManager.register_system_update("break_gens")
def update_system(
    config: Scenario,
    system: System,
    parser: BaseParser,
    pcm_defaults_fpath: str | None = None,
    capacity_threshold: int = CAPACITY_THRESHOLD,
) -> System:
    """Break apart large generators based on average capacity.

    This function updates and overrides the data objects from the translator to
    be passed to the exporter.

    Args:
        translator: r2x.Translator object,
        *args: additional arguments that can be passed,
        **kwargs: additiona arguments.
    """
    logger.info("Dividing generators into average size generators")
    assert config.input_config
    if pcm_defaults_fpath is None:
        logger.debug("Using {}", config.input_config.defaults["pcm_defaults_fpath"])
        pcm_defaults = read_json(config.input_config.defaults["pcm_defaults_fpath"])
    else:
        logger.debug("Using custom defaults from {}", pcm_defaults_fpath)
        pcm_defaults: dict = read_json(pcm_defaults_fpath)

    reference_generators = (
        pd.DataFrame.from_dict(pcm_defaults)
        .transpose()
        .reset_index()
        .rename(
            columns={
                "index": "tech",
            }
        )
        .set_index("tech")
        .replace({np.nan: None})
        .to_dict(orient="index")
    )
    non_break_techs = config.input_config.defaults.get("non_break_techs", [])

    return break_generators(system, reference_generators, capacity_threshold, non_break_techs)


def break_generators(  # noqa: C901
    system: System,
    reference_generators: dict[str, dict],
    capacity_threshold: int = CAPACITY_THRESHOLD,
    non_break_techs: list[str] | None = None,
    break_category: str = "category",
) -> System:
    """Break component generator into smaller units."""
    if non_break_techs:
        regex_pattern = f"^(?!{'|'.join(non_break_techs)})."  # Oh yes.
    else:
        regex_pattern = ".*"

    capacity_dropped = 0  # count capacity dropped
    for component in system.get_components(Generator, filter_func=lambda x: re.search(regex_pattern, x.name)):
        if not (tech := getattr(component, break_category, None)):
            logger.trace("Skipping component {} with missing category", component.label)
            continue
        logger.trace("Breaking {}", component.label)

        if not (reference_tech := reference_generators.get(tech)):
            logger.trace("{} not found in reference_generators", tech)
            continue
        if not (avg_capacity := reference_tech.get("avg_capacity_MW", None)):
            continue
        logger.trace("Average_capacity: {}", avg_capacity)
        reference_base_power = (
            component.active_power.magnitude
            if isinstance(component.active_power, BaseQuantity)
            else component.active_power
        )
        no_splits = int(reference_base_power // avg_capacity)
        remainder = reference_base_power % avg_capacity

        # If there is not splits, we skip the generator
        if no_splits <= 1:
            continue
        split_no = 1
        logger.trace(
            "Breaking generator {} with active_power {} into {} generators of {} capacity",
            component.name,
            reference_base_power,
            no_splits,
            avg_capacity,
        )
        for _ in range(no_splits):
            component_name = component.name + f"_{split_no:02}"
            new_component = system.copy_component(component, name=component_name, attach=True)
            new_base_power = (
                ActivePower(avg_capacity, component.active_power.units)
                if isinstance(component.active_power, BaseQuantity)
                else avg_capacity * ureg.MW
            )
            new_component.active_power = new_base_power
            proportion = (
                avg_capacity / reference_base_power
            )  # Required to recalculate properties that depend on active_power
            for property in PROPERTIES_TO_BREAK:
                if attr := getattr(new_component, property, None):
                    new_component.ext[f"{property}_original"] = attr
                    property_value = _apply_new_value(attr, proportion)
                    setattr(new_component, property, property_value)
            new_component.ext["original_capacity"] = component.active_power
            new_component.ext["original_name"] = component.name
            new_component.ext["broken"] = True

            for attribute in system.get_supplemental_attributes_with_component(component, Emission):
                system.add_supplemental_attribute(new_component, attribute)
            if system.has_time_series(component):
                logger.trace(
                    "Component {} has time series attached to it. Copying first one", component.label
                )
                ts = system.get_time_series(component)
                system.add_time_series(ts, new_component)
            split_no += 1

        if remainder > capacity_threshold:
            component_name = component.name + f"_{split_no:02}"
            new_component = system.copy_component(component, name=component_name, attach=True)
            new_component.active_power = remainder * ureg.MW
            proportion = (
                remainder / reference_base_power
            )  # Required to recalculate properties that depend on active_power
            for property in PROPERTIES_TO_BREAK:
                if attr := getattr(new_component, property, None):
                    new_component.ext[f"{property}_original"] = attr
                    property_value = _apply_new_value(attr, proportion)
                    setattr(new_component, property, property_value)
            new_component.ext["original_capacity"] = component.active_power
            new_component.ext["original_name"] = component.name
            new_component.ext["broken"] = True
            for attribute in system.get_supplemental_attributes_with_component(component, Emission):
                system.add_supplemental_attribute(new_component, attribute)

            if system.has_time_series(component):
                logger.trace(
                    "Component {} has time series attached to it. Copying first one", component.label
                )
                ts = system.get_time_series(component)
                system.add_time_series(ts, new_component)
        else:
            capacity_dropped = capacity_dropped + remainder
            logger.debug("Dropped {} capacity for {}", remainder, component.name)

        # Finally remove the component and emissions from original component
        system.remove_component(component)
        for attribute in system.get_supplemental_attributes_with_component(component):
            system.remove_supplemental_attribute_from_component(component, attribute)

    logger.info("Total capacity dropped {} MW", capacity_dropped)
    return system


def _apply_new_value(attr: Any, proportion: float):
    if isinstance(attr, MinMax):
        return MinMax(min=attr.min * proportion, max=attr.max * proportion)
    return attr * proportion
