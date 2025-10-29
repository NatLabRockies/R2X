"""Plugin to dissaggregate and aggregate generators.

This plugin breaks apart generators that are to big in conmparisson with the
WECC database. If the generator is to small after the breakup than the capacity
threshold variable, we drop the genrator entirely.
"""

# System packages
import re
from argparse import ArgumentParser
import random

import numpy as np
import pandas as pd
from infrasys.base_quantity import BaseQuantity

# Local imports
from loguru import logger

from r2x.api import System
from r2x.config_scenario import Scenario
from r2x.models import Emission, Generator
from r2x.parser.handler import BaseParser
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
]
PROPERTIES_TO_PERTURB = [
    "planned_outage_rate",
    "forced_outage_rate",
    "mean_time_to_repair",
    "emissions",
    "startup_cost",
    "shutdown_cost"
]

def perturb(value, perturb_factor):
    return round(value * perturb_factor, 3)


def cli_arguments(parser: ArgumentParser):
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--capacity-threshold",
        type=int,
        help="Capacity threshold for aggregating generators.",
        default=CAPACITY_THRESHOLD,
    )


def update_system(
    config: Scenario,
    parser: BaseParser,
    system: System,
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

    reference_generators_old = (
        pd.concat({
            k: pd.DataFrame(v).transpose()
            for k,v
            in pcm_defaults['old'].items()
        }, axis=0)
        .replace({np.nan: None})
        .to_dict(orient="index")
    )
    reference_generators_new = (
        pd.concat({
            k: pd.DataFrame(v).transpose()
            for k,v
            in pcm_defaults['new'].items()
        }, axis=0)
        .replace({np.nan: None})
        .to_dict(orient="index")
    )
    break_categories = ['region', 'category']
    non_break_techs = config.input_config.defaults.get("non_break_techs", [])

    return break_generators(
        system,
        reference_generators_old,
        reference_generators_new,
        capacity_threshold,
        non_break_techs,
        break_categories
    )


def break_generators(  # noqa: C901
    system: System,
    reference_generators_old: dict[str, dict],
    reference_generators_new: dict[str, dict],
    capacity_threshold: int = CAPACITY_THRESHOLD,
    non_break_techs: list[str] | None = None,
    break_categories: list[str] = ["category"],
) -> System:
    """Break component generator into smaller units."""
    if non_break_techs:
        regex_pattern = f"^(?!{'|'.join(non_break_techs)})."  # Oh yes.
    else:
        regex_pattern = ".*"

    capacity_dropped = 0  # count capacity dropped
    for component in system.get_components(Generator, filter_func=lambda x: re.search(regex_pattern, x.name)):
        if 'init' in component.ext['reeds_vintage']:
            reference_generators = reference_generators_old
        else:
            reference_generators = reference_generators_new

        if not (tech := getattr(component, 'category', None)):
            logger.trace("Skipping component {} with missing category", component.label)
            continue
    
        region = getattr(getattr(component, "bus"), "name")
        if not (reference_generator := reference_generators.get((region, tech))):
            logger.trace("region {} / tech {} not found in reference_generators", region, tech)
            continue

        logger.trace("Breaking {}", component.label)

        if not (avg_capacity := reference_generator.get("avg_capacity_MW", None)):
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

        if type(component).__name__ in ["EnergyReservoirStorage"]:
            perturb_factor = random.uniform(0.98, 1.02)
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
                    setattr(new_component, property, attr * proportion)
            for property in PROPERTIES_TO_PERTURB:
                if attr := getattr(new_component, property, None):
                    new_component.ext[f"{property}_original"] = attr
                    if isinstance(attr, float):
                        new_attr = perturb(attr, perturb_factor)
                    else:
                        new_attr = perturb(attr.copy(), perturb_factor)
                    setattr(
                        new_component,
                        property,
                        new_attr
                    )
            new_component.ext["original_capacity"] = component.active_power
            new_component.ext["original_name"] = component.name
            new_component.ext["broken"] = True
            new_component.available = no_splits

            for attribute in system.get_supplemental_attributes_with_component(component, Emission):
                new_attribute = attribute.model_copy()
                if "emissions" in PROPERTIES_TO_PERTURB:
                    new_attribute.rate = perturb(new_attribute.rate, perturb_factor)
                system.add_supplemental_attribute(new_component, new_attribute)
            if system.has_time_series(component):
                logger.trace(
                    "Component {} has time series attached to it. Copying first one", component.label
                )
                ts = system.get_time_series(component)
                system.add_time_series(ts, new_component)
            split_no += 1
        else:
            for _ in range(no_splits):
                perturb_factor = random.uniform(0.98, 1.02)
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
                        setattr(new_component, property, attr * proportion)
                for property in PROPERTIES_TO_PERTURB:
                    if attr := getattr(new_component, property, None):
                        new_component.ext[f"{property}_original"] = attr
                        if isinstance(attr, float):
                            new_attr = perturb(attr, perturb_factor)
                        else:
                            new_attr = perturb(attr.copy(), perturb_factor)
                        setattr(
                            new_component,
                            property,
                            new_attr
                        )
                new_component.ext["original_capacity"] = component.active_power
                new_component.ext["original_name"] = component.name
                new_component.ext["broken"] = True

                for attribute in system.get_supplemental_attributes_with_component(component, Emission):
                    new_attribute = attribute.model_copy()
                    if "emissions" in PROPERTIES_TO_PERTURB:
                        new_attribute.rate = perturb(new_attribute.rate, perturb_factor)
                    system.add_supplemental_attribute(new_component, new_attribute)
                if system.has_time_series(component):
                    logger.trace(
                        "Component {} has time series attached to it. Copying first one", component.label
                    )
                    ts = system.get_time_series(component)
                    system.add_time_series(ts, new_component)
                split_no += 1

        if remainder > capacity_threshold:
            perturb_factor = random.uniform(0.98, 1.02)
            component_name = component.name + f"_{split_no:02}"
            new_component = system.copy_component(component, name=component_name, attach=True)
            new_component.active_power = remainder * ureg.MW
            proportion = (
                remainder / reference_base_power
            )  # Required to recalculate properties that depend on active_power
            for property in PROPERTIES_TO_BREAK:
                if attr := getattr(new_component, property, None):
                    new_component.ext[f"{property}_original"] = attr
                    setattr(new_component, property, attr * proportion)
            for property in PROPERTIES_TO_PERTURB:
                if attr := getattr(new_component, property, None):
                    new_component.ext[f"{property}_original"] = attr
                    if isinstance(attr, float):
                        new_attr = perturb(attr, perturb_factor)
                    else:
                        new_attr = perturb(attr.copy(), perturb_factor)
                    setattr(
                        new_component,
                        property,
                        new_attr
                    )
            new_component.ext["original_capacity"] = component.active_power
            new_component.ext["original_name"] = component.name
            new_component.ext["broken"] = True

            for attribute in system.get_supplemental_attributes_with_component(component, Emission):
                new_attribute = attribute.model_copy()
                if "emissions" in PROPERTIES_TO_PERTURB:
                    new_attribute.rate = perturb(new_attribute.rate, perturb_factor)
                system.add_supplemental_attribute(new_component, new_attribute)
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
