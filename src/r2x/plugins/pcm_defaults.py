"""Augment results from CEM with PCM defaults."""

from argparse import ArgumentParser

from infrasys.base_quantity import BaseQuantity
import pandas as pd
from loguru import logger

from r2x.models import Generator
from r2x.api import System
from r2x.config_scenario import Scenario
from r2x.parser.handler import BaseParser
from r2x.units import ActivePower
from r2x.utils import read_json


def cli_arguments(parser: ArgumentParser):
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--pcm-defaults-fpath",
        help="File containing the defaults",
    )


def update_system(
    config: Scenario, parser: BaseParser, system: System, pcm_defaults_fpath: str | None = None
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

    Returns
    -------
        System
    """
    logger.info("Augmenting generators attributes")
    assert config.input_config
    if pcm_defaults_fpath is None:
        logger.debug("Using {}", config.input_config.defaults["pcm_defaults_fpath"])
        pcm_defaults = read_json(config.input_config.defaults["pcm_defaults_fpath"])
    else:
        logger.debug("Using custom defaults from {}", pcm_defaults_fpath)
        pcm_defaults: dict = read_json(pcm_defaults_fpath)

    reference_data_old = (
        pd.concat({
            k: pd.DataFrame(v).transpose()
            for k,v
            in pcm_defaults['old'].items()
        }, axis=0)
    )
    reference_data_new = (
        pd.concat({
            k: pd.DataFrame(v).transpose()
            for k,v
            in pcm_defaults['new'].items()
        }, axis=0)
    )

    for reference_data in [reference_data_old, reference_data_new]:
        # Rename columns on the file itself and remove this
        reference_data = reference_data.loc[
            :,
            [
                "min_stable_level_percentage",
                "start_cost_per_MW",
                "shutdown_cost_per_MW",
                "max_ramp_up_percentage",
                "run_up_rate",
                "mean_time_to_repair",
                "min_down_time",
                "min_up_time",
                "maintenance_rate",
                "forced_outage_rate",
                "fom_cost",
                "heat_rate",
                "vom_cost"
            ],
        ]
        dtypes = {
            "min_stable_level_percentage": "float",
            "start_cost_per_MW": "float",
            "shutdown_cost_per_MW": "float",
            "max_ramp_up_percentage": "float",
            "run_up_rate": "float",
            "mean_time_to_repair": "float",
            "min_down_time": "float",
            "min_up_time": "float",
            "maintenance_rate": "float",
            "forced_outage_rate": "float",
            "fom_cost": "float",
            "heat_rate": "float",
            "vom_cost": "float"
        }
        reference_data = reference_data.astype(dtypes)

        reference_categories = reference_data.index.unique()

    for component in system.get_components(Generator):
        if 'init' in component.ext['reeds_vintage']:
            reference_data = reference_data_old
        else:
            reference_data = reference_data_new

        reeds_tech = getattr(component, "ext").get("reeds_tech")
        if isinstance(reference_categories[0], str):
            if reeds_tech not in reference_categories:
                continue
            wecc_data_row = (
                reference_data.loc[reference_data.index.str.startswith(reeds_tech)]
                .dropna(axis=1)
                .to_dict(orient="records")[0]
            )
        else:
            reeds_region = getattr(getattr(component, "bus"), "name")
            reeds_region_tech = (reeds_region, reeds_tech)
            if reeds_region_tech not in reference_categories:
                continue
            wecc_data_row = (
                reference_data.loc[reference_data.index == reeds_region_tech]
                .dropna(axis=1)
                .to_dict(orient="records")[0]
            )

        
        values_to_add = {}

        # I do not like this implementation.
        values_to_add["planned_outage_rate"] = (
            BaseQuantity(wecc_data_row.get("maintenance_rate"), "%")
            if wecc_data_row.get("maintenance_rate")
            else getattr(component, "planned_outage_rate", None)
        )
        values_to_add["forced_outage_rate"] = (
            BaseQuantity(wecc_data_row.get("forced_outage_rate"), "%")
            if wecc_data_row.get("forced_outage_rate")
            else getattr(component, "forced_outage_rate", None)
        )
        values_to_add["ramp_up"] = (
            getattr(component, "active_power")
            * BaseQuantity(wecc_data_row.get("max_ramp_up_percentage"), "1/min")
            if wecc_data_row.get("max_ramp_up_percentage")
            else None
        )
        values_to_add["ramp_down"] = (
            getattr(component, "active_power")
            * BaseQuantity(wecc_data_row.get("max_ramp_up_percentage"), "1/min")
            if wecc_data_row.get("max_ramp_up_percentage")
            else None
        )
        values_to_add["run_up"] = (
            getattr(component, "active_power")
            * BaseQuantity(wecc_data_row.get("run_up_rate"), "1/min")
            if wecc_data_row.get("run_up_rate")
            else None
        )
        values_to_add["min_rated_capacity"] = (
            getattr(component, "active_power")
            * BaseQuantity(wecc_data_row.get("min_stable_level_percentage"), "")
            if wecc_data_row.get("min_stable_level_percentage")
            else ActivePower(0, "MW")
        )
        values_to_add["mean_time_to_repair"] = (
            BaseQuantity(wecc_data_row.get("mean_time_to_repair"), "h")
            if wecc_data_row.get("mean_time_to_repair")
            else None
        )
        values_to_add["min_up_time"] = (
            BaseQuantity(wecc_data_row.get("min_up_time"), "h") if wecc_data_row.get("min_up_time") else None
        )
        values_to_add["min_down_time"] = (
            BaseQuantity(wecc_data_row.get("min_down_time"), "h")
            if wecc_data_row.get("min_down_time")
            else None
        )
        values_to_add["startup_cost"] = (
            getattr(component, "active_power")
            * BaseQuantity(wecc_data_row.get("start_cost_per_MW"), "usd/MW")
            if wecc_data_row.get("start_cost_per_MW")
            else None
        )
        values_to_add["shutdown_cost"] = (
            getattr(component, "active_power")
            * BaseQuantity(wecc_data_row.get("shutdown_cost_per_MW"), "usd/MW")
            if wecc_data_row.get("shutdown_cost_per_MW")
            else None
        )
        valid_fields = {key: value for key, value in values_to_add.items() if key in component.model_fields}
        for key, value in valid_fields.items():
            setattr(component, key, value)
            
        if fom_cost := wecc_data_row.get("fom_cost"):
            component.operation_cost.fixed = fom_cost

        if heat_rate := wecc_data_row.get("heat_rate"):
            component.operation_cost.variable.value_curve.function_data.proportional_term = heat_rate

        if vom_cost := wecc_data_row.get("vom_cost"):
            component.operation_cost.variable.vom_cost.function_data.proportional_term = vom_cost

    return system
