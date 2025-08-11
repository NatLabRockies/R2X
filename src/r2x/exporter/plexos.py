"""Create PLEXOS model from translated ReEDS data."""

import string
import uuid
from argparse import ArgumentParser
from collections.abc import Callable
from functools import partial
from importlib.resources import files
from typing import Any

from infrasys.component import Component
from loguru import logger
from plexosdb import ClassEnum, CollectionEnum, PlexosDB

from r2x.config_models import PlexosConfig, ReEDSConfig
from r2x.enums import ReserveType
from r2x.exporter.handler import BaseExporter, get_export_properties, get_export_records
from r2x.exporter.utils import (
    apply_correct_commit,
    apply_extract_key,
    apply_flatten_key,
    apply_pint_deconstruction,
    apply_property_map,
    apply_valid_properties,
    get_reserve_type,
)
from r2x.models import (
    ACBus,
    Emission,
    EnergyReservoirStorage,
    Generator,
    HydroDispatch,
    HydroEnergyReservoir,
    HydroPumpedStorage,
    InterruptiblePowerLoad,
    LoadZone,
    MonitoredLine,
    PowerLoad,
    RenewableDispatch,
    RenewableNonDispatch,
    Reserve,
    ThermalStandard,
    Transformer2W,
    TransmissionInterface,
)
from r2x.models.branch import Line
from r2x.models.utils import Constraint
from r2x.plugin_manager import PluginManager
from r2x.units import get_magnitude
from r2x.utils import custom_attrgetter, get_enum_from_string, read_json

NESTED_ATTRIBUTES = {"ext", "bus", "services"}
TIME_SERIES_PROPERTIES = ["Min Provision", "Static Risk"]
DEFAULT_XML_TEMPLATE = "master_9.2R6_btu.xml"
EXT_PROPERTIES = {"UoS Charge", "Fixed Load"}
KEYS_TO_FLATTEN = {"active_power_limits", "active_power_flow_limits", "storage_capacity", "flow_limits"}


@PluginManager.register_cli("exporter", "plexos")
def cli_arguments(parser: ArgumentParser):
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--master-file",
        required=False,
        help="Plexos master file to use as template.",
    )


