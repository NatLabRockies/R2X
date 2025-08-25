"""R2X Sienna system exporter."""

# System packages
import json
from functools import partial
from operator import itemgetter
from pathlib import Path
from typing import Any
from urllib.request import urlopen

# Third-party packages
from infrasys import Component, SingleTimeSeries
from loguru import logger

# Local imports
from r2x.api import System
from r2x.config_models import ReEDSConfig, SiennaConfig, get_year
from r2x.config_scenario import Scenario
from r2x.exporter.handler import BaseExporter, get_export_records
from r2x.exporter.utils import (
    apply_default_value,
    apply_flatten_key,
    apply_pint_deconstruction,
    apply_property_map,
    apply_unnest_key,
)
from r2x.models import (
    ACBranch,
    Bus,
    DCBranch,
    Generator,
    HydroPumpedStorage,
    PowerLoad,
    Reserve,
    ReserveMap,
    Storage,
)
from r2x.models.branch import Transformer2W
from r2x.utils import haskey

PSY_URL = "https://raw.githubusercontent.com/NREL-Sienna/PowerSystems.jl/refs/heads/main/"
TABLE_DATA_SPEC = "src/descriptors/power_system_inputs.json"


def get_psy_fields() -> dict[str, Any]:
    """Get PSY JSON schema."""
    request = urlopen(PSY_URL + TABLE_DATA_SPEC)
    descriptor = json.load(request)
    return descriptor


