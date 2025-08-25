"""Plexos parser class."""

import importlib
from argparse import ArgumentParser
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Any

import numpy as np
import polars as pl
from infrasys.cost_curves import CostCurve, FuelCurve, UnitSystem
from infrasys.exceptions import ISNotStored
from infrasys.function_data import (
    LinearFunctionData,
    QuadraticFunctionData,
)
from infrasys.time_series_models import SingleTimeSeries
from infrasys.value_curves import AverageRateCurve, InputOutputCurve, LinearCurve
from loguru import logger
from pint import Quantity
from plexosdb import ClassEnum, CollectionEnum, PlexosDB
from plexosdb.utils import get_sql_query

from r2x.api import System
from r2x.config_models import PlexosConfig
from r2x.enums import (
    ACBusTypes,
    EmissionType,
    PrimeMoversType,
    ReserveDirection,
    ReserveType,
    StorageTechs,
    ThermalFuels,
)
from r2x.exceptions import R2XModelError, R2XParserError
from r2x.exporter.utils import get_property_magnitude
from r2x.models import (
    ACBus,
    Area,
    Emission,
    EnergyReservoirStorage,
    FromTo_ToFrom,
    Generator,
    HydroDispatch,
    HydroGenerationCost,
    HydroPumpedStorage,
    InputOutput,
    LoadZone,
    MinMax,
    MonitoredLine,
    PowerLoad,
    RenewableGen,
    RenewableGenerationCost,
    Reserve,
    ReserveMap,
    ThermalGen,
    ThermalGenerationCost,
    Transformer2W,
    TransmissionInterface,
    TransmissionInterfaceMap,
    UpDown,
)
from r2x.plugin_manager import PluginManager
from r2x.units import ureg
from r2x.utils import get_enum_from_string, get_pint_unit, validate_string

from .handler import PCMParser, csv_handler
from .parser_helpers import (
    construct_pwl_from_quadtratic,
    field_filter,
    prepare_ext_field,
    reconcile_timeseries,
)
from .plexos_utils import (
    DATAFILE_COLUMNS,
    PLEXOS_ACTION_MAP,
    filter_property_dates,
    find_xml,
    get_column_enum,
    parse_data_file,
    time_slice_handler,
)
from .polars_helpers import pl_filter_by_year

models = importlib.import_module("r2x.models")

R2X_MODELS = importlib.import_module("r2x.models")
BASE_WEATHER_YEAR = 2007
XML_FILE_KEY = "xml_file"
DEFAULT_QUERY_COLUMNS_SCHEMA = {  # NOTE: Order matters
    "membership_id": pl.Int64,
    "parent_object_id": pl.Int32,
    "parent_object_name": pl.String,
    "parent_class_name": pl.String,
    "child_class_name": pl.String,
    "category": pl.String,
    "object_id": pl.Int32,
    "name": pl.String,
    "property_name": pl.String,
    "property_unit": pl.String,
    "property_value": pl.Float32,
    "band": pl.Int32,
    "date_from": pl.String,
    "date_to": pl.String,
    "memo": pl.String,
    "scenario_category": pl.String,
    "scenario": pl.String,
    "action": pl.String,
    "data_file_tag": pl.String,
    "data_file": pl.String,
    "variable_tag": pl.String,
    "timeslice_tag": pl.String,
    "timeslice": pl.String,
    "timeslice_value": pl.Float32,
    "data_text": pl.String,
}
DEFAULT_PROPERTY_COLUMNS = [
    "band",
    "property_name",
    "property_value",
    "property_unit",
    "data_file",
    "variable",
    "action",
    # "variable_tag",
    # "variable_default",
    # "timeslice",
    # "timeslice_value",
]
DEFAULT_INDEX = ["object_id", "name", "category"]
SIMPLE_QUERY_COLUMNS_SCHEMA = {
    "parent_class_name": pl.String,
    "child_class_name": pl.String,
    "parent_object_id": pl.Int32,
    "object_id": pl.Int32,
    "name": pl.String,
    "category": pl.String,
    "property_name": pl.String,
    "property_unit": pl.String,
    "property_value": pl.Float64,
    "band": pl.Int32,
    "date_from": pl.String,
    "date_to": pl.String,
    "text": pl.String,
    "text_class_name": pl.String,
    "tag_timeslice": pl.String,
    "tag_timeslice_object_id": pl.Int32,
    "tag_datafile": pl.String,
    "tag_datafile_object_id": pl.Int32,
    "tag_variable": pl.String,
    "tag_variable_object_id": pl.Int32,
    "action": pl.String,
    "scenario": pl.String,
}


@PluginManager.register_cli("parser", "plexos")
def cli_arguments(parser: ArgumentParser) -> None:
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--model",
        required=False,
        help="Plexos model to translate",
    )