class PlexosExporter(BaseExporter):
    """Plexos exporter class."""

    def __init__(
        self,
        *args,
        plexos_scenario: str = "default",
        database_manager=None,
        xml_fname: str | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        assert self.config.output_config
        assert self.config.input_config

        if not isinstance(self.config.output_config, PlexosConfig):
            msg = (
                f"Output config is of type {type(self.config.output_config)}. "
                "It should be type of `PlexosConfig`."
            )
            raise TypeError(msg)

        # Do not allow multiple years for the solve year.
        if isinstance(self.config.input_config, ReEDSConfig) and isinstance(
            self.config.input_config.solve_year, list
        ):
            msg = "Multiple solve years are not supported yet."
            raise NotImplementedError(msg)

        # Map relevant input configuration to output configuration
        self.output_config = self.config.input_config.to_class(PlexosConfig, self.config.output_config)
        self.plexos_scenario = plexos_scenario or self.output_config.model_name
        if not xml_fname and not (xml_fname := getattr(self.output_config, "master_file", None)):
            xml_fname = files("r2x.defaults").joinpath(DEFAULT_XML_TEMPLATE)  # type: ignore
            logger.debug("Using default XML template.")

        # Initialize PlexosDB
        self._db_mgr = PlexosDB.from_xml(xml_path=xml_fname)
        self.plexos_scenario_id = self._db_mgr.add_scenario(plexos_scenario)

        self._setup_plexos_configuration()

    def _setup_plexos_configuration(self) -> None:
        self.property_map = self.output_config.defaults["plexos_property_map"]
        self.valid_properties = self.output_config.defaults["valid_properties"]
        self.commit_map = self.output_config.defaults["commit_map"]
        self.default_units = self.output_config.defaults["default_units"]
        self.reserve_types = self.output_config.defaults["reserve_types"]

        self.simulation_objects = self.output_config.defaults["simulation_objects"]
        self.static_horizon_type = self.output_config.defaults["static_horizon_type"]
        self.static_horizons = self.output_config.defaults[self.static_horizon_type]
        self.static_model_type = self.output_config.defaults["static_model_type"]
        self.static_models = self.output_config.defaults[self.static_model_type]
        self.plexos_reports_fpath = self.output_config.defaults["plexos_reports"]

        # Set modeling years that will be used.
        assert isinstance(self.output_config.model_year, int)
        self.model_year: int = self.output_config.model_year
        self.weather_year: int = self.output_config.horizon_year or self.model_year

    def run(self, *args, new_database: bool = True, **kwargs) -> "PlexosExporter":
        """Run the exporter."""
        logger.info("Starting {}", self.__class__.__name__)

        self.time_series_to_csv(config=self.config, system=self.system, reference_year=self.weather_year)

        # If starting w/o a reference file we add our custom models and objects
        if new_database:
            self._add_simulation_objects()
            self._add_horizons()
            self._add_models()
            self._add_reports()
        self.add_constraints()
        self.add_topology()
        self.add_lines()
        self.add_transformers()
        self.add_interfaces()
        self.add_emissions()
        self.add_reserves()
        self.add_batteries()
        self.add_generators()
        self.add_storage()

        self._db_mgr.to_xml(f"{self.output_folder}/{self.config.name}.xml")

        return self

    def _get_time_series_properties(self, component):  # noqa: C901
        """Add time series object to certain plexos properties."""
        if not self.system.has_time_series(component):
            return

        if len(self.system.list_time_series(component)) > 1:
            # NOTE:@pedro this is a temporary fix for the multiple time series issue.
            return

        ts_metadata = self.system.get_time_series(component)

        config_dict = self.config.__dict__
        config_dict["name"] = self.config.name
        csv_fname = config_dict.get("time_series_fname", "${component_type}_${name}_${weather_year}.csv")
        string_template = string.Template(csv_fname)
        config_dict["component_type"] = f"{component.__class__.__name__}_{ts_metadata.name}"
        config_dict["weather_year"] = self.weather_year
        csv_fname = string_template.safe_substitute(config_dict)
        csv_fpath = self.ts_directory / csv_fname
        time_series_property: dict[str, Any] = {"Data File": str(csv_fpath)}

        # Property with time series can change. Validate this option based on the component type.
        match component:
            case InterruptiblePowerLoad():
                time_series_property["Fixed Load"] = "0"
            case PowerLoad():
                time_series_property["Load"] = "0"
            case RenewableDispatch():
                time_series_property["Rating"] = "0"
                time_series_property["Load Subtracter"] = "0"
            case RenewableNonDispatch():
                time_series_property["Rating"] = "0"
                time_series_property["Load Subtracter"] = "0"
            case Reserve():
                match component.reserve_type:
                    case ReserveType.SPINNING:
                        time_series_property["Min Provision"] = "0"
                    case ReserveType.FLEXIBILITY:
                        time_series_property["Min Provision"] = "0"
                    case ReserveType.REGULATION:
                        time_series_property["Min Provision"] = "0"
                    case _:
                        raise NotImplementedError(f"Reserve {component.type} not supported")
            case HydroDispatch():
                name = self.system.get_time_series(component).name
                if not name:
                    return None
                property_name = self.property_map.get(name, None)
                if property_name:
                    time_series_property[property_name] = "0"
            case HydroEnergyReservoir():
                time_series_property["Fixed Load"] = "0"
            case ThermalStandard():
                name = self.system.get_time_series(component).name
                if not name:
                    return None
                property_name = self.property_map.get(name, None)
                if property_name:
                    time_series_property[property_name] = "0"
            case _:
                raise NotImplementedError(f"Time Series for {component.label} not supported yet.")
        return time_series_property

    def insert_component_properties(
        self,
        component_type: type["Component"],
        /,
        *,
        parent_class: ClassEnum,
        child_class: ClassEnum,
        parent_object_name: str = "System",
        collection: CollectionEnum,
        filter_func: Callable | None = None,
        scenario: str | None = None,
        records: list[dict] | None = None,
        exclude_fields: set[str] | None = NESTED_ATTRIBUTES,
    ) -> None:
        """Bulk insert properties from selected component type."""
        logger.debug("Adding {} table properties...", component_type.__name__)
        scenario = scenario or self.plexos_scenario
        if not records:
            records = [
                component.model_dump(
                    exclude_none=True, exclude=exclude_fields, mode="python", serialize_as_any=True
                )
                for component in self.system.get_components(component_type, filter_func=filter_func)
            ]

        if not records:
            logger.warning("No components found for type {}", component_type)
            return

        collection_properties = self._db_mgr.list_valid_properties(
            collection, parent_class_enum=parent_class, child_class_enum=child_class
        )
        # property_names = [key[0] for key in collection_properties]
        match component_type.__name__:
            case "EnergyReservoirStorage":
                custom_map = {"active_power": "Max Power", "storage_capacity": "Capacity"}
            case "Line":
                custom_map = {"rating": "Max Flow"}
            case _:
                custom_map = {}
        property_map = self.property_map | custom_map

        export_records = get_export_records(
            records,
            partial(apply_operation_cost),
            partial(apply_extract_key, key="ext", keys_to_extract=EXT_PROPERTIES),
            partial(
                apply_flatten_key,
                keys_to_flatten=KEYS_TO_FLATTEN,
            ),
            partial(apply_property_map, property_map=property_map),
            partial(apply_correct_commit, commit_map=self.commit_map),
            partial(apply_pint_deconstruction, unit_map=self.default_units),
            partial(apply_valid_properties, valid_properties=collection_properties, add_name=True),
        )
        self._db_mgr.add_properties_from_records(
            export_records,
            object_class=child_class,
            parent_class=parent_class,
            parent_object_name=parent_object_name,
            collection=collection,
            scenario=scenario,
        )

    def add_component_category(
        self,
        component_type: type["Component"],
        class_enum: ClassEnum,
        category_attribute: str = "category",
        filter_func: Callable | None = None,
    ):
        """Add all categories for a component type."""
        component_categories = {
            custom_attrgetter(component, category_attribute)
            for component in self.system.get_components(component_type, filter_func=filter_func)
        }

        existing_rank = self._db_mgr.get_category_max_id(class_enum)
        class_id = self._db_mgr.get_class_id(class_enum)
        categories = [
            (class_id, rank, category or "")
            for rank, category in enumerate(
                sorted(component_categories, key=lambda x: (x is None, x)), start=existing_rank + 1
            )
        ]

        # Maybe replace `t_category` with right schema.
        query = "INSERT INTO t_category(class_id, rank, name) VALUES (?,?,?)"
        self._db_mgr._db.executemany(query, categories)
        return

    def bulk_insert_objects(
        self,
        component_type: type["Component"],
        class_enum: ClassEnum,
        collection_enum: CollectionEnum,
        category_attribute: str = "category",
        name_prefix: str = "",
        filter_func: Callable | None = None,
    ):
        """Bulk insert objects to the database."""
        logger.debug("Adding plexos objects for component type {}", component_type.__name__)

        query = """
        SELECT
            t_category.name
            ,t_category.category_id
        FROM
            t_category
        LEFT JOIN
            t_class ON t_class.class_id = t_category.class_id
        WHERE
            t_class.name = :class_name
        """
        categories_ids = {
            key: value for key, value in self._db_mgr.query(query, params={"class_name": class_enum})
        }
        class_id = self._db_mgr.get_class_id(class_enum)

        objects = [
            (
                class_id,
                component.name + name_prefix,
                self._get_category_id(component, category_attribute, categories_ids),
                str(uuid.uuid4()),
            )
            for component in self.system.get_components(component_type, filter_func=filter_func)
        ]
        object_names = tuple(d[1] for d in objects)
        if not objects:
            logger.warning("No components found for type' {}", component_type)
            return

        query = "INSERT INTO t_object(class_id, name, category_id, GUID) values (?,?,?,?)"
        self._db_mgr._db.executemany(query, objects)

        # Add system membership
        system_object_id = self._db_mgr.get_object_id(ClassEnum.System, name="System")
        system_class_id = self._db_mgr.get_class_id(ClassEnum.System)
        collection_id = self._db_mgr.get_collection_id(
            collection_enum, parent_class_enum=ClassEnum.System, child_class_enum=class_enum
        )
        objects_placeholders = ", ".join("?" * len(object_names))
        membership_query = f"""
            INSERT into t_membership(
              parent_class_id, parent_object_id,
              collection_id, child_class_id, child_object_id
            )
            SELECT
                ? as parent_class_id,
                ? as parent_object_id,
                ? as collection_id,
                ? as child_class_id,
                object_id as child_object_id
            FROM
              t_object
            WHERE
              class_id = ?
              and t_object.name in ({objects_placeholders})
        """
        query_parameters = (
            system_class_id,
            system_object_id,
            collection_id,
            class_id,
            class_id,
            *object_names,
        )
        self._db_mgr._db.execute(membership_query, query_parameters)

        # Enable all classes that we add into the database.
        # Some are disabled by default.
        self._db_mgr._db.execute(f"UPDATE t_class SET is_enabled=1 WHERE t_class.name='{class_enum}'")
        return

    def add_topology(self) -> None:
        """Create network topology on Plexos."""
        # Adding Regions
        self.add_component_category(ACBus, category_attribute="area.name", class_enum=ClassEnum.Region)
        self.bulk_insert_objects(
            ACBus,
            category_attribute="area.name",
            class_enum=ClassEnum.Region,
            collection_enum=CollectionEnum.Regions,
        )
        self.insert_component_properties(
            ACBus,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Region,
            collection=CollectionEnum.Regions,
        )
        for bus in self.system.get_components(ACBus, filter_func=lambda x: x.ext):
            collection_properties = self._db_mgr.list_valid_properties(
                CollectionEnum.Zones, parent_class_enum=ClassEnum.System, child_class_enum=ClassEnum.Zone
            )
            properties = get_export_properties(
                bus.ext,
                partial(apply_property_map, property_map=self.property_map),
                partial(apply_pint_deconstruction, unit_map=self.default_units),
                partial(apply_valid_properties, valid_properties=collection_properties),
            )
            if properties:
                for property_name, property_value in properties.items():
                    self._db_mgr.add_property(
                        ClassEnum.Region,
                        bus.name,
                        property_name,
                        property_value,
                        collection_enum=CollectionEnum.Regions,
                        scenario=self.plexos_scenario,
                    )

        # Adding Zones
        # self.add_component_category(LoadZone, class_enum=ClassEnum.Zone)
        self.bulk_insert_objects(LoadZone, class_enum=ClassEnum.Zone, collection_enum=CollectionEnum.Zones)
        self.insert_component_properties(
            LoadZone,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Zone,
            collection=CollectionEnum.Zones,
        )

        # Adding nodes
        # NOTE: For nodes, we do not add category.
        # self.add_component_category(ACBus, class_enum=ClassEnum.Node)
        self.bulk_insert_objects(ACBus, class_enum=ClassEnum.Node, collection_enum=CollectionEnum.Nodes)
        self.insert_component_properties(
            ACBus, parent_class=ClassEnum.System, child_class=ClassEnum.Node, collection=CollectionEnum.Nodes
        )

        # Add node memberships to zone and regions.
        # On our default Plexos translation, both Zones and Regions are child of the Node class.
        for bus in self.system.get_components(ACBus):
            bus_load_zone = bus.load_zone
            self._db_mgr.add_membership(
                parent_object_name=bus.name,
                child_object_name=bus.name,
                parent_class_enum=ClassEnum.Node,
                child_class_enum=ClassEnum.Region,
                collection_enum=CollectionEnum.Region,
            )
            if bus_load_zone is None:
                continue
            self._db_mgr.add_membership(
                parent_object_name=bus.name,
                child_object_name=bus_load_zone.name,
                parent_class_enum=ClassEnum.Node,
                child_class_enum=ClassEnum.Zone,
                collection_enum=CollectionEnum.Zone,
            )

        # Adding load time series
        logger.debug("Adding load time series properties")
        for component in self.system.get_components(
            PowerLoad, filter_func=lambda component: self.system.has_time_series(component)
        ):
            time_series_properties = self._get_time_series_properties(component)
            if time_series_properties:
                text = time_series_properties.pop("Data File")
                for property_name, property_value in time_series_properties.items():
                    self._db_mgr.add_property(
                        ClassEnum.Region,
                        component.bus.name,
                        property_name,
                        property_value,
                        collection_enum=CollectionEnum.Regions,
                        scenario=self.plexos_scenario,
                        text={"Data File": text},
                    )
        return

    def add_lines(self) -> None:
        """Add transmission lines that connect topology elements."""
        # Adding Lines
        # NOTE: The default line on Plexos is a `MonitoredLine` without category. If we need to add a category
        # in the future, we will uncomment the line below with the pertinent category name.
        self.add_component_category(MonitoredLine, class_enum=ClassEnum.Line)
        self.bulk_insert_objects(Line, class_enum=ClassEnum.Line, collection_enum=CollectionEnum.Lines)
        self.insert_component_properties(
            Line, parent_class=ClassEnum.System, child_class=ClassEnum.Line, collection=CollectionEnum.Lines
        )
        self.bulk_insert_objects(
            MonitoredLine, class_enum=ClassEnum.Line, collection_enum=CollectionEnum.Lines
        )
        self.insert_component_properties(
            MonitoredLine,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Line,
            collection=CollectionEnum.Lines,
        )

        # Add additional properties if any and membersips
        collection_properties = self._db_mgr.list_valid_properties(
            CollectionEnum.Lines, parent_class_enum=ClassEnum.System, child_class_enum=ClassEnum.Line
        )
        for line in self.system.get_components(MonitoredLine, Line):
            properties = get_export_properties(
                line.ext,
                partial(apply_property_map, property_map=self.property_map),
                partial(apply_pint_deconstruction, unit_map=self.default_units),
                partial(apply_valid_properties, valid_properties=collection_properties),
            )
            for property_name, property_value in properties.items():
                self._db_mgr.add_property(
                    ClassEnum.Line,
                    line.name,
                    property_name,
                    property_value,
                    collection_enum=CollectionEnum.Lines,
                    scenario=self.plexos_scenario,
                )
            self._db_mgr.add_membership(
                parent_object_name=line.name,
                child_object_name=line.from_bus.name,
                parent_class_enum=ClassEnum.Line,
                child_class_enum=ClassEnum.Node,
                collection_enum=CollectionEnum.NodeFrom,
            )
            self._db_mgr.add_membership(
                parent_object_name=line.name,
                child_object_name=line.to_bus.name,
                parent_class_enum=ClassEnum.Line,
                child_class_enum=ClassEnum.Node,
                collection_enum=CollectionEnum.NodeTo,
            )
        return

    def add_transformers(self) -> None:
        """Add Transformer objects to the database."""
        self.add_component_category(Transformer2W, class_enum=ClassEnum.Transformer)
        self.bulk_insert_objects(
            Transformer2W, class_enum=ClassEnum.Transformer, collection_enum=CollectionEnum.Transformers
        )
        self.insert_component_properties(
            Transformer2W,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Transformer,
            collection=CollectionEnum.Transformers,
        )
        for transformer in self.system.get_components(Transformer2W):
            self._db_mgr.add_membership(
                parent_object_name=transformer.name,
                child_object_name=transformer.from_bus.name,
                parent_class_enum=ClassEnum.Transformer,
                child_class_enum=ClassEnum.Node,
                collection_enum=CollectionEnum.NodeFrom,
            )
            self._db_mgr.add_membership(
                parent_object_name=transformer.name,
                child_object_name=transformer.to_bus.name,
                parent_class_enum=ClassEnum.Transformer,
                child_class_enum=ClassEnum.Node,
                collection_enum=CollectionEnum.NodeTo,
            )
        return

    def add_interfaces(self) -> None:
        """Add transmission interfaces."""
        self.bulk_insert_objects(
            TransmissionInterface,
            class_enum=ClassEnum.Interface,
            collection_enum=CollectionEnum.Interfaces,
        )
        self.insert_component_properties(
            TransmissionInterface,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Interface,
            collection=CollectionEnum.Interfaces,
        )

    def add_constraints(self) -> None:
        """Add custom constraints."""
        self.bulk_insert_objects(
            Constraint,
            class_enum=ClassEnum.Constraint,
            collection_enum=CollectionEnum.Constraints,
        )
        collection_properties = self._db_mgr.list_valid_properties(
            CollectionEnum.Constraints,
            parent_class_enum=ClassEnum.System,
            child_class_enum=ClassEnum.Constraint,
        )
        for constraint in self.system.get_components(Constraint):
            properties = get_export_properties(
                constraint.ext,
                partial(apply_property_map, property_map=self.property_map),
                partial(apply_pint_deconstruction, unit_map=self.default_units),
                partial(apply_valid_properties, valid_properties=collection_properties),
            )

            if properties:
                for property_name, property_value in properties.items():
                    self._db_mgr.add_property(
                        ClassEnum.Constraint,
                        constraint.name,
                        property_name,
                        property_value,
                        collection_enum=CollectionEnum.Constraints,
                        scenario=self.plexos_scenario,
                    )

        return

    def add_emissions(self) -> None:
        """Add emission objects to the database."""
        logger.debug("Adding Emission objects...")
        self._db_mgr._db.execute(f"UPDATE t_class SET is_enabled=1 WHERE t_class.name='{ClassEnum.Emission}'")
        # Getting all unique emission types (e.g., CO2, NOX) from the emissions objects.
        # NOTE: On Plexos, we need to add each emission type individually to the Emission class
        emission_types = set(
            map(lambda x: x.emission_type, list(self.system.get_supplemental_attributes(Emission)))
        )
        for emission_type in emission_types:
            self._db_mgr.add_object(
                ClassEnum.Emission,
                name=emission_type,
                collection_enum=CollectionEnum.Emissions,
            )

            # Add emission caps from emission_cap.py if added.
            emission_constraint_name = f"Annual_{emission_type}_cap"
            collection_properties = self._db_mgr.list_valid_properties(
                CollectionEnum.Constraints,
                parent_class_enum=ClassEnum.Emission,
                child_class_enum=ClassEnum.Constraint,
            )
            for constraint in self.system.get_components(
                Constraint, filter_func=lambda x: x.name == emission_constraint_name
            ):
                self._db_mgr.add_membership(
                    parent_object_name=emission_type,
                    child_object_name=constraint.name,
                    parent_class_enum=ClassEnum.Emission,
                    child_class_enum=ClassEnum.Constraint,
                    collection_enum=CollectionEnum.Constraints,
                )
                properties = get_export_properties(
                    constraint.ext[emission_type],
                    partial(apply_property_map, property_map=self.property_map),
                    partial(apply_pint_deconstruction, unit_map=self.default_units),
                    partial(apply_valid_properties, valid_properties=collection_properties),
                )
                if properties:
                    for property_name, property_value in properties.items():
                        self._db_mgr.add_property(
                            ClassEnum.Constraint,
                            constraint.name,
                            property_name,
                            property_value,
                            parent_object_name=emission_type,
                            parent_class_enum=ClassEnum.Emission,
                            collection_enum=CollectionEnum.Constraints,
                            scenario=self.plexos_scenario,
                        )
        return

    def add_reserves(self) -> None:
        """Add system reserves to the database.

        This method only appends the information for the type of reserves. Each
        generator that contributes to the reserve will add the membership for
        the type of reserve as a child membership.
        """
        # Adding reserves
        # self.add_component_category(Reserve, class_enum=ClassEnum.Reserve)
        self.bulk_insert_objects(
            Reserve, class_enum=ClassEnum.Reserve, collection_enum=CollectionEnum.Reserves
        )

        self.insert_component_properties(
            Reserve,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Reserve,
            collection=CollectionEnum.Reserves,
            exclude_fields=NESTED_ATTRIBUTES | {"max_requirement"},
        )
        for reserve in self.system.get_components(Reserve):
            properties: dict[str, Any] = {}
            properties["Type"] = get_reserve_type(
                reserve_type=reserve.reserve_type,
                reserve_direction=reserve.direction,
                reserve_types=self.reserve_types,
            )
            properties["Is Enabled"] = "-1" if reserve.available else "0"
            properties["Mutually Exclusive"] = True

            for property, value in properties.items():
                self._db_mgr.add_property(
                    ClassEnum.Reserve,
                    reserve.name,
                    property,
                    value,
                    collection_enum=CollectionEnum.Reserves,
                    scenario=self.plexos_scenario,
                )
            time_series_properties = self._get_time_series_properties(reserve)
            if time_series_properties:
                text = time_series_properties.pop("Data File")
                for property_name, property_value in time_series_properties.items():
                    self._db_mgr.add_property(
                        ClassEnum.Reserve,
                        reserve.name,
                        property_name,
                        property_value,
                        collection_enum=CollectionEnum.Reserves,
                        scenario=self.plexos_scenario,
                        text={"Data File": text},
                    )

            # Add Regions properties. Currently, we only add the load_risk
            component_dict = reserve.model_dump(
                exclude_none=True, exclude=NESTED_ATTRIBUTES | {"max_requirement"}
            )

            if not reserve.region:
                return
            reserve_region = reserve.region
            assert reserve_region is not None
            regions = self.system.get_components(
                ACBus, filter_func=lambda x: x.load_zone.name == reserve_region.name
            )

            collection_properties = self._db_mgr.list_valid_properties(
                CollectionEnum.Regions,
                parent_class_enum=ClassEnum.Reserve,
                child_class_enum=ClassEnum.Region,
            )
            for region in regions:
                self._db_mgr.add_membership(
                    parent_object_name=reserve.name,
                    child_object_name=region.name,  # Zone has the same name
                    parent_class_enum=ClassEnum.Reserve,
                    child_class_enum=ClassEnum.Region,
                    collection_enum=CollectionEnum.Regions,
                )
                properties = get_export_properties(
                    component_dict,
                    partial(apply_property_map, property_map=self.property_map),
                    partial(apply_pint_deconstruction, unit_map=self.default_units),
                    partial(apply_valid_properties, valid_properties=collection_properties),
                )
                if properties:
                    for property_name, property_value in properties.items():
                        self._db_mgr.add_property(
                            ClassEnum.Region,
                            region.name,
                            property_name,
                            property_value,
                            parent_object_name=reserve.name,
                            parent_class_enum=ClassEnum.Reserve,
                            collection_enum=CollectionEnum.Regions,
                            scenario=self.plexos_scenario,
                        )
        return

    def add_generators(self):
        """Add generator objects to the database."""

        # Add generator objects excluding batteries
        def exclude_battery(component):
            return not isinstance(component, EnergyReservoirStorage)

        self.add_component_category(Generator, class_enum=ClassEnum.Generator, filter_func=exclude_battery)
        self.bulk_insert_objects(
            Generator,
            class_enum=ClassEnum.Generator,
            collection_enum=CollectionEnum.Generators,
            filter_func=exclude_battery,
        )
        self.insert_component_properties(
            Generator,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Generator,
            collection=CollectionEnum.Generators,
            filter_func=exclude_battery,
            exclude_fields=[],
        )

        # Add generator memberships
        logger.debug("Adding generator memberships")
        for generator in self.system.get_components(Generator, filter_func=exclude_battery):
            self._db_mgr.add_membership(
                parent_object_name=generator.name,
                child_object_name=generator.bus.name,
                parent_class_enum=ClassEnum.Generator,
                child_class_enum=ClassEnum.Node,
                collection_enum=CollectionEnum.Nodes,
            )
            properties = self._get_time_series_properties(generator)
            if properties:
                text = properties.pop("Data File")
                for property_name, property_value in properties.items():
                    self._db_mgr.add_property(
                        ClassEnum.Generator,
                        generator.name,
                        property_name,
                        property_value,
                        collection_enum=CollectionEnum.Generators,
                        scenario=self.plexos_scenario,
                        text={"Data File": text},
                    )
            if generator.services:
                for service in generator.services:
                    match service:
                        case Reserve():
                            self._db_mgr.add_membership(
                                parent_object_name=service.name,
                                child_object_name=generator.name,
                                parent_class_enum=ClassEnum.Reserve,
                                child_class_enum=ClassEnum.Generator,
                                collection_enum=CollectionEnum.Generators,
                            )
                        case _:
                            raise NotImplementedError(f"{service} not yet implemented for generator.")

        # NOTE: This needs to be optimized. It is currently slow.
        logger.debug("Adding generator emisssions memberships")
        for emission in self.system.get_supplemental_attributes(Emission):
            for generator in self.system.get_components_with_supplemental_attribute(emission):
                self._db_mgr.add_membership(
                    parent_object_name=emission.emission_type,
                    child_object_name=generator.name,
                    parent_class_enum=ClassEnum.Emission,
                    child_class_enum=ClassEnum.Generator,
                    collection_enum=CollectionEnum.Generators,
                )
                self._db_mgr.add_property(
                    ClassEnum.Generator,
                    generator.name,
                    self.property_map["rate"],
                    get_magnitude(emission.rate),
                    parent_class_enum=ClassEnum.Emission,
                    parent_object_name=emission.emission_type,
                    collection_enum=CollectionEnum.Generators,
                    scenario=self.plexos_scenario,
                )

    def add_batteries(self):
        """Add battery objects to the database."""
        # Add battery objects
        self.add_component_category(EnergyReservoirStorage, class_enum=ClassEnum.Battery)
        self.bulk_insert_objects(
            EnergyReservoirStorage,
            class_enum=ClassEnum.Battery,
            collection_enum=CollectionEnum.Batteries,
        )
        self.insert_component_properties(
            EnergyReservoirStorage,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Battery,
            collection=CollectionEnum.Batteries,
        )
        # Add battery memberships
        for battery in self.system.get_components(EnergyReservoirStorage):
            self._db_mgr.add_membership(
                parent_object_name=battery.name,
                child_object_name=battery.bus.name,
                parent_class_enum=ClassEnum.Battery,
                child_class_enum=ClassEnum.Node,
                collection_enum=CollectionEnum.Nodes,
            )
            if battery.services:
                for service in battery.services:
                    match service:
                        case Reserve():
                            self._db_mgr.add_membership(
                                parent_object_name=service.name,
                                child_object_name=battery.name,
                                parent_class_enum=ClassEnum.Reserve,
                                child_class_enum=ClassEnum.Battery,
                                collection_enum=CollectionEnum.Batteries,
                            )
                        case _:
                            raise NotImplementedError(f"{service} not yet implemented for generator.")

    def add_storage(self):
        """Add storage objects to the database."""
        # Add pump storage objects
        self.add_component_category(
            HydroPumpedStorage, category_attribute="head", class_enum=ClassEnum.Storage
        )
        self.add_component_category(
            HydroPumpedStorage, category_attribute="tail", class_enum=ClassEnum.Storage
        )
        self.bulk_insert_objects(
            HydroPumpedStorage,
            class_enum=ClassEnum.Storage,
            category_attribute="head",
            collection_enum=CollectionEnum.Storages,
            name_prefix="_head",
        )
        self.bulk_insert_objects(
            HydroPumpedStorage,
            class_enum=ClassEnum.Storage,
            category_attribute="tail",
            collection_enum=CollectionEnum.Storages,
            name_prefix="_tail",
        )

        head_storage = [
            component.model_dump(exclude_none=True, exclude=NESTED_ATTRIBUTES)
            for component in self.system.get_components(HydroPumpedStorage)
        ]
        for component in head_storage:
            component["name"] += "_head"
        self.insert_component_properties(
            HydroPumpedStorage,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Storage,
            collection=CollectionEnum.Storages,
            records=head_storage,
        )
        tail_storage = [
            component.model_dump(exclude_none=True, exclude=NESTED_ATTRIBUTES)
            for component in self.system.get_components(HydroPumpedStorage)
        ]
        for component in tail_storage:
            component["name"] += "_tail"
        self.insert_component_properties(
            HydroPumpedStorage,
            parent_class=ClassEnum.System,
            child_class=ClassEnum.Storage,
            collection=CollectionEnum.Storages,
            records=tail_storage,
        )

        for phs in self.system.get_components(HydroPumpedStorage):
            head_name = f"{phs.name}_head"
            tail_name = f"{phs.name}_tail"
            self._db_mgr.add_membership(
                parent_object_name=phs.name,
                child_object_name=head_name,
                parent_class_enum=ClassEnum.Generator,
                child_class_enum=ClassEnum.Storage,
                collection_enum=CollectionEnum.HeadStorage,
            )
            self._db_mgr.add_membership(
                parent_object_name=phs.name,
                child_object_name=tail_name,
                parent_class_enum=ClassEnum.Generator,
                child_class_enum=ClassEnum.Storage,
                collection_enum=CollectionEnum.TailStorage,
            )
        return

    def _add_simulation_objects(self):
        for simulation_object in self.simulation_objects:
            collection_enum = get_enum_from_string(simulation_object["collection_name"], CollectionEnum)
            class_enum: ClassEnum = get_enum_from_string(simulation_object["class_name"], ClassEnum)
            for objects in simulation_object["attributes"]:
                self._db_mgr.add_object(
                    class_enum,
                    objects["name"],
                    collection_enum=collection_enum,
                    category=objects["category"] or "-",
                )

            # Add attributes
            property_list = self.output_config.defaults[simulation_object["class_name"]]
            for attributes in property_list["attributes"]:
                self._db_mgr.add_attribute(
                    get_enum_from_string(attributes["class"], ClassEnum),
                    object_name=attributes["name"],
                    attribute_name=attributes["attribute"],
                    attribute_value=attributes["value"],
                )

    def _add_horizons(self):
        logger.info("Adding model horizon")
        for horizon, values in self.static_horizons.items():
            self._db_mgr.add_object(
                ClassEnum.Horizon,
                name=horizon,
                collection_enum=CollectionEnum.Horizons,
            )
            for attribute, attribute_value in values["attributes"].items():
                self._db_mgr.add_attribute(
                    ClassEnum.Horizon,
                    object_name=horizon,
                    attribute_name=attribute,
                    attribute_value=attribute_value,
                )

    def _add_models(self):
        for model, values in self.static_models.items():
            self._db_mgr.add_object(
                ClassEnum.Model,
                name=model,
                collection_enum=CollectionEnum.Models,
                category=values["category"],
            )
            for attribute, attribute_value in values["attributes"].items():
                self._db_mgr.add_attribute(
                    ClassEnum.Model,
                    object_name=model,
                    attribute_name=attribute,
                    attribute_value=attribute_value,
                )
            for child_class_name, child_object_name in values["memberships"].items():
                collection_enum = get_enum_from_string(child_class_name, CollectionEnum)
                child_class = get_enum_from_string(child_class_name, ClassEnum)
                self._db_mgr.add_membership(
                    parent_object_name=model,
                    child_object_name=child_object_name,
                    parent_class_enum=ClassEnum.Model,
                    child_class_enum=child_class,
                    collection_enum=collection_enum,
                )
            self._db_mgr.add_membership(
                parent_object_name=model,
                child_object_name=self.plexos_scenario,
                parent_class_enum=ClassEnum.Model,
                child_class_enum=ClassEnum.Scenario,
                collection_enum=CollectionEnum.Scenarios,
            )
        return

    def _add_reports(self):
        logger.debug("Using {} for reports.", self.plexos_reports_fpath)
        report_objects = read_json(self.plexos_reports_fpath)

        for report_object in report_objects:
            report_object["collection"] = get_enum_from_string(report_object["collection"], CollectionEnum)
            report_object["parent_class"] = get_enum_from_string(report_object["parent_class"], ClassEnum)
            report_object["child_class"] = get_enum_from_string(report_object["child_class"], ClassEnum)
            self._db_mgr.add_report(**report_object)
        return

    def _get_category_id(self, component, category_attribute, categories_ids, default_category="-"):
        category_to_get = custom_attrgetter(component, category_attribute)

        if category_to_get not in categories_ids:
            return categories_ids[default_category]
        return categories_ids[category_to_get]


def apply_operation_cost(component: dict) -> dict[str, Any]:
    """Parse Infrasys Operation Cost into Plexos Records."""
    if not (cost := component.get("operation_cost")):
        return component
    match cost["class_type"]:
        case "ThermalGenerationCost":
            if shut_down := cost.get("start_up"):
                component["Start Cost"] = shut_down
            if shut_down := cost.get("shut_down"):
                component["Shutdown Cost"] = shut_down

            if cost.get("variable"):
                component = _variable_type_parsing(component, cost)
        case _:
            pass
    return component


def _variable_type_parsing(component: dict, cost_dict: dict[str, Any]) -> dict[str, Any]:
    fuel_curve = cost_dict["variable"]
    value_curve_type = cost_dict["value_curve_type"]
    variable_type = cost_dict["variable_type"]
    function_data = fuel_curve["value_curve"]["function_data"]
    match variable_type:
        case "FuelCurve":
            match value_curve_type:
                case "AverageRateCurve":
                    component["Heat Rate"] = function_data.proportional_term
                case "InputOutputCurve":
                    raise NotImplementedError("`InputOutputCurve` not yet implemented on Plexos exporter.")
        case "CostCurve":
            pass

    if fuel_cost := fuel_curve.get("fuel_cost"):
        component["Fuel Price"] = fuel_cost
    if vom_cost := fuel_curve.get("vom_cost"):
        component["VO&M Charge"] = vom_cost["function_data"].proportional_term

    return component
