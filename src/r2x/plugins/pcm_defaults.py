"""Augment results from CEM with PCM defaults."""

from argparse import ArgumentParser, _ArgumentGroup

from infrasys.base_quantity import BaseQuantity
import pandas as pd
from loguru import logger

from r2x.models import Generator
from r2x.api import System
from r2x.config_scenario import Scenario
from r2x.parser.handler import BaseParser
from r2x.utils import read_json
from r2x.plugin_manager import PluginManager
from r2x.units import get_magnitude


@PluginManager.register_cli("system_update", "pcm_defaults")
def cli_arguments(parser: ArgumentParser | _ArgumentGroup):
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--pcm-defaults-fpath",
        help="File containing the defaults",
    )


@PluginManager.register_system_update("pcm_defaults")
def update_system(
    config: Scenario, system: System, parser: BaseParser, pcm_defaults_fpath: str | None = None
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

    reference_data = (
        pd.DataFrame.from_dict(pcm_defaults)
        .transpose()
        .reset_index()
        .rename(
            columns={
                "index": "tech",
            }
        )
    )
    reference_data.loc[reference_data.tech.str.startswith("battery"), "mean_time_to_repair"] = (
        config.input_config.defaults["storage_mean_time_to_repair"]
    )
    reference_data.loc[reference_data.tech.str.startswith("hyd"), "mean_time_to_repair"] = (
        config.input_config.defaults["hydro_mean_time_to_repair"]
    )
    reference_data.loc[reference_data.tech.str.startswith("hyd"), "max_ramp_up_percentage"] = (
        config.input_config.defaults["hydro_ramp_rate"] * 100
    )
    reference_data.loc[reference_data.tech.str.endswith("nd"), "min_stable_level_percentage"] = 1

    # Rename columns on the file itself and remove this
    reference_data = reference_data.loc[
        :,
        [
            "tech",
            "min_stable_level_percentage",
            "start_cost_per_MW",
            "max_ramp_up_percentage",
            "mean_time_to_repair",
            "min_down_time",
            "min_up_time",
            "maintenance_rate",
            "forced_outage_rate",
        ],
    ]
    dtypes = {
        "min_stable_level_percentage": "float",
        "start_cost_per_MW": "float",
        "max_ramp_up_percentage": "float",
        "mean_time_to_repair": "float",
        "min_down_time": "float",
        "min_up_time": "float",
        "maintenance_rate": "float",
        "forced_outage_rate": "float",
    }
    reference_data = reference_data.astype(dtypes)

    reference_techs = reference_data.tech.unique()

    for component in system.get_components(Generator):
        reeds_tech = getattr(component, "ext").get("reeds_tech")

        if reeds_tech not in reference_techs:
            continue

        wecc_data_row = (
            reference_data.loc[reference_data.tech.str.startswith(reeds_tech)]
            .dropna(axis=1)
            .to_dict(orient="records")[0]
        )
        values_to_add = {}

        # I do not like this implementation.
        values_to_add["planned_outage_rate"] = (
            getattr(component, "planned_outage_rate", None)
            or BaseQuantity(wecc_data_row.get("maintenance_rate"), "%")
            if wecc_data_row.get("maintenance_rate")
            else None
        )
        values_to_add["forced_outage_rate"] = (
            getattr(component, "forced_outage_rate", None)
            or BaseQuantity(wecc_data_row.get("forced_outage_rate"), "%")
            if wecc_data_row.get("forced_outage_rate")
            else None
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
        valid_fields = {key: value for key, value in values_to_add.items() if key in component.model_fields}
        for key, value in valid_fields.items():
            setattr(component, key, value)

        if hasattr(component, "active_power_limits") and hasattr(component.active_power_limits, "min"):
            setattr(
                component.active_power_limits,
                "min",
                get_magnitude(getattr(component, "active_power", 0))
                * wecc_data_row.get("min_stable_level_percentage", 1),
            )

    return system