class SiennaExporter(BaseExporter):
    """Sienna exporter class.

    This is the class that export the infrasys system to csv's required to read
    in PowerSystems.jl. The class contains a method per file that needs to get
    created and some of the methods manipulate the data to be compliant wth
    PowerSystems.jl. The order is important for some steps, however, most
    of them could be run sequentially.

    The method `run` is the responsible of running all the exporter.

    Notes
    -----
    All the methods defined an `output_columns` which defines the fields from
    the `Component` that we want to export.

    All methods call `export_component_to_csv` or `export_dict_to_csv` that
    is defined on the `BaseExporter` class.


    See Also
    --------
    BaseExporter.export_component_to_csv
    BaseExporter.export_dict_to_csv
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert self.config.output_config
        assert self.config.input_config
        self.output_data = {}
        if not isinstance(self.config.output_config, SiennaConfig):
            msg = (
                f"Output config is of type {type(self.config.output_config)}. "
                "It should be type of `PlexosConfig`."
            )
            raise TypeError(msg)
        if isinstance(self.config.input_config, ReEDSConfig) and isinstance(
            self.config.input_config.solve_year, list
        ):
            msg = "Multiple solve years are not supported yet."
            raise NotImplementedError(msg)

        self.output_config = self.config.input_config.to_class(SiennaConfig, self.config.output_config)
        self.property_map = self.output_config.defaults.get("sienna_property_map", {})
        self.unit_map = self.output_config.defaults.get("sienna_unit_map", {})
        self.output_fields = self.output_config.defaults["table_data"]
        self.year = get_year(self.output_config)
        assert self.year is not None

    def run(self, *args, path=None, **kwargs) -> "SiennaExporter":
        """Run sienna exporter workflow.


        Notes
        -----
        All methods call `export_component_to_csv` or `export_dict_to_csv` that
        is defined on the `BaseExporter` class.

        If performance is a constraint, we could parallelize the methods.
        """
        logger.info("Starting {}", self.__class__.__name__)

        self.process_bus_data()
        self.process_load_data()
        self.process_branch_data()
        self.process_dc_branch_data()
        self.process_gen_data()
        self.process_reserves_data()
        self.process_storage_data()
        self.export_data()
        create_timeseries_pointers(
            self.config,
            self.system,
            output_folder=self.config.output_folder,
        )

        return self

    def process_bus_data(self, fname: str = "bus.csv") -> None:
        """Create bus.csv file.

        Parameters
        ----------
        fname : str
            Name of the file to be created
        """
        output_fields = [
            "bus_id",
            "name",
            "area",
            "zone",
            "base_voltage",
            "bus_type",
        ]

        records = [
            component.model_dump(exclude_none=True, mode="python", serialize_as_any=True)
            for component in self.system.get_components(Bus)
        ]

        key_mapping = {"number": "bus_id", "load_zone": "zone"}
        export_records = get_export_records(
            records,
            partial(apply_property_map, property_map=self.property_map | key_mapping),
            partial(apply_pint_deconstruction, unit_map=self.unit_map),
            partial(apply_unnest_key, key_map={"zone": "name", "area": "name"}),
        )
        self.system._export_dict_to_csv(
            export_records,
            fpath=self.output_folder / fname,
            fields=output_fields,
            restval="NA",
        )

    def process_load_data(self, fname: str = "load.csv") -> None:
        """Create load.csv file.

        Parameters
        ----------
        fname : str
            Name of the file to be created
        """
        output_fields = [
            "bus_id",
            "name",
            "available",
            "active_power",
            "reactive_power",
            "max_active_power",
            "max_reeactive_power",
        ]
        records = [
            component.model_dump(exclude_none=True, mode="python", serialize_as_any=True)
            for component in self.system.get_components(PowerLoad)
        ]
        key_mapping = {
            "bus": "bus_id",
        }
        export_records = get_export_records(
            records,
            partial(apply_property_map, property_map=self.property_map | key_mapping),
            partial(apply_pint_deconstruction, unit_map=self.unit_map),
            partial(apply_unnest_key, key_map={"bus_id": "number"}),
        )
        self.system._export_dict_to_csv(
            export_records,
            fpath=self.output_folder / fname,
            fields=output_fields,
            restval="0.0",
        )
        logger.info(f"File {fname} created.")

    def process_branch_data(self, fname: str = "branch.csv") -> None:
        """Create branch.csv file.

        Parameters
        ----------
        fname : str
            Name of the file to be created
        """
        output_fields = [
            "name",
            "connection_points_from",
            "connection_points_to",
            "r",
            "x",
            "primary_shunt",
            "rate",
            "rating_up",
            "rating_down",
            "tap",
            "is_transformer",
            "ext",
        ]

        key_mapping = {
            "from_bus": "connection_points_from",
            "to_bus": "connection_points_to",
            "class_type": "branch_type",
            "rating": "rate",
            "b": "primary_shunt",
        }

        records = [
            component.model_dump(exclude_none=True, mode="python", serialize_as_any=True)
            for component in self.system.get_components(ACBranch)
        ]
        export_records = get_export_records(
            records,
            partial(apply_property_map, property_map=self.property_map | key_mapping),
            partial(apply_pint_deconstruction, unit_map=self.unit_map),
            partial(
                apply_unnest_key,
                key_map={"connection_points_from": "number", "connection_points_to": "number"},
            ),
            partial(
                lambda component, key, func: component.update({key: func(component)}) or component,
                key="is_transformer",
                func=lambda d: True if d["branch_type"] == Transformer2W.__name__ else False,
            ),
            partial(apply_default_value, default_value_map={"tap": 1.0}),
        )
        self.system._export_dict_to_csv(
            export_records,
            fpath=self.output_folder / fname,
            fields=output_fields,
            restval="NA",
        )
        logger.info(f"File {fname} created.")

    def process_dc_branch_data(self, fname="dc_branch.csv") -> None:
        """Create dc_branch.csv file.

        Parameters
        ----------
        fname : str
            Name of the file to be created
        """
        output_fields = [
            "name",
            "connection_points_from",
            "connection_points_to",
            "rate",
            "loss",
        ]

        self.system.export_component_to_csv(
            DCBranch,
            fpath=self.output_folder / fname,
            fields=output_fields,
            unnest_key="number",
            key_mapping={
                "from_bus": "connection_points_from",
                "to_bus": "connection_points_to",
                "class_type": "branch_type",
                "rating_up": "rate",
            },
            restval="NA",
        )
        logger.info(f"File {fname} created.")
        return

    def process_gen_data(self, fname="gen.csv"):
        """Create gen.csv file.

        Parameters
        ----------
        fname : str
            Name of the file to be created
        """
        # reactive power cant be export

        key_mapping = {
            "bus": "bus_id",
            "prime_mover_type": "unit_type",
        }

        records = [
            component.model_dump(exclude_none=True, mode="python", serialize_as_any=True)
            for component in self.system.get_components(Generator)
        ]
        export_records = get_export_records(
            records,
            partial(apply_operation_table_data),
            partial(apply_flatten_key, keys_to_flatten={"active_power_limits"}),
            partial(apply_property_map, property_map=self.property_map | key_mapping),
            partial(apply_pint_deconstruction, unit_map=self.unit_map),
            partial(apply_unnest_key, key_map={"bus_id": "number"}),
            partial(
                apply_default_value,
                default_value_map={"fuel_price": 0.0, "power_factor": 1.0, "startup_cost": 0.0},
            ),
        )

        sorted_records = sorted(export_records, key=itemgetter("name"), reverse=True)
        self.system._export_dict_to_csv(
            sorted_records,
            fpath=self.output_folder / fname,
            fields=self.output_fields["generator"],
            restval="NA",
        )
        logger.info(f"File {fname} created.")

    def process_reserves_data(self, fname="reserves.csv") -> None:
        """Create reserve.csv file.

        Parameters
        ----------
        fname : str
            Name of the file to be created
        """
        output_fields = [
            "name",
            "requirement",
            "timeframe",
            "eligible_region",
            "direction",
            "contributing_devices",
            "eligible_device_categories",
            "eligible_device_subcategories",
        ]

        # ReserveMap holds the eligible devices in the mapping.
        reserve_map_list: list[dict[str, Any]] = list(
            map(lambda component: component["mapping"], self.system.to_records(ReserveMap))
        )

        if not reserve_map_list:
            msg = "Reserve map class not found on the system. Skipping reserve contributing devices file."
            logger.warning(msg)
            return

        if len(reserve_map_list) > 1:
            logger.warning("We do not support multiple reserve maps per system")
            return
        reserve_map: dict = reserve_map_list[0]

        reserves: list[dict[str, Any]] = list(self.system.to_records(Reserve))

        output_data = []
        for reserve in reserves:
            # NOTE: Only export reserves that exists on the reserve map
            if reserve["name"] in reserve_map:
                output_dict = reserve
                output_dict["direction"] = reserve["direction"].name
                output_dict["eligible_device_categories"] = "(Generator,Storage)"
                contributing_devices = reserve_map.get(reserve["name"])
                output_dict["contributing_devices"] = str(tuple(contributing_devices)).replace(  # type: ignore
                    "'", ""
                )  # Sienna expects a tuple for this field that looks like "(val1,val2,val3)"
                output_data.append(output_dict)

        key_mapping = {"region": "eligible_region", "max_requirement": "requirement"} | self.property_map

        export_records = get_export_records(
            output_data,
            partial(apply_property_map, property_map=self.property_map | key_mapping),
            partial(apply_pint_deconstruction, unit_map=self.unit_map),
            partial(apply_unnest_key, key_map={"eligible_region": "name"}),
        )
        self.system._export_dict_to_csv(
            export_records,
            fpath=self.output_folder / fname,
            fields=output_fields,
            restval="NA",
        )
        logger.info(f"File {fname} created.")
        return

    def process_storage_data(self, fname="storage.csv") -> None:
        """Create storage.csv file.

        Parameters
        ----------
        fname : str
            Name of the file to be created
        """
        output_fields = [
            "name",
            "position",
            "available",
            "generator_name",
            "bus_id",
            "active_power",
            "rating",
            "input_efficiency",
            "output_efficiency",
            "storage_capacity",
            "min_storage_capacity",
            "max_storage_capacity",
            "input_active_power_limit_min",
            "output_active_power_limit_max",
            "output_active_power_limit_min",
            "unit_type",
        ]

        storage_list = get_export_records(
            list(
                self.system.to_records(
                    Generator, filter_func=lambda x: isinstance(x, Storage | HydroPumpedStorage)
                )
            ),
            partial(apply_property_map, property_map=self.property_map),
            partial(apply_flatten_key, keys_to_flatten={"active_power_limits"}),
            partial(apply_pint_deconstruction, unit_map=self.unit_map),
            # partial(apply_valid_properties, valid_properties=output_fields),
        )

        if not storage_list:
            logger.warning("No storage devices found")
            return

        output_data = []
        for storage in storage_list:
            output_dict = storage
            output_dict["generator_name"] = storage["name"]
            output_dict["input_active_power_limit_max"] = output_dict["active_power_limits_max"]
            output_dict["output_active_power_limit_max"] = output_dict["active_power_limits_max"]
            # NOTE: If we need to change this in the future, we could probably
            # use the function max to check if the component has the field.
            output_dict["input_active_power_limit_min"] = 0  # output_dict["active_power"]
            output_dict["output_active_power_limit_min"] = 0  # output_dict["active_power"]
            output_dict["active_power"] = output_dict["active_power"]
            output_dict["bus_id"] = (
                getattr(self.system.get_component_by_label(output_dict["bus"]), "number", None)
                if output_dict["bus"]
                else None
            )
            output_dict["rating"] = output_dict["rating"]

            # NOTE: For pumped hydro storage we create a head and a tail
            # representation that keeps track of the upper and down reservoir
            # state of charge.
            # if storage["class_type"] == "HydroPumpedStorage":
            original_name = output_dict["name"]
            output_dict["name"] = original_name + "_head"
            output_dict["position"] = "head"
            output_data.append(output_dict)
            tail_copy = output_dict.copy()
            tail_copy["name"] = original_name + "_tail"
            output_dict["position"] = "tail"
            output_data.append(tail_copy)

        key_mapping = self.property_map
        self.system._export_dict_to_csv(
            output_data,
            fpath=self.output_folder / fname,
            fields=output_fields,
            key_mapping=key_mapping,
            unnest_key="number",
            restval="NA",
        )

        logger.info("File storage.csv created.")

    def create_timeseries_pointers(self) -> None:
        """Create timeseries_pointers.json file.

        Parameters
        ----------
        fname : str
            Name of the file to be created
        """

    def export_data(self) -> None:
        """Export csv data to specified folder from output_data attribute."""
        logger.debug("Saving Sienna data and timeseries files.")

        # First export all time series objects
        self.time_series_to_csv(config=self.config, system=self.system, reference_year=self.year)
        logger.info("Saving time series data.")


def create_timeseries_pointers(
    config: Scenario,
    system: System,
    /,
    reference_year: int | None = None,
    *,
    output_folder: str | Path | None = None,
    name: str | None = None,
    time_series_type: type[SingleTimeSeries] = SingleTimeSeries,
    default_fname: str = "timeseries_pointers.json",
    time_series_folder: str = "Data",
    **user_attributes: str,
) -> bool:
    """Export time series pointers to json file.

    Parameters
    ----------
    config : Scenario
        The scenario configuration object containing output settings.
    system : System
        The system containing the components and time series data.
    output_folder : str | Path | None, optional
        The directory where CSV files should be saved (default is `config.output_folder`).
    reference_year : int | None, optional
        The reference year for time series generation (default is inferred from `config`).
    default_fname: str
        Name of the pointers file. Default `timeseries_pointers.json`.
    time_series_folder : Literal["Data"], optional
        Subfolder for storing time series files (default is "Data").
    **user_attributes : str
        Additional filtering attributes for selecting time series data.

    See Also
    --------
    create_time_series_arrays
    check_time_series_length_consistency
    """
    logger.info("Exporting time series pointers.")
    output_folder = output_folder or config.output_folder
    assert output_folder is not None
    if isinstance(output_folder, str):
        output_folder = Path(output_folder)

    if not reference_year:
        assert config.output_config is not None
        reference_year = get_year(config.output_config)

    ts_pointers_list = []
    for component in system.get_components(
        Component,
        filter_func=lambda x: system.has_time_series(
            x, time_series_type=time_series_type, name=name, **user_attributes
        ),
    ):
        for ts_metadata in system.time_series.list_time_series_metadata(
            component, time_series_type=time_series_type, name=name, **user_attributes
        ):
            assert hasattr(ts_metadata, "resolution")
            ts_component_name = f"{component.__class__.__name__}_{ts_metadata.name}"
            ts_pointers = {
                "category": type(component).__name__,
                "component_name": component.name,
                "data_file": str(
                    output_folder
                    / time_series_folder
                    / f"{ts_component_name}_{config.name}_{reference_year}.csv"
                ),
                "normalization_factor": "MAX",  # LL: null is not translated properly
                "resolution": ts_metadata.resolution.seconds,
                "name": ts_metadata.name,
                "scaling_factor_multiplier_module": "PowerSystems",
                "scaling_factor_multiplier": "get_max_active_power",
            }
            ts_pointers_list.append(ts_pointers)

    with open(output_folder / default_fname, mode="w") as f:
        json.dump(ts_pointers_list, f, indent=4)

    logger.info("File {} created.", output_folder / default_fname)
    return True


def apply_operation_table_data(
    component: dict[str, Any],
) -> dict[str, Any]:
    """Process and apply operation cost data for `PSY.power_system_table_data.jl`.

    This function extracts operation cost data from a component dictionary and adds
    various cost-related fields to it. It handles different types of cost data,
    including variable costs, fuel costs, heat rates, and cost/fuel curves.

    Parameters
    ----------
    component : dict[str, Any]
        A dictionary containing component data, potentially including operation cost information.

    Returns
    -------
    dict[str, Any]
        The input component dictionary, potentially modified with additional operation cost fields.

    Notes
    -----
    This function modifies the input dictionary in-place and returns it.

    The function processes the following types of operation costs:
    - Variable costs (vom_cost)
    - Fuel costs
    - Heat rate coefficients (a0, a1, a2)
    - Cost curves
    - Fuel curves

    Raises
    ------
    AssertionError
        If the fuel_cost is None when present in the variable cost data.
    NotImplementedError
        If an unsupported variable curve type is encountered.

    Examples
    --------
    >>> component = {
    ...     "operation_cost": {
    ...         "variable": {
    ...             "vom_cost": {"function_data": {"proportional_term": 10}},
    ...             "fuel_cost": 0.05,
    ...             "value_curve": {
    ...                 "function_data": {
    ...                     "constant_term": 100,
    ...                     "proportional_term": 20,
    ...                     "quadratic_term": 0.5,
    ...                     "points": [(0, 0), (50, 1000), (100, 2500)],
    ...                 }
    ...             },
    ...         },
    ...         "variable_type": "CostCurve",
    ...     }
    ... }
    >>> updated_component = apply_operation_table_data(component)
    >>> updated_component["variable_cost"]
    10
    >>> updated_component["fuel_price"]
    50.0
    >>> updated_component["heat_rate_a0"]
    100
    >>> updated_component["output_point_1"]
    50
    >>> updated_component["cost_point_1"]
    1000
    """
    if not component.get("operation_cost", False):
        return component

    operation_cost = component["operation_cost"]

    if not (variable := operation_cost.get("variable")):
        return component

    if haskey(variable, ["vom_cost", "function_data"]):
        component["variable_cost"] = variable["vom_cost"]["function_data"].proportional_term

    if "fuel_cost" in variable.keys():
        assert variable["fuel_cost"] is not None
        # Note: We multiply the fuel price by 1000 to offset the division
        # done by Sienna when it parses .csv files
        component["fuel_price"] = variable["fuel_cost"] * 1000
    if haskey(variable, ["value_curve", "function_data"]):
        function_data = variable["value_curve"]["function_data"]
        function_data_fields = function_data.model_fields_set
        if "constant_term" in function_data_fields:
            component["heat_rate_a0"] = function_data.constant_term
        if "proportional_term" in function_data_fields:
            component["heat_rate_a1"] = function_data.proportional_term
        if "quadratic_term" in function_data_fields:
            component["heat_rate_a2"] = function_data.quadratic_term
        if "points" in function_data_fields:
            component = _variable_type_parsing(component, operation_cost)
    return component


def _variable_type_parsing(component: dict, cost_dict: dict[str, Any]) -> dict[str, Any]:
    variable_curve = cost_dict["variable"]
    x_y_coords = variable_curve["value_curve"]["function_data"].points
    match cost_dict["variable_type"]:
        case "CostCurve":
            for i, (x_coord, y_coord) in enumerate(x_y_coords):
                output_point_col = f"output_point_{i}"
                component[output_point_col] = x_coord

                cost_point_col = f"cost_point_{i}"
                component[cost_point_col] = y_coord
        case "FuelCurve":
            for i, (x_coord, y_coord) in enumerate(x_y_coords):
                output_point_col = f"output_point_{i}"
                component[output_point_col] = x_coord

                heat_rate_col = "heat_rate_avg_0" if i == 0 else f"heat_rate_incr_{i}"
                component[heat_rate_col] = y_coord
        case _:
            msg = f"Type {cost_dict['variable_type']} variable curve not supported"
            raise NotImplementedError(msg)
    return component