class PlexosParser(PCMParser):
    """Plexos parser class."""

    def __init__(self, *args, xml_file: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        assert self.config.run_folder
        assert self.config.input_config
        assert isinstance(self.config.input_config, PlexosConfig)  # Only take Plexos configurations
        self.run_folder = Path(self.config.run_folder)
        self.input_config = self.config.input_config
        self.system = System(name=self.config.name, auto_add_composed_components=True)
        self.property_map = self.input_config.defaults["plexos_input_property_map"] or {}
        self.device_map = self.input_config.defaults["plexos_device_map"] or {}
        self.fuel_map = self.input_config.defaults["plexos_fuel_map"] or {}
        self.category_map = self.input_config.defaults["plexos_category_map"] or {}
        self.device_match_string = self.input_config.defaults["device_name_inference_map"] or {}
        self.generator_models = self.input_config.defaults["generator_models"] or {}
        self.year = self.input_config.model_year
        assert self.year
        assert isinstance(self.year, int)

        # TODO(pesap): Rename exceptions to include R2X
        # https://github.com/NREL/R2X/issues/5
        # R2X needs at least one of this maps defined to correctly work.
        one_required = ["fuel_map", "device_map", "category_map"]
        if all(getattr(self, one_req, {}) == {} for one_req in one_required) and self.device_match_string:
            msg = f"At least one of {', or '.join(one_required)} is required to initialize PlexosParser"
            raise R2XParserError(msg)

        # Populate databse from XML file.
        # If xml file is not specified, check user_dict["fmap"]["xml_file"] or use
        # only xml file in project directory
        if xml_file is None:
            xml_file = self.input_config.fmap.get("xml_file", {}).get("fname", None)
            xml_file = xml_file or str(find_xml(self.run_folder))

        xml_file = str(self.run_folder / xml_file)

        self.db = PlexosDB.from_xml(xml_file)

        # Extract scenario data
        model_name = getattr(self.input_config, "model_name", None) or self.input_config.fmap.get(
            "xml_file", {}
        ).get("model_name", None)
        if model_name is None:
            model_name = self._select_model_name()
        logger.info("Parsing plexos model={}", model_name)
        self._process_scenarios(model_name=model_name)

        # date from is in days since 1900, convert to year
        if not self.year:
            logger.debug("Getting ST year from model horizon")
            date_from = self._collect_horizon_data(model_name=model_name).get("Date From")
            if date_from is not None:
                self.year = int((date_from / 365.25) + 1900)

        self.hourly_time_index = pl.datetime_range(
            datetime(self.year, 1, 1), datetime(self.year + 1, 1, 1), interval="1h", eager=True, closed="left"
        ).to_frame("datetime")
        self._data_file_cache: dict[Path, pl.DataFrame] = {}
        self._data_file_column_types: dict[Path, DATAFILE_COLUMNS] = {}

        return

    def build_system(self) -> System:
        """Create infrasys system."""
        logger.info("Building infrasys system using {}", self.__class__.__name__)

        # If we decide to change the engine for handling the data we can do it here.
        object_data = self._plexos_table_data()
        self.plexos_data = self._polarize_data(object_data=object_data)

        # Construct the network
        self._construct_areas()
        self._construct_load_zones()
        self._construct_buses()
        self._construct_branches()
        self._construct_transformers()
        self._construct_interfaces()
        self._construct_reserves()
        self._add_reserve_region_properties()

        # Generators
        self._construct_generators()
        self._add_buses_to_generators()
        self._add_generator_reserves()

        # Batteries
        self._construct_batteries()
        self._add_buses_to_batteries()
        self._add_battery_reserves()

        self._construct_load_profiles()

        # Emission object_class
        self._add_generator_emissions()
        return self.system

    def _collect_horizon_data(self, model_name: str) -> dict[str, float]:
        """Collect horizon data (Date From/To) from Plexos database."""
        horizon_query = f"""
        SELECT
            atr.name AS attribute_name,
            COALESCE(attr_data.value, atr.default_value) AS attr_val
        FROM
            t_object
        LEFT JOIN t_class AS class ON
            t_object.class_id == class.class_id
        LEFT JOIN t_attribute AS atr ON
            t_object.class_id  == atr.class_id
        LEFT JOIN t_membership AS tm ON
            t_object.object_id  == tm.child_object_id
        LEFT JOIN t_class AS parent_class ON
            tm.parent_class_id == parent_class.class_id
        LEFT JOIN t_object AS to2 ON
            tm.parent_object_id == to2.object_id
        LEFT JOIN t_attribute_data attr_data ON
            attr_data.attribute_id == atr.attribute_id AND t_object.object_id == attr_data.object_id
        WHERE
            class.name == '{ClassEnum.Horizon.value}'
            AND parent_class.name == '{ClassEnum.Model.value}'
            AND to2.name == '{model_name}'
        """
        horizon_data = self.db.query(horizon_query)
        horizon_map = {key: value for key, value in horizon_data}
        return horizon_map

    def _get_fuel_prices(self):
        logger.debug("Creating fuel representation")
        system_fuels = (pl.col("child_class_name") == ClassEnum.Fuel.value) & (
            pl.col("parent_class_name") == ClassEnum.System.value
        )

        fuels = self._get_model_data(system_fuels)
        fuels.write_csv("fuels.csv")
        fuel_prices = {}
        for fuel_name, fuel_data in fuels.group_by("name"):
            fuel_name = fuel_name[0]
            property_records = fuel_data.to_dicts()

            for property in property_records:
                property.update({"property_unit": "$/MMBtu"})

            mapped_records, multi_band_records = self._parse_property_data(property_records)
            if multi_band_records:
                logger.warning("Some properties have multiple bands.")
            mapped_records["name"] = fuel_name
            fuel_prices[fuel_name] = mapped_records.get("Price", 0)
        return fuel_prices

    def _construct_areas(self) -> None:
        """Create Area representation from a PLEXOS model.

        Area is an aggregation of buses that could or could not be used for balancing purposes.
        The equivalent of an Area from PLEXOS is a `ClassEnum.Region` category.
        """
        logger.info("Creating `Area` representation")
        system_regions = (pl.col("child_class_name") == ClassEnum.Region.value) & (
            pl.col("parent_class_name") == ClassEnum.System.value
        )
        regions = self._get_model_data(system_regions)
        for area in regions["category"].unique():
            self.system.add_component(Area(name=area))

    def _construct_load_zones(self, default_model=LoadZone) -> None:
        """Create LoadZone representation.

        Plexos can define load at multiple levels, but for balancing the load,
        we assume that it happens at the region level, which is a typical way
        of doing it.
        """
        logger.info("Creating `LoadZone` representation")
        system_regions = (pl.col("child_class_name") == ClassEnum.Zone.value) & (
            pl.col("parent_class_name") == ClassEnum.System.value
        )
        regions = self._get_model_data(system_regions)

        region_pivot = regions.pivot(
            index=DEFAULT_INDEX,
            on="property_name",
            values="property_value",
            aggregate_function="first",
        )
        for region in region_pivot.iter_rows(named=True):
            valid_fields, ext_data = field_filter(region, default_model.model_fields)
            valid_fields = prepare_ext_field(valid_fields, ext_data)
            self.system.add_component(default_model(**valid_fields))
        return

    def _construct_buses(self, default_model=ACBus) -> None:
        logger.info("Creating `Bus` representation")

        # Get list of buses that are connected to lines, because `sienna` doesn't like islanded buses
        buses_connected_to_lines = self._get_model_data(
            (
                (pl.col("parent_class_name") == ClassEnum.Line.value).or_(
                    pl.col("parent_class_name") == ClassEnum.Transformer.value
                )
            )
            & (pl.col("child_class_name") == ClassEnum.Node.value)
        )["name"]

        system_buses = (
            (pl.col("child_class_name") == ClassEnum.Node.value)
            & (pl.col("parent_class_name") == ClassEnum.System.value)
            & (pl.col("name").is_in(buses_connected_to_lines))
        )
        region_buses = (pl.col("child_class_name") == ClassEnum.Region.value) & (
            pl.col("parent_class_name") == ClassEnum.Node.value
        )
        zone_buses = (pl.col("child_class_name") == ClassEnum.Zone.value) & (
            pl.col("parent_class_name") == ClassEnum.Node.value
        )
        system_buses = self._get_model_data(system_buses)
        buses_region = self._get_model_data(region_buses)
        buses_zone = self._get_model_data(zone_buses)
        for idx, (bus_name, bus_data) in enumerate(system_buses.group_by("name")):
            bus_name = bus_name[0]
            logger.trace("Parsing bus = {}", bus_name)

            property_records = bus_data.to_dicts()
            mapped_records, _ = self._parse_property_data(property_records)
            mapped_records["name"] = bus_name
            # mapped_records, _ = self._parse_property_data(property_records)

            valid_fields, ext_data = field_filter(mapped_records, default_model.model_fields)

            # Get region from buses region memberships
            region_name = buses_region.filter(pl.col("parent_object_id") == bus_data["object_id"].unique())[
                "category"
            ].item()
            zone_name = (
                buses_zone.filter(pl.col("parent_object_id") == bus_data["object_id"].unique())["name"]
                .unique()
                .item()
            )

            valid_fields["area"] = self.system.get_component(Area, name=region_name)
            valid_fields["load_zone"] = self.system.get_component(LoadZone, name=zone_name)

            # We parse all the buses as PV unless in the model someone specify a bus is a slack.
            # Plexos defines the True value of a Slack bus assigning it -1. Possible values are only 0
            # (False), -1 (True).
            valid_fields["bustype"] = ACBusTypes.PV
            if mapped_records.get("Is Slack Bus") == -1:
                valid_fields["bustype"] = ACBusTypes.SLACK

            valid_fields["base_voltage"] = (
                230.0 if not valid_fields.get("base_voltage") else valid_fields["base_voltage"]
            )

            valid_fields = prepare_ext_field(valid_fields, ext_data)
            bus = default_model(number=idx + 1, **valid_fields)
            self.system.add_component(bus)

            if max_active_power := mapped_records.pop("max_active_power", False):
                max_load = (
                    np.nanmax(max_active_power.data)
                    if isinstance(max_active_power, SingleTimeSeries)
                    else max_active_power
                )
                # We only add the load if it is bigger than zero.
                if max_load > 0:
                    load = PowerLoad(name=f"{bus_name}", bus=bus, max_active_power=max_load)
                    self.system.add_component(load)
                    ts_dict = {"solve_year": self.year}
                    if isinstance(max_active_power, SingleTimeSeries):
                        self.system.add_time_series(max_active_power, load, context=None, **ts_dict)

            ts_fields = {k: v for k, v in mapped_records.items() if isinstance(v, SingleTimeSeries)}
            if ts_fields:
                generator = self.system.get_component_by_label(f"{default_model.__name__}.{bus_name}")
                ts_dict = {"solve_year": self.year}
                for ts_name, ts in ts_fields.items():
                    ts.name = ts_name
                    self.system.add_time_series(ts, generator, context=None, **ts_dict)
        return

    def _add_generator_emissions(self, default_model=Emission):
        logger.info("Creating buses representation")
        emission_objects = (pl.col("child_class_name") == ClassEnum.Emission.value) & (
            pl.col("parent_class_name") == ClassEnum.System.value
        )
        generator_emissions = (pl.col("child_class_name") == ClassEnum.Generator.value) & (
            pl.col("parent_class_name") == ClassEnum.Emission.value
        )
        emission_objects = self._get_model_data(emission_objects)
        generator_emissions = self._get_model_data(generator_emissions)
        generator_emissions = generator_emissions.join(
            emission_objects, left_on="parent_object_id", right_on="object_id", suffix="_emission"
        )

        for generator_name, generator_data in generator_emissions.group_by(["name", "name_emission"]):
            generator_name = generator_name[0]
            logger.trace("Parsing generator emission properties = {}", generator_name)

            property_records = generator_data.to_dicts()
            mapped_records, multi_band_records = self._parse_property_data(property_records)
            mapped_records["generator_name"] = generator_name
            emission_name = generator_data["name_emission"].item()
            if emission_name in EmissionType._value2member_map_:
                mapped_records["emission_type"] = EmissionType[emission_name]
            else:
                mapped_records["emission_type"] = EmissionType.OTHER

            gen_component = self.system.list_components_by_name(Generator, generator_name)

            # If there is not gen_component at this point it means the generator is not activated on the model
            # or we could not parse it.
            if not gen_component:
                continue

            assert len(gen_component) == 1
            gen_component = gen_component[0]
            valid_fields, _ = field_filter(mapped_records, default_model.model_fields)

            required_fields = {
                key: value for key, value in default_model.model_fields.items() if value.is_required()
            }
            if not all(key in mapped_records for key in required_fields):
                missing_fields = [key for key in required_fields if key not in mapped_records]
                logger.warning(
                    "Skipping emission {} for generator {}. Missing Required Fields: {}",
                    emission_name,
                    generator_name,
                    missing_fields,
                )
                continue
            self.system.add_supplemental_attribute(gen_component, default_model(**valid_fields))

    def _construct_reserves(self, default_model=Reserve):
        logger.info("Creating reserve representation")

        system_reserves = self._get_model_data(
            (pl.col("child_class_name") == ClassEnum.Reserve.name)
            & (pl.col("parent_class_name") == ClassEnum.System.name)
        )

        for reserve_name, reserve_data in system_reserves.group_by("name"):
            reserve_name = reserve_name[0]
            logger.trace("Parsing reserve = {}", reserve_name)
            property_records = reserve_data.to_dicts()
            mapped_records, _ = self._parse_property_data(property_records)
            mapped_records["name"] = reserve_name
            reserve_type = validate_string(mapped_records.pop("Type", "default"))
            plexos_reserve_map = self.input_config.defaults["reserve_types"].get(
                str(reserve_type), self.input_config.defaults["reserve_types"]["default"]
            )  # Pass string so we do not need to convert the json mapping.
            mapped_records["reserve_type"] = ReserveType[plexos_reserve_map["type"]]
            mapped_records["direction"] = ReserveDirection[plexos_reserve_map["direction"]]

            # Service model uses all floats
            mapped_records["max_requirement"] = (
                get_property_magnitude(mapped_records.pop("max_requirement"))
                if mapped_records.get("max_requirement")
                else None
            )
            mapped_records["vors"] = mapped_records.pop("vors").magnitude

            if mapped_records.get("duration"):
                mapped_records["duration"] = mapped_records["duration"].magnitude
            if mapped_records["time_frame"].units == "second":
                mapped_records["time_frame"] = mapped_records["time_frame"].magnitude / 60
            else:
                mapped_records["time_frame"] = mapped_records["time_frame"].magnitude

            valid_fields, ext_data = field_filter(mapped_records, default_model.model_fields)
            valid_fields = prepare_ext_field(valid_fields, ext_data)

            # NOTE: Plexos has a property called `Is Enabled` that takes either 1 or -1.
            # Where -1 False (0) or True (-1)

            if "available" in valid_fields and valid_fields["available"] == -1:
                valid_fields["available"] = 1

            ts_fields = {k: v for k, v in mapped_records.items() if isinstance(v, SingleTimeSeries)}

            valid_fields.update(
                {
                    ts_name: get_property_magnitude(np.mean(ts.data))
                    for ts_name, ts in ts_fields.items()
                    if ts_name in valid_fields.keys()
                }
            )

            valid_fields = prepare_ext_field(valid_fields, ext_data)
            self.system.add_component(default_model(**valid_fields))

            if ts_fields:
                reserve = self.system.get_component_by_label(f"{default_model.__name__}.{reserve_name}")
                ts_dict = {"solve_year": self.year}
                for ts_name, ts in ts_fields.items():
                    ts.name = ts_name
                    self.system.add_time_series(ts, reserve, context=None, **ts_dict)

        reserve_map = ReserveMap(name="contributing_generators")
        self.system.add_component(reserve_map)
        return

    def _add_reserve_region_properties(self):
        region_reserve_filter = (pl.col("child_class_name") == ClassEnum.Region.value) & (
            pl.col("parent_class_name") == ClassEnum.Reserve.value
        )
        system_reserves = self._get_model_data(
            (pl.col("child_class_name") == ClassEnum.Reserve.name)
            & (pl.col("parent_class_name") == ClassEnum.System.name)
        )
        region_reserve_data = self._get_model_data(region_reserve_filter)
        for reserve_object_id, reserve_data in region_reserve_data.group_by("parent_object_id"):
            reserve_object_id = reserve_object_id[0]
            region_names = reserve_data["name"].unique().to_list()

            load_zone_name = set(
                component.load_zone.name
                for component in self.system.get_components(ACBus)
                if component.name in region_names
            )
            if len(load_zone_name) > 1:
                msg = "Buses have multiple load zones attached. Not supported."
                raise NotImplementedError(msg)
            if not len(reserve_data["property_value"].unique() == 1):
                msg = "Multiple property values not supported for Reserve regions."
                raise NotImplementedError
            property_records = reserve_data.to_dicts()
            mapped_records, _ = self._parse_property_data(property_records)

            reserve_name = (
                system_reserves.filter(pl.col("object_id") == reserve_object_id)["name"].unique().item()
            )
            reserve_object = self.system.get_component(Reserve, reserve_name)
            load_zone = self.system.get_component(LoadZone, next(iter(load_zone_name)))
            reserve_object.region = load_zone
            if mapped_records.get("load_risk"):
                reserve_object.load_risk = mapped_records["load_risk"]
        return

    def _construct_branches(self, default_model=MonitoredLine):
        logger.info("Creating lines")
        system_lines = (pl.col("child_class_name") == ClassEnum.Line.value) & (
            pl.col("parent_class_name") == ClassEnum.System.value
        )
        system_lines = self._get_model_data(system_lines)

        lines_pivot = system_lines.pivot(
            index=DEFAULT_INDEX,
            on="property_name",
            values="property_value",
            aggregate_function="first",
        )
        if lines_pivot.is_empty():
            logger.warning("No line objects found on the system.")
            return

        lines_pivot_memberships = self.db.get_object_memberships(
            *lines_pivot["name"].to_list(), class_enum=ClassEnum.Line
        )
        for line in lines_pivot.iter_rows(named=True):
            line_properties_mapped = {self.property_map.get(key, key): value for key, value in line.items()}
            line_properties_mapped["rating"] = line_properties_mapped.get("max_power_flow", 0.0)
            line_properties_mapped["flow_limits"] = FromTo_ToFrom(
                from_to=line_properties_mapped.pop("Max Flow", 0.0),
                to_from=line_properties_mapped.pop("Min Flow", 0.0),
            )

            if line_properties_mapped["rating"] is None:
                logger.warning("Skipping disabled line {}", line)
                continue

            valid_fields, ext_data = field_filter(line_properties_mapped, default_model.model_fields)

            from_bus_name = next(
                membership
                for membership in lines_pivot_memberships
                if (
                    membership["parent"] == line["name"]
                    and membership["parent_class_name"] == ClassEnum.Line.name
                    and membership["collection_name"].replace(" ", "") == CollectionEnum.NodeFrom.name
                )
            )["child"]
            from_bus = self.system.get_component(ACBus, from_bus_name)
            to_bus_name = next(
                membership
                for membership in lines_pivot_memberships
                if (
                    membership["parent"] == line["name"]
                    and membership["parent_class_name"] == ClassEnum.Line.name
                    and membership["collection_name"].replace(" ", "") == CollectionEnum.NodeTo.name
                )
            )["child"]
            to_bus = self.system.get_component(ACBus, to_bus_name)
            valid_fields["from_bus"] = from_bus
            valid_fields["to_bus"] = to_bus

            valid_fields = prepare_ext_field(valid_fields, ext_data)
            self.system.add_component(default_model(**valid_fields))
        return

    def _construct_transformers(self, default_model=Transformer2W):
        logger.info("Creating transformers")
        system_transformers = (pl.col("child_class_name") == ClassEnum.Transformer.value) & (
            pl.col("parent_class_name") == ClassEnum.System.value
        )
        system_transformers = self._get_model_data(system_transformers)
        transformer_pivot = system_transformers.pivot(
            index=DEFAULT_INDEX,
            on="property_name",
            values="property_value",
            aggregate_function="first",
        )
        if transformer_pivot.is_empty():
            logger.warning("No transformer objects found on the system.")
            return

        lines_pivot_memberships = self.db.get_object_memberships(
            *transformer_pivot["name"].to_list(), class_enum=ClassEnum.Transformer
        )
        for transformer in transformer_pivot.iter_rows(named=True):
            transformer_properties_mapped = {
                self.property_map.get(key, key): value for key, value in transformer.items()
            }
            transformer_properties_mapped["rating"] = transformer_properties_mapped.get(
                "max_active_power", 0.0
            )
            transformer_properties_mapped["rating_up"] = transformer_properties_mapped.pop(
                "max_power_flow", 0.0
            )
            transformer_properties_mapped["rating_down"] = transformer_properties_mapped.pop(
                "min_power_flow", 0.0
            )

            if transformer_properties_mapped["rating"] is None:
                logger.warning("Skipping disabled transformer {}", transformer)
                continue

            valid_fields, ext_data = field_filter(transformer_properties_mapped, default_model.model_fields)

            from_bus_name = next(
                membership
                for membership in lines_pivot_memberships
                if (
                    membership["parent"] == transformer["name"]
                    and membership["parent_class_name"] == ClassEnum.Transformer.name
                    and membership["collection"].replace(" ", "") == CollectionEnum.NodeFrom.name
                )
            )["child"]
            from_bus = self.system.get_component(ACBus, from_bus_name)
            to_bus_name = next(
                membership
                for membership in lines_pivot_memberships
                if (
                    membership["parent"] == transformer["name"]
                    and membership["parent_class_name"] == ClassEnum.Transformer.name
                    and membership["collection"].replace(" ", "") == CollectionEnum.NodeTo.name
                )
            )["child"]
            to_bus = self.system.get_component(ACBus, to_bus_name)
            valid_fields["from_bus"] = from_bus
            valid_fields["to_bus"] = to_bus

            valid_fields = prepare_ext_field(valid_fields, ext_data)
            self.system.add_component(default_model(**valid_fields))
        return

    def _infer_model_type(self, generator_name):
        inference_mapper = self.device_match_string
        generator_name_lower = generator_name.lower()
        for key, device_info in inference_mapper.items():
            if key in generator_name_lower:
                return device_info
        return None

    def _get_fuel_pmtype(
        self, generator_name, fuel_name: str | None = None, category: str | None = None
    ) -> dict[str, str]:
        """Return fuel prime mover combo based on priority.

        This function will return first a match using the generator name, then
        by fuel map and if not it will try to infer it using the generator name

        Returns
        -------
        dict
            Either an empty dictionary or a dictionary with fuel and prime mover type.
        """
        match_fuel_pmtype = (
            self.device_map.get(generator_name)
            or self.fuel_map.get(fuel_name)
            or self.category_map.get(category)
            or self._infer_model_type(generator_name)
        )
        if not match_fuel_pmtype:
            return {}

        msg = (
            "Mapping returned a different data structure. "
            f"Returned {type(match_fuel_pmtype)} and expected type dict."
        )
        assert isinstance(match_fuel_pmtype, dict), msg
        return match_fuel_pmtype

    def _get_model_type(self, fuel_pmtype: dict[str, str | None]) -> str:
        """Get model type for given pair of fuel and prime mover type.

        Notes
        -----
        We return an empty string if not match found since it is used for the
        getattr function. If you pass a None it does not work.

        Returns
        -------
        str
            Match found or Empty string if not match is found.
        """
        assert len(self.generator_models) < 1000, "Change the data structure. Fool."
        if fuel_pmtype is None:
            return ""
        for model, items in self.generator_models.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if item == fuel_pmtype:
                    return model
        return ""

    def _construct_generators(self):  # noqa: C901
        """Create Plexos generator objects."""
        logger.info("Creating generator objects")

        # Filter only generator objects that belong to the system
        # NOTE: Polars 1.1.0 can not make a comparisson between a Enum and a string column. If we convert the
        # Enum to string it works, but we might be able to change this in a near future if polars supports it.
        system_generators_filter = (pl.col("child_class_name") == str(ClassEnum.Generator)) & (
            pl.col("parent_class_name") == str(ClassEnum.System)
        )

        system_generators = self._get_model_data(system_generators_filter)
        if self.config.feature_flags.get("plexos-csv", None):
            system_generators.write_csv("generators.csv")

        # NOTE: The best way to identify the type of generator on Plexos is by reading the fuel
        fuel_query = f"""
        SELECT
            parent_object.name AS parent_object_name,
            child_object.name AS fuel_name
        FROM
            t_membership AS mem
            LEFT JOIN t_object AS child_object ON mem.child_object_id = child_object.object_id
            LEFT JOIN t_object AS parent_object ON mem.parent_object_id = parent_object.object_id
            LEFT JOIN t_class AS child_class ON child_object.class_id = child_class.class_id
            LEFT JOIN t_class AS parent_cls ON parent_object.class_id = parent_cls.class_id
        WHERE
            child_class.name = '{ClassEnum.Fuel}'
            AND parent_cls.name = '{ClassEnum.Generator}'
        """
        generator_fuel = self.db.query(fuel_query)
        generator_fuel_map = {key: value for key, value in generator_fuel}

        fuel_prices = self._get_fuel_prices()

        # Iterate over properties to create generator object
        for generator_name, generator_data in system_generators.group_by("name"):
            generator_name = generator_name[0]

            category = generator_data["category"].unique()
            object_id = generator_data["object_id"].unique().item()
            if len(category) > 1:
                msg = "Generator has more then one category. Check the dataset"
                logger.debug(msg)
            category = category[0]

            fuel_name = generator_fuel_map.get(generator_name)
            logger.trace("Parsing generator = {} with fuel type = {}", generator_name, fuel_name)

            fuel_pmtype = self._get_fuel_pmtype(generator_name, fuel_name=fuel_name, category=category)

            if not fuel_pmtype:
                msg = "Fuel mapping not found for {} with fuel_type={}"
                logger.warning(msg, generator_name, fuel_name)
                continue

            # We assume that if we find the fuel, there is a model_map
            model_map = self._get_model_type(fuel_pmtype)
            try:
                model_map = getattr(R2X_MODELS, model_map)
            except AttributeError:
                msg = (
                    f"Mapping {fuel_pmtype} does not have a corresponding generator model. "
                    "Check that the combination of fuel and type exist on the `generator_models`"
                )
                raise AttributeError(msg)

            # property_records = generator_data[DEFAULT_PROPERTY_COLUMNS].to_dicts()
            property_records = generator_data.to_dicts()

            mapped_records, multi_band_records = self._parse_property_data(property_records)
            mapped_records["name"] = generator_name

            # if multi_band_records:
            #     pass

            # Get prime mover enum
            mapped_records["prime_mover_type"] = fuel_pmtype["type"]
            mapped_records["prime_mover_type"] = PrimeMoversType[mapped_records["prime_mover_type"]]

            if issubclass(model_map, ThermalGen) and fuel_pmtype.get("fuel"):
                mapped_records["fuel"] = get_enum_from_string(fuel_pmtype["fuel"], ThermalFuels)

            # Pumped Storage generators are not required to have Max Capacity property
            if "max_active_power" not in mapped_records and "pump_load" in mapped_records:
                mapped_records["rating"] = mapped_records["pump_load"]

            mapped_records = self._set_unit_capacity(mapped_records)
            if model_map.__name__ == HydroPumpedStorage.__name__:
                mapped_records = self._get_storage_objects_attached(object_id, mapped_records)

                # NOTE: Some Plexos models mighy have different up and down capacities. We need to parse those
                # at some point as well.
                mapped_records["storage_capacity"] = UpDown(
                    up=mapped_records["storage_capacity"], down=mapped_records["storage_capacity"]
                )
            if mapped_records is None:
                logger.trace("Skipping disabled generator {}", generator_name)
                # When unit availability is not set, we skip the generator
                continue

            required_fields = {
                key: value for key, value in model_map.model_fields.items() if value.is_required()
            }
            if not all(key in mapped_records for key in required_fields):
                missing_fields = [key for key in required_fields if key not in mapped_records]
                logger.warning(
                    "Skipping generator {}. Missing Required Fields: {}", generator_name, missing_fields
                )
                continue

            if not mapped_records.get("fuel_price"):
                mapped_records["fuel_price"] = fuel_prices.get(generator_fuel_map.get(generator_name), 0.0)
            mapped_records = self._construct_operating_costs(mapped_records, generator_name, model_map)

            valid_fields, ext_data = field_filter(mapped_records, model_map.model_fields)

            ts_fields = {k: v for k, v in mapped_records.items() if isinstance(v, SingleTimeSeries)}

            valid_fields.update(
                {
                    ts_name: np.mean(ts.data)
                    for ts_name, ts in ts_fields.items()
                    if ts_name in valid_fields.keys()
                }
            )

            valid_fields = prepare_ext_field(valid_fields, ext_data)
            self.system.add_component(model_map(**valid_fields))
            generator = self.system.get_component_by_label(f"{model_map.__name__}.{generator_name}")

            if ts_fields:
                generator = self.system.get_component_by_label(f"{model_map.__name__}.{generator_name}")
                ts_dict = {"solve_year": self.year}
                for ts_name, ts in ts_fields.items():
                    ts.name = ts_name

                    # NOTE: This is fix to avoid mismatch with unit registry for custom units.
                    if isinstance(ts.data, Quantity):
                        # ts_dict["units"] = str(ts.data.units)
                        ts.data = ts.data.magnitude
                    self.system.add_time_series(ts, generator, **ts_dict)
        return

    def _get_storage_objects_attached(self, object_id: int, mapped_records: dict[str, Any]) -> dict[str, Any]:
        """Get head and tail objects for generators with Storage.

        Currently only works for PHS type of generator where the generator appears and it has a head and tail
        object attached to it.

        Notes
        -----
            If the head and tail have separate values, we just get the first occurence.
        """
        system_storage_filter = (pl.col("child_class_name") == str(ClassEnum.Storage)) & (
            pl.col("parent_class_name") == str(ClassEnum.System)
        )
        generator_storage_filter = (pl.col("child_class_name") == str(ClassEnum.Storage)) & (
            pl.col("parent_class_name") == str(ClassEnum.Generator)
        )
        storage_objects = self._get_model_data(generator_storage_filter).filter(
            pl.col("parent_object_id") == object_id
        )["object_id"]

        system_storage_data = self._get_model_data(system_storage_filter).filter(
            pl.col("object_id").is_in(storage_objects)
        )
        mapped_storage_records, ext_data = self._parse_property_data(system_storage_data.to_dicts())

        return mapped_storage_records | mapped_records

    def _add_buses_to_generators(self):
        # Add buses to generators
        generators = [generator["name"] for generator in self.system.to_records(Generator)]
        generator_memberships = self.db.get_object_memberships(
            *generators,
            class_enum=ClassEnum.Generator,
            collection_enum=CollectionEnum.Nodes,
        )
        for generator in self.system.get_components(Generator):
            buses = [
                membership for membership in generator_memberships if membership["parent"] == generator.name
            ]
            if buses:
                for bus in buses:
                    try:
                        bus_object = self.system.get_component(ACBus, name=bus["child"])
                    except ISNotStored:
                        logger.warning(
                            "Skipping membership for generator:{} since reserve {} is not stored",
                            generator.name,
                            buses["child"],
                        )
                        continue
                    generator.bus = bus_object
        return

    def _add_generator_reserves(self):
        reserve_map = self.system.get_component(ReserveMap, name="contributing_generators")
        generators = [generator["name"] for generator in self.system.to_records(Generator)]
        generator_memberships = self.db.get_object_memberships(
            *generators,
            class_enum=ClassEnum.Generator,
            parent_class_enum=ClassEnum.Reserve,
            collection_enum=CollectionEnum.Generators,
        )
        for generator in self.system.get_components(Generator):
            reserves = [
                membership for membership in generator_memberships if membership["child"] == generator.name
            ]
            if reserves:
                # NOTE: This would get replaced if we have a method on infrasys
                # that check if something exists on the system
                for reserve in reserves:
                    try:
                        reserve_object = self.system.get_component(Reserve, name=reserve["parent"])
                    except ISNotStored:
                        logger.warning(
                            "Skipping membership for generator:{} since reserve {} is not stored",
                            generator.name,
                            reserve["child"],
                        )
                        continue
                    reserve_map.mapping[reserve_object.name].append(generator.name)
        return

    def _construct_batteries(self):
        logger.info("Creating battery objects")
        system_batteries = self._get_model_data(
            (pl.col("child_class_name") == ClassEnum.Battery.name)
            & (pl.col("parent_class_name") == ClassEnum.System.name)
        )

        required_fields = {
            key: value for key, value in EnergyReservoirStorage.model_fields.items() if value.is_required()
        }

        for battery_name, battery_data in system_batteries.group_by("name"):
            battery_name = battery_name[0]
            logger.trace("Parsing battery = {}", battery_name)

            property_records = battery_data.to_dicts()

            mapped_records, _ = self._parse_property_data(property_records)
            mapped_records["name"] = battery_name
            mapped_records["prime_mover_type"] = PrimeMoversType.BA

            mapped_records = self._set_unit_capacity(mapped_records)
            if mapped_records is None:
                continue
            mapped_records["storage_technology_type"] = StorageTechs.OTHER_CHEM

            mapped_records["input_active_power_limits"] = MinMax(min=0, max=mapped_records["base_power"])
            mapped_records["output_active_power_limits"] = MinMax(min=0, max=mapped_records["base_power"])
            mapped_records["efficiency"] = InputOutput(
                input=mapped_records.get("charge_efficiency", 1),
                output=mapped_records.get("discharge_efficiency", 1),
            )

            valid_fields, ext_data = field_filter(mapped_records, EnergyReservoirStorage.model_fields)

            if not all(key in valid_fields for key in required_fields):
                missing_fields = [key for key in required_fields if key not in valid_fields]
                logger.warning(
                    "Skipping battery {}. Missing required fields: {}", battery_name, missing_fields
                )
                continue

            if mapped_records["storage_capacity"] == 0:
                logger.warning("Skipping battery {} since it has zero capacity", battery_name)
                continue

            valid_fields = prepare_ext_field(valid_fields, ext_data)
            self.system.add_component(EnergyReservoirStorage(**valid_fields))
        return

    def _add_buses_to_batteries(self):
        batteries = [battery["name"] for battery in self.system.to_records(EnergyReservoirStorage)]
        if not batteries:
            msg = "No battery objects found on the system. Skipping adding membership to buses"
            logger.warning(msg)
            return
        generator_memberships = self.db.get_object_memberships(
            *batteries,
            class_enum=ClassEnum.Battery,
            collection_enum=CollectionEnum.Nodes,
        )
        for component in self.system.get_components(EnergyReservoirStorage):
            buses = [
                membership for membership in generator_memberships if membership["parent"] == component.name
            ]
            if buses:
                for bus in buses:
                    try:
                        bus_object = self.system.get_component(ACBus, name=bus["child"])
                    except ISNotStored:
                        logger.warning(
                            "Skipping membership for battery:{} since bus {} is not stored",
                            component.name,
                            buses["child"],
                        )
                        continue
                    component.bus = bus_object
        return

    def _add_battery_reserves(self):
        reserve_map = self.system.get_component(ReserveMap, name="contributing_generators")
        batteries = [battery["name"] for battery in self.system.to_records(EnergyReservoirStorage)]
        if not batteries:
            msg = "No battery objects found on the system. Skipping adding reserve memberships"
            logger.warning(msg)
            return
        generator_memberships = self.db.get_object_memberships(
            *batteries,
            class_enum=ClassEnum.Battery,
            parent_class_enum=ClassEnum.Reserve,
            collection_enum=CollectionEnum.Batteries,
        )

        for battery in self.system.get_components(EnergyReservoirStorage):
            reserves = [
                membership for membership in generator_memberships if membership["child"] == battery.name
            ]
            if reserves:
                # NOTE: This would get replaced if we have a method on infrasys
                # that check if something exists on the system
                for reserve in reserves:
                    try:
                        reserve_object = self.system.get_component(Reserve, name=reserve["parent"])
                    except ISNotStored:
                        logger.warning(
                            "Skipping membership for generator:{} since reserve {} is not stored",
                            battery.name,
                            reserve["parent"],
                        )
                        continue
                    reserve_map.mapping[reserve_object.name].append(battery.name)
        return

    def _construct_interfaces(self, default_model=TransmissionInterface):
        """Construct Transmission Interface and Transmission Interface Map."""
        logger.info("Creating transmission interfaces")
        system_interfaces_mask = (pl.col("child_class_name") == ClassEnum.Interface.name) & (
            pl.col("parent_class_name") == ClassEnum.System.name
        )
        system_interfaces = self._get_model_data(system_interfaces_mask)
        interfaces = system_interfaces.pivot(
            index=DEFAULT_INDEX,
            on="property_name",
            values="property_value",
            aggregate_function="first",
        )

        interface_property_map = {
            v: k
            for k, v in self.input_config.defaults["plexos_input_property_map"].items()
            if k in default_model.model_fields
        }

        tx_interface_map = TransmissionInterfaceMap(name="transmission_map")
        for interface in interfaces.iter_rows(named=True):
            mapped_interface = {
                interface_property_map.get(key, key): value for key, value in interface.items()
            }
            valid_fields, ext_data = field_filter(mapped_interface, default_model.model_fields)

            # Add flow limits
            if "Max Flow" in mapped_interface:
                valid_fields["active_power_flow_limits"] = MinMax(
                    min=mapped_interface.get("Min Flow", 0.0), max=mapped_interface["Max Flow"]
                )

            # NOTE: TransmissionInterface require a direction mapping. This basically says the direction of
            # the flow to each of the lines contributing to the interface.
            valid_fields["direction_mapping"] = {}

            # Check that the interface has all the required fields of the model.
            required_fields = {
                key: value for key, value in default_model.model_fields.items() if value.is_required()
            }
            if not all(key in valid_fields for key in required_fields):
                missing_fields = [key for key in required_fields if key not in mapped_interface]
                logger.warning(
                    "{}:{} missing required fields: {}. Skipping it.",
                    default_model.__name__,
                    interface["name"],
                    missing_fields,
                )
                continue

            valid_fields = prepare_ext_field(valid_fields, ext_data)
            self.system.add_component(default_model(**valid_fields))

        # Add lines memberships
        lines = [line["name"] for line in self.system.to_records(MonitoredLine)]
        if not lines:
            return
        lines_memberships = self.db.get_object_memberships(
            *lines,
            class_enum=ClassEnum.Line,
            parent_class_enum=ClassEnum.Interface,
            collection_enum=CollectionEnum.Lines,
        )
        for line in self.system.get_components(MonitoredLine):
            interface = next(
                (membership for membership in lines_memberships if membership["child"] == line.name), None
            )
            if interface:
                # NOTE: This would get replaced if we have a method on infrasys
                # that check if something exists on the system
                try:
                    interface_object = self.system.get_component(
                        TransmissionInterface, name=interface["parent"]
                    )
                except ISNotStored:
                    logger.warning(
                        "Skipping membership for line:{} since interface {} is not stored",
                        line.name,
                        interface["parent"],
                    )
                    continue
                tx_interface_map.mapping[interface_object.name].append(line.label)
        self.system.add_component(tx_interface_map)
        return

    def _construct_value_curves(self, record, generator_name):  # noqa: C901
        """Construct value curves for generators."""
        if not any("Heat Rate" in key or "heat_rate" in key for key in record.keys()):
            return None
        vc = None
        heat_rate_avg = record.get("heat_rate", None)
        heat_rate_base = record.get("Heat Rate Base", None)
        heat_rate_incr = record.get("Heat Rate Incr", None)
        heat_rate_incr2 = record.get("Heat Rate Incr2", None)

        if any(isinstance(val, SingleTimeSeries) for val in [heat_rate_avg, heat_rate_base, heat_rate_incr]):
            logger.warning(
                "Time-varying heat-rates not implemented for generator={}. Using median value instead",
                generator_name,
            )

        heat_rate_avg = (
            Quantity(
                np.median(heat_rate_avg.data),
                units=heat_rate_avg.data.units,
            )
            if isinstance(heat_rate_avg, SingleTimeSeries)
            else heat_rate_avg
        )
        heat_rate_base = (
            Quantity(
                np.median(heat_rate_base.data),
                units=heat_rate_base.data.units,
            )
            if isinstance(heat_rate_base, SingleTimeSeries)
            else heat_rate_base
        )
        heat_rate_incr = (
            Quantity(
                np.median(heat_rate_incr.data),
                units=heat_rate_incr.data.units,
            )
            if isinstance(heat_rate_incr, SingleTimeSeries)
            else heat_rate_incr
        )

        if heat_rate_incr and heat_rate_incr.units == "british_thermal_unit / kilowatt_hour":
            heat_rate_incr = Quantity(heat_rate_incr.magnitude * 1e-3, "british_thermal_unit / watt_hour")

        if (
            heat_rate_avg
            and isinstance(heat_rate_avg, Quantity)
            and heat_rate_avg.units == "british_thermal_unit / kilowatt_hour"
        ):
            heat_rate_avg = Quantity(heat_rate_avg.magnitude * 1e-3, "british_thermal_unit / watt_hour")

        if heat_rate_avg:
            fn = LinearFunctionData(proportional_term=heat_rate_avg.magnitude, constant_term=0)
            vc = AverageRateCurve(
                function_data=fn,
                initial_input=heat_rate_avg.magnitude,
            )
        elif heat_rate_incr2 and "** 2" in str(heat_rate_incr2.units):
            fn = QuadraticFunctionData(
                quadratic_term=heat_rate_incr2.magnitude,
                proportional_term=heat_rate_incr.magnitude,
                constant_term=heat_rate_base.magnitude,
            )
            if self.config.feature_flags.get("quad2pwl", None):
                n_tranches = self.config.feature_flags.get("quad2pwl", None)
                fn = construct_pwl_from_quadtratic(fn, record, n_tranches)
        elif not heat_rate_incr2 and heat_rate_incr:
            fn = LinearFunctionData(
                proportional_term=heat_rate_incr.magnitude, constant_term=heat_rate_base.magnitude
            )
        else:
            logger.warning("Heat Rate type not implemented for generator={}", generator_name)
            fn = None

        if not vc and fn:
            vc = InputOutputCurve(function_data=fn)
        if not vc and fn is None:
            vc = LinearCurve(0)
        return vc

    def _construct_operating_costs(self, mapped_records, generator_name, model_map):
        """Construct operating costs from Value Curves and Operating Costs."""
        vom_cost = mapped_records.get("vom_price", 0.0)
        if isinstance(vom_cost, Quantity):
            vom_cost = vom_cost.magnitude

        if issubclass(model_map, RenewableGen):
            mapped_records["operation_cost"] = RenewableGenerationCost()
        elif issubclass(model_map, ThermalGen):
            heat_rate_curve = self._construct_value_curves(mapped_records, generator_name)
            fuel_cost = mapped_records.get("fuel_price", 0)
            if isinstance(fuel_cost, SingleTimeSeries) and isinstance(fuel_cost.data, Quantity):
                fuel_cost = np.mean(fuel_cost.data.magnitude)
            elif isinstance(fuel_cost, Quantity):
                fuel_cost = fuel_cost.magnitude
            if heat_rate_curve:
                cost_curve = FuelCurve(
                    value_curve=heat_rate_curve, fuel_cost=fuel_cost, power_units=UnitSystem.NATURAL_UNITS
                )
            else:
                cost_curve = CostCurve(
                    value_curve=LinearCurve(0),
                    vom_cost=LinearCurve(vom_cost),
                    power_units=UnitSystem.NATURAL_UNITS,
                )
            mapped_records["operation_cost"] = ThermalGenerationCost(
                variable=cost_curve,
                start_up=mapped_records.get("startup_cost", 0),
            )
        elif issubclass(model_map, HydroDispatch):
            mapped_records["operation_cost"] = HydroGenerationCost()
        else:
            logger.debug(
                "Operating cost parsing not implemented for generator={} model map={}",
                generator_name,
                model_map,
            )

        mapped_records["vom_price"] = mapped_records.get("vom_price", 0)
        return mapped_records

    def _select_model_name(self):
        # TODO(pesap): Handle exception if no model name found
        # https://github.com/NREL/R2X/issues/10
        query = f"""
        select obj.name
        from t_object as obj
        left join t_class as cls on obj.class_id = cls.class_id
        where cls.name = '{ClassEnum.Model.name}'
        """
        result = self.db.query(query)
        model_names = [row[0] for row in result]

        print("Available models:")
        for idx, name in enumerate(model_names):
            print(f"{idx + 1}. {name}")

        while True:
            try:
                choice = int(input("Select a model by number: "))
                if 1 <= choice <= len(model_names):
                    return model_names[choice - 1]
                else:
                    print(f"Please enter a number between 1 and {len(model_names)}.")
            except ValueError:
                print("Invalid input. Please enter a number.")

    def _process_scenarios(self, model_name: str | None = None) -> None:
        """Create a SQLite representation of the XML."""
        if model_name is None:
            msg = "Required model name not found. Parser requires a model to parse from the Plexos database"
            raise R2XModelError(msg)
        # self.db = PlexosDB(xml_fname=xml_fpath)

        logger.trace("Getting object_id for model={}", model_name)
        model_id_query = """
        SELECT
            object_id
        FROM
            t_object
        LEFT JOIN
            t_class on t_class.class_id = t_object.class_id
        WHERE t_object.name = ? and t_class.name = ?
        """
        model_id = self.db.query(
            model_id_query,
            params=(model_name, ClassEnum.Model),
        )
        if len(model_id) > 1:
            msg = f"Multiple models with the same {model_name} returned. Check database or spelling."
            logger.debug(model_id)
            raise R2XModelError(msg)
        if not model_id:
            msg = f"Model `{model_name}` not found on the XML. Check spelling of the `model_name`."
            raise R2XParserError(msg)
        self.model_id = model_id[0][0]  # Unpacking tuple [(model_id,)]

        # NOTE: When doing performance updates this query could get some love.
        valid_scenarios = self.db.query(
            "select obj.name from t_membership mem "
            "left join t_object as obj on obj.object_id = mem.child_object_id "
            "left join t_class as cls on cls.class_id = obj.class_id "
            f"where mem.parent_object_id = {self.model_id} and cls.name = '{ClassEnum.Scenario}'"
        )
        valid_scenarios_query = """
        SELECT
            t_object.name
        FROM
            t_membership as membership
        LEFT JOIN
            t_object on t_object.object_id = membership.child_object_id
        LEFT JOIN
            t_class on t_object.class_id = t_class.class_id
        WHERE
            membership.parent_object_id = ? and
            t_class.name = ?
        """
        valid_scenarios = self.db.query(
            valid_scenarios_query,
            params=(self.model_id, ClassEnum.Scenario),
        )
        if not valid_scenarios:
            msg = f"{model_name=} does not have any scenario attached to it."
            logger.warning(msg)
            return
        assert valid_scenarios
        self.scenarios = [scenario[0] for scenario in valid_scenarios]  # Flatten list of tuples
        return None

    def _set_unit_capacity(self, record):  # noqa: C901
        """Set availability and active power limit TS for generators.

        Plexos does not have a property for base_power (MW) instead it defines it as Max Capacity. In some
        cases, users will derate this Max Capacity using the Rating property which overrules the Max
        Capacity and it becomes the new max_active_power of the generator. This property can be defined as a
        single value or a value that changes by pattern or a time series. If defined as a time series, we
        take the get the maximum active power limits.

        If the Rating property exist and is not defined for the entire time series, Plexos assumes that the
        times not covered the Rating = 0.

        Plexos allows to define a Rating Factor that is expressed as percentage of of the Max Capacity or
        Rating if it is defined. If this property is active, we update the active_power_limits to match the
        new rating.

        Plexos models multiple generators by changing the units attributes (that gets translated to
        available here). If the `available` key is 0, it means that the unit is deactivated from the model or
        retired. If it is 1, it means a single unit that is active.

        Notes
        -----
        At this point of the code, all the properties should be either a single value, or a `SingleTimeSeries`
        """
        if not (availability := record.get("available")):
            logger.debug("Unit `{}` is not activated on the model.", record["name"])
            return
        record["active_power_limits"] = self._get_active_power_limits(record)

        # Set availability, rating, storage_capacity as multiplier of availability/'units'
        if (
            record.get("storage_capacity") is not None
            and not isinstance(record.get("available"), SingleTimeSeries)
            and availability > 1
        ):
            record["storage_capacity"] *= availability

        # If we have Rating, we need to re-adjust the max_active_power and the active_power limits
        # Rating can be either a single number or a time series.
        if rating := record.get("rating"):
            if isinstance(rating, SingleTimeSeries):
                rating = rating.data
                if rating.units == "percent":
                    rating = rating.to("")
                # We override the max active power to the max rating
                record["max_active_power"] = np.nanmax(rating)
                record["active_power_limits_max"] = np.nanmax(rating)
            else:
                record["max_active_power"] = rating * availability
                record["active_power_limits_max"] = rating * availability

        # If we have rating factor we apply it to the max_active power
        # NOTE: There could be cases where the Rating Factor applies to the rating instead of the Max
        # Capacity. For those cases, we will need to re-adjust this function.
        if rating_factor := record.get("Rating Factor"):
            if isinstance(rating_factor, SingleTimeSeries):
                rating_factor_data = rating_factor.data
                if rating_factor_data.units == "percent":
                    rating_factor_data = rating_factor_data.to("")
                if not (max_active_power := record.get("max_active_power")):
                    # Order of the operation matters
                    record["max_active_power"] = availability * record["base_power"] * rating_factor_data
                else:
                    record["max_active_power"] = availability * max_active_power.data * rating_factor_data
                if not isinstance(record["max_active_power"], SingleTimeSeries):
                    record["max_active_power"] = SingleTimeSeries.from_array(
                        record["max_active_power"].data,
                        name="max_active_power",
                        initial_timestamp=rating_factor.initial_timestamp,
                        resolution=rating_factor.resolution,
                    )
            else:
                record["max_active_power"] = rating_factor * record["base_power"] * availability

        # Since we use available as if the unit is active or not, we need to set it back to 1
        record["available"] = 1

        return record

    def _get_active_power_limits(self, record) -> MinMax:
        # assert record["base_power"] is not None
        if active_power_min := record.get("min_rated_capacity"):
            if isinstance(active_power_min, SingleTimeSeries):
                active_power_min = np.nanmin(active_power_min.data)
        active_power_limits_min = active_power_min or 0.0

        if active_power_max := record.get("max_active_power"):
            if isinstance(active_power_max, SingleTimeSeries):
                active_power_max = np.nanmax(active_power_max.data)
        active_power_limits_max = (active_power_max or record["base_power"]) * record["available"]
        return MinMax(min=active_power_limits_min, max=active_power_limits_max)

    def _plexos_table_data(self) -> list[tuple]:
        sql_query = get_sql_query("simple_object_query.sql")
        object_data = self.db.query(sql_query)
        return object_data

    def _polarize_data(self, object_data: list[tuple]) -> pl.DataFrame:
        data = pl.from_records(object_data, schema=SIMPLE_QUERY_COLUMNS_SCHEMA)

        # Filtering Variables to select only the correct band-id which should be used
        # when accessing Variable data. We may also need to apply this filtering to
        # other Enum classes.
        variables = data.filter(
            (pl.col("child_class_name") == ClassEnum.Variable.name)
            & (pl.col("parent_class_name") == ClassEnum.System.name)
        )
        if not variables.is_empty():
            variables = variables.group_by("object_id", maintain_order=True).map_groups(
                lambda groupdf: groupdf.filter(pl.col("band") == pl.col("band").min())
            )

            data = data.filter(pl.col("child_class_name") != ClassEnum.Variable.name)
            data = pl.concat([data, variables])

        # Create a lookup map to find nested objects easily
        object_map = data.select(["object_id", "tag_datafile", "tag_datafile_object_id"]).to_dict(
            as_series=False
        )

        self.id_to_name = dict(zip(object_map["object_id"], object_map["tag_datafile"]))
        self.id_to_tag_id = dict(zip(object_map["object_id"], object_map["tag_datafile_object_id"]))
        return data

    def _get_model_data(self, data_filter) -> pl.DataFrame:
        """Filter plexos data for a given class and all scenarios in a model."""
        assert isinstance(self.year, int)
        scenario_specific_data = None
        scenario_filter = None
        if getattr(self, "scenarios", None):
            scenario_filter = pl.col("scenario").is_in(self.scenarios)
            scenario_specific_data = self.plexos_data.filter(data_filter & scenario_filter)
            scenario_specific_data = filter_property_dates(scenario_specific_data, self.year)

        base_case_filter = pl.col("scenario").is_null()
        # Default is to parse data normally if there is not scenario. If scenario exist modify the filter.
        if scenario_specific_data is None:
            system_data = self.plexos_data.filter(data_filter & base_case_filter)
            system_data = filter_property_dates(system_data, self.year)
        else:
            # include both scenario specific and basecase data
            combined_key_base = pl.col("name") + "_" + pl.col("property_name")
            combined_key_scenario = (
                scenario_specific_data["name"] + "_" + scenario_specific_data["property_name"]
            )

            base_case_filter = base_case_filter & (
                ~combined_key_base.is_in(combined_key_scenario) | pl.col("property_name").is_null()
            )
            base_case_data = self.plexos_data.filter(data_filter & base_case_filter)
            base_case_data = filter_property_dates(base_case_data, self.year)

            system_data = pl.concat([scenario_specific_data, base_case_data])

        # If date_from / date_to is specified, override the base_case_value
        rows_to_keep = system_data.filter(pl.col("date_from").is_not_null() | pl.col("date_to").is_not_null())
        rtk_key = rows_to_keep["name"] + "_" + rows_to_keep["property_name"]
        sys_data_key = system_data["name"] + "_" + system_data["property_name"]
        if not rows_to_keep.is_empty():
            # remove if name and property_name are the same
            system_data = system_data.filter(~sys_data_key.is_in(rtk_key))
            system_data = pl.concat([system_data, rows_to_keep])

        return system_data

    def _construct_load_profiles(self):
        logger.info("Creating load profile time series")
        system_regions = (pl.col("child_class_name") == ClassEnum.Region.name) & (
            pl.col("parent_class_name") == ClassEnum.System.name
        )
        regions = self._get_model_data(system_regions)
        for region, region_data in regions.group_by("name"):
            property_records = region_data.to_dicts()
            mapped_records, _ = self._parse_property_data(property_records)

            if max_active_power := mapped_records.get("max_active_power"):
                max_load = (
                    np.nanmax(max_active_power.data)
                    if isinstance(max_active_power, SingleTimeSeries)
                    else max_active_power
                )
            else:
                continue
            bus_region_membership = self.db.get_object_memberships(
                region[0],
                class_enum=ClassEnum.Region,
                parent_class_enum=ClassEnum.Node,
                collection_enum=CollectionEnum.Region,
            )
            for bus in bus_region_membership:
                bus = self.system.get_component(ACBus, name=bus["parent"])
                load = PowerLoad(name=f"{bus.name}", bus=bus, max_active_power=max_load)
                self.system.add_component(load)
                ts_dict = {"solve_year": self.year}
                if isinstance(max_active_power, SingleTimeSeries):
                    self.system.add_time_series(max_active_power, load, **ts_dict)
        return

    def _data_file_reader(self, fpath_str: str, csv_file_encoding="utf8"):
        path = self.run_folder / Path(fpath_str)
        if "\\" in fpath_str:
            path = self.run_folder / PureWindowsPath(fpath_str)

        if path in self._data_file_cache:
            return path, self._data_file_cache[path], self._data_file_column_types[path]

        if encoding := self.config.feature_flags.get("csv_file_encoding"):
            csv_file_encoding = encoding

        data_file = csv_handler(path, csv_file_encoding=csv_file_encoding)

        column_type: DATAFILE_COLUMNS | None = get_column_enum(data_file.columns)
        if column_type is None:
            msg = f"Could not parse {path}. Time series format {data_file.columns=} not yet supported."
            raise NotImplementedError(msg)

        parsed_file = parse_data_file(column_type, data_file)

        if "year" in parsed_file.columns:
            parsed_file = pl_filter_by_year(parsed_file, year=self.year)

            if parsed_file.is_empty():
                logger.warning("No time series data specified for year filter. Year passed {}", self.year)

        if path not in self._data_file_cache:
            self._data_file_cache[path] = parsed_file
            self._data_file_column_types[path] = column_type

        return path, parsed_file, column_type

    def _data_file_handler(
        self,
        record_name: str,
        property_name: str,
        fpath_str: str,
        variable_name: str | None = None,
        csv_file_encoding: str = "utf8",
    ):
        """Read time varying data from a data file."""
        assert isinstance(self.year, int)
        path, parsed_file, column_type = self._data_file_reader(fpath_str)

        if "name" in parsed_file.columns:
            cols = [col.lower() for col in [record_name, property_name, variable_name] if col]
            parsed_file = parsed_file.filter(pl.col("name").str.to_lowercase().is_in(cols))

        if record_name in parsed_file.columns:
            parsed_file = parsed_file.fiter(pl.col(record_name))

        if parsed_file.is_empty():
            msg = "Could not find record_name = {} or property_name = {} in fpath = {}. Check data file."
            logger.warning(msg, record_name, property_name, path)
            return

        single_value = self._get_single_value(parsed_file, record_name, property_name, variable_name)
        if single_value is not None:
            return single_value

        if _ := self.config.feature_flags.get("simplify-heat-rate") and property_name == "Heat Rate":
            logger.debug("Simplified time series heat rate for {}", record_name)
            return parsed_file["value"].median()

        # PATCH: It is not common to have a Max Capacity time series. But if it is the case, we just get the
        # median as well
        if property_name == "Max Capacity":
            logger.trace("Simplified Max Capacity time series for {}", record_name)
            return parsed_file["value"].median()

        if "year" not in parsed_file.columns:
            parsed_file = parsed_file.with_columns(year=self.year)

        columns_to_check = self._create_columns_to_check(column_type)

        if not parsed_file.filter(parsed_file.select(columns_to_check).is_duplicated()).is_empty():
            logger.debug("File {} has duplicated rows. Removing duplicates.", path)
            parsed_file = parsed_file.unique(subset=columns_to_check).sort(pl.all())

        # We reconcile the time series data using the hourly time stamp given by the solve year

        parsed_file = reconcile_timeseries(parsed_file, hourly_time_index=self.hourly_time_index)
        assert "value" in parsed_file.columns, (
            f"Error: column value not found on time series file for {record_name}:{property_name}"
        )
        return parsed_file["value"].cast(pl.Float64).to_numpy()

    def _create_columns_to_check(self, column_type: DATAFILE_COLUMNS):
        # NOTE: Some files might have duplicated data. If so, we warn the user and drop the duplicates.
        columns_to_check = [
            column
            for column in column_type.value
            if column
            in [
                "Name",
                "name",
                "pattern",
                "year",
                "datetime",
                "DateTime",
                "month",
                "day",
                "period",
                "hour",
            ]
        ]
        if (
            column_type == DATAFILE_COLUMNS.TS_YMDH
            or column_type == DATAFILE_COLUMNS.TS_NMDH
            or column_type == DATAFILE_COLUMNS.TS_NMCDH
            or column_type == DATAFILE_COLUMNS.TS_NYMDH
        ):
            columns_to_check.append("hour")
        if column_type == DATAFILE_COLUMNS.TS_NM or column_type == DATAFILE_COLUMNS.TS_NMCDH:
            columns_to_check.append("month")
        if column_type == DATAFILE_COLUMNS.TS_NMCDH:
            columns_to_check.append("day")
        return columns_to_check

    def _get_single_value(
        self,
        parsed_file: pl.DataFrame,
        record_name: str,
        property_name: str,
        variable_name: str | None = None,
    ) -> float | None:
        """Return a single value from the parsed file if it matches certain conditions."""
        if not len(parsed_file) == 1:
            return None

        # Return if there is only a value column specified
        if "value" in parsed_file.columns:
            return parsed_file["value"][0]

        if property_name.lower() in parsed_file.columns:
            return parsed_file[property_name.lower()][0]

        names_to_check = [name for name in (record_name, property_name, variable_name) if name]
        if any(name.lower() in parsed_file["name"] for name in names_to_check):
            return parsed_file["value"][0]
        return None

    def _parse_value(self, value: Any, variable_name: str | None = None, unit: str | None = None):
        """Return appropiate value with units if passed."""
        if not isinstance(value, np.ndarray | Sequence):
            return value * ureg.Unit(unit) if unit else value

        assert isinstance(self.year, int)
        assert variable_name
        initial_time = datetime(self.year, 1, 1)
        resolution = timedelta(hours=1)

        return SingleTimeSeries(
            data=ureg.Quantity(value, unit) if unit else value,  # type: ignore
            name=variable_name,
            initial_timestamp=initial_time,
            resolution=resolution,
        )

    def _apply_action(self, action, val_a, val_b):
        val_a_data = val_a.data if isinstance(val_a, SingleTimeSeries) else val_a
        val_b_data = val_b.data if isinstance(val_b, SingleTimeSeries) else val_b

        results = action(val_a_data, val_b_data)
        if isinstance(val_a, SingleTimeSeries):
            val_a.data = results
            return val_a
        if isinstance(val_b, SingleTimeSeries):
            val_b.data = results
            return val_b
        return results

    def _parse_property_data(self, record_data: list[dict[str, Any]]):
        mapped_properties = {}
        property_counts: dict[str, Any] = {}
        multi_band_properties = set()
        timeslice_properties = set()
        unit = None
        mapped_property_name = None
        property_unit_map = {}

        for record in record_data:
            band = record["band"]
            prop_name = record["property_name"]
            prop_value = record["property_value"]
            timeslice = record["tag_timeslice"]
            unit = record["property_unit"].replace("$", "usd") if record["property_unit"] else None
            mapped_property_name = self.property_map.get(prop_name, prop_name)
            unit = get_pint_unit(unit)
            property_unit_map[mapped_property_name] = unit
            value = self._handle_record(record, prop_name, prop_value, unit)

            if mapped_property_name not in property_counts:
                mapped_properties[mapped_property_name] = value
                property_counts[mapped_property_name] = {band}
                property_counts[mapped_property_name] = {
                    "count": 1,
                    "bands": {band},
                    "timeslices": {timeslice},
                    "values": {band: {timeslice: value}},  # Store values by band and timeslice
                }
            else:
                property_counts[mapped_property_name]["count"] += 1
                property_counts[mapped_property_name]["bands"].add(band)
                property_counts[mapped_property_name]["timeslices"].add(timeslice)

                # Capture the value for multi-band/multi-timeslice
                if band not in property_counts[mapped_property_name]["values"]:
                    property_counts[mapped_property_name]["values"][band] = {}
                property_counts[mapped_property_name]["values"][band][timeslice] = value

                # Handle multi-band and multi-timeslice cases
                if len(property_counts[mapped_property_name]["bands"]) > 1:
                    multi_band_properties.add(mapped_property_name)
                if len(property_counts[mapped_property_name]["timeslices"]) > 1:
                    timeslice_properties.add(mapped_property_name)

                mapped_properties[mapped_property_name] = value
        if timeslice_properties:
            for property in timeslice_properties:
                property_with_timeslice = property_counts[property]
                pattern_values = []
                for timeslice in property_with_timeslice["timeslices"]:
                    timeslice_object_id = self.db.get_object_id(ClassEnum.Timeslice, name=timeslice)
                    timeslice_data = self._filter_by_object_id(timeslice_object_id)
                    pattern_values.append(
                        {
                            "pattern": timeslice_data["text"][0],
                            "value": property_with_timeslice["values"][1][
                                timeslice
                            ],  # 1 since we only assume single band timeslices
                        }
                    )
                mapped_properties[property] = self._parse_value(
                    time_slice_handler(pattern_values, self.hourly_time_index),
                    property,
                    unit=property_unit_map[property],
                )
        return mapped_properties, multi_band_properties

    def _handle_record(self, record: dict[str, Any], prop_name, prop_value, unit):  # noqa: C901
        """Handle record data.

        Possible cases:
        1. The record has a property value withouth any text, tag_timeslice, tag_variable, tag_datafile

        Possible time series cases:
        1. A Data File is defined for a property as a text
        2. A Data File is defined for a property as a tag with a nested DataFile

        Possible timeslice cases values:
        1. A time slice is defined for a property as a text,
        2. A time slice is defined for a property as a tag with a nested time slice,

        Possible variable cases values. Not that variable needs to have knowdlege of the action
        1. A variable is defined for a property as a tag with a time slice,
        2. A variable is defined for a property as a tag with a data file
        3. A variable is defined for a property as a tag with a nested data file
        4. A variable is defined for a property as a text with a data file
        5. A variable is defined for a property as a text with a nested data file
        """
        action = PLEXOS_ACTION_MAP.get(record["action"], None) if record.get("action") else None
        mapped_property_name = self.property_map.get(prop_name, prop_name)
        match record:
            case {"text": None, "tag_timeslice": None, "tag_datafile": None, "tag_variable": None}:
                logger.trace("Parsing standard property")
                value = self._parse_value(prop_value, unit=unit)
            case {"text": str(), "text_class_name": ClassEnum.DataFile}:
                data_file_value = self._data_file_handler(record["name"], prop_name, record["text"])
                if data_file_value is None:
                    data_file_value = prop_value
                value = self._parse_value(
                    value=data_file_value, variable_name=mapped_property_name, unit=unit
                )
            case {"text": str(), "text_class_name": ClassEnum.Variable}:
                nested_object_id = self.db.get_object_id(ClassEnum.Variable, name=record["text"])
                nested_object_data = self._get_nested_object_data(nested_object_id)
                if isinstance(nested_object_data, str):
                    value = (
                        self._data_file_handler(
                            record_name=record["name"],
                            property_name=prop_name,
                            fpath_str=nested_object_data,
                            variable_name=record["text"],
                        )
                        or prop_value
                    )
                else:
                    value = nested_object_data
                if action:
                    value = self._apply_action(action, prop_value, value)
                value = self._parse_value(value, variable_name=mapped_property_name, unit=unit)

            # This case covers when the variable is used to scale a property that is nested on a data file
            case {"tag_datafile": str(), "tag_variable": str()}:
                nested_object_id = self.db.get_object_id(ClassEnum.Variable, name=record["tag_variable"])
                nested_object_data = self._get_nested_object_data(nested_object_id)
                if isinstance(nested_object_data, str):
                    nested_object_data = self._data_file_handler(
                        record_name=record["name"],
                        property_name=prop_name,
                        fpath_str=nested_object_data,
                        variable_name=record["tag_variable"],
                    )
                record["text"] = self._get_nested_object_data(record["tag_datafile_object_id"])
                data_file_value = self._data_file_handler(
                    record["name"], prop_name, fpath_str=str(record["text"])
                )
                if data_file_value is None:
                    data_file_value = prop_value
                value = self._apply_action(action, data_file_value, nested_object_data)
                value = self._parse_value(value, variable_name=mapped_property_name, unit=unit)
            case {"tag_datafile": str()}:
                record["text"] = self._get_nested_object_data(record["tag_datafile_object_id"])
                data_file_value = self._data_file_handler(
                    record["name"], prop_name, fpath_str=str(record["text"])
                )
                if data_file_value is None:
                    data_file_value = prop_value
                value = self._parse_value(data_file_value, variable_name=mapped_property_name, unit=unit)
            case {"tag_variable": str()}:
                nested_object_id = self.db.get_object_id(ClassEnum.Variable, name=record["tag_variable"])
                nested_object_data = self._get_nested_object_data(nested_object_id)
                if isinstance(nested_object_data, str):
                    value = self._data_file_handler(
                        record_name=record["name"],
                        property_name=prop_name,
                        fpath_str=nested_object_data,
                        variable_name=record["tag_variable"],
                    )
                else:
                    value = nested_object_data
                if action:
                    value = self._apply_action(action, prop_value, value)
                value = self._parse_value(value, variable_name=mapped_property_name, unit=unit)

            case {"tag_timeslice": str()}:
                value = self._parse_value(prop_value, variable_name=mapped_property_name, unit=unit)
            case _:
                msg = f"Record format class not yet supported. {record=}"
                raise NotImplementedError(msg)

        return value

    def _resolve_object_id(self, object_id: int) -> int:
        """Recursively resolve the object ID by following the tag_object_id when tag_object_name is defined.

        Parameters
        ----------
        object_id : int
            The initial object ID to resolve.

        Returns
        -------
        int
            The resolved object ID that does not have a tag_object_name.
        """
        assert self.id_to_name
        assert self.id_to_tag_id
        while True:
            tag_object_name = self.id_to_name.get(object_id)
            if tag_object_name is None:
                return object_id

            object_id = self.id_to_tag_id[object_id]

    def _filter_by_object_id(self, object_id: int) -> pl.DataFrame:
        """Filter the DataFrame to return rows that match the specified object_id.

        Parameters
        ----------
        object_id : int
            The object ID to filter the DataFrame by.

        Returns
        -------
        pl.DataFrame
            A filtered DataFrame containing only rows where the object_id matches.
        """
        assert hasattr(self, "plexos_data"), "plexos data not processed yet"
        return self._get_model_data(pl.col("object_id") == object_id)

    def _get_nested_object_data(self, object_id: int) -> str | float | np.ndarray:
        assert object_id
        logger.trace("Unnesting nested object", object_id)
        nested_object_id = self._resolve_object_id(object_id)
        nested_object_data = self._filter_by_object_id(nested_object_id)
        nested_object_records = nested_object_data.to_dicts()
        if len(nested_object_records) > 1:
            logger.warning("Multiple nested objects")
            key_str = "text_class_name"
            if all(
                record.get(key_str) == ClassEnum.Timeslice
                for record in nested_object_records
                if key_str in record
            ):
                property_unit = {record["property_unit"] for record in nested_object_records}
                if len(property_unit) > 1:
                    raise NotImplementedError

                unit = get_pint_unit(property_unit.pop())
                timeslice_patterns = [
                    {"pattern": record.get("text"), "value": ureg.Quantity(record["property_value"], unit)}
                    for record in nested_object_records
                ]

                return time_slice_handler(
                    records=timeslice_patterns,
                    hourly_time_index=self.hourly_time_index,
                )

        nested_object_record = nested_object_records[0]  # Get the only element of the list

        match nested_object_record["child_class_name"]:
            case ClassEnum.DataFile:
                return nested_object_record["text"]
            case ClassEnum.Variable:
                return nested_object_record["property_value"]
            case _:
                raise NotImplementedError
