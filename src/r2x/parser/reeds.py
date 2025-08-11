"""Functions related to parsers."""

from __future__ import annotations

import importlib
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import repeat
from operator import attrgetter
from typing import TYPE_CHECKING

import numpy as np
import polars as pl
import pyarrow as pa
from infrasys.cost_curves import CostCurve, FuelCurve, UnitSystem
from infrasys.function_data import LinearFunctionData
from infrasys.time_series_models import SingleTimeSeries
from infrasys.value_curves import AverageRateCurve, LinearCurve
from loguru import logger
from pint import Quantity

from r2x.api import System
from r2x.config_models import ReEDSConfig
from r2x.enums import (
    ACBusTypes,
    EmissionType,
    PrimeMoversType,
    ReserveDirection,
    ReserveType,
    StorageTechs,
    ThermalFuels,
)
from r2x.exceptions import R2XParserError
from r2x.models import (
    ACBus,
    Area,
    Bus,
    Emission,
    EnergyReservoirStorage,
    FromTo_ToFrom,
    Generator,
    HybridSystem,
    HydroDispatch,
    HydroEnergyReservoir,
    HydroGen,
    HydroGenerationCost,
    InputOutput,
    LoadZone,
    MinMax,
    MonitoredLine,
    PowerLoad,
    RenewableDispatch,
    RenewableGen,
    RenewableGenerationCost,
    RenewableNonDispatch,
    Reserve,
    ReserveMap,
    ThermalGen,
    ThermalGenerationCost,
    TransmissionInterface,
    TransmissionInterfaceMap,
    UpDown,
)
from r2x.models.costs import StorageCost
from r2x.models.generators import Storage
from r2x.parser.handler import BaseParser, create_model_instance
from r2x.plugin_manager import PluginManager
from r2x.units import ActivePower, EmissionRate, Energy, Percentage, Time, ureg
from r2x.utils import get_enum_from_string, match_category, read_csv

from .polars_helpers import pl_left_multi_join

if TYPE_CHECKING:
    from argparse import ArgumentParser


R2X_MODELS = importlib.import_module("r2x.models")
UNITS = importlib.import_module("r2x.units")
BASE_WEATHER_YEAR = 2007


@PluginManager.register_cli("parser", "reeds-US")
def cli_arguments(parser: ArgumentParser) -> None:
    """CLI arguments for the plugin."""
    parser.add_argument(
        "--weather-year",
        type=int,
        dest="weather_year",
        help="ReEDS weather year to translate",
    )


class ReEDSParser(BaseParser):
    """ReEDS parser class."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        assert self.config.input_config
        assert isinstance(self.config.input_config, ReEDSConfig)
        self.reeds_config = self.config.input_config
        if not self.reeds_config.weather_year:
            raise AttributeError("Missing weather year from the configuration class.")
        if not self.reeds_config.solve_year:
            raise AttributeError("Missing solve year from the configuration class.")
        self.device_map = self.reeds_config.defaults["reeds_device_map"]
        self.tech_to_fuel_pm = self.reeds_config.defaults["tech_to_fuel_pm"]
        self.excluded_categories = self.reeds_config.defaults["excluded_categories"]
        self.weather_year: int = self.reeds_config.weather_year
        self.skip_validation: bool = getattr(self.reeds_config, "skip_validation", False)
        # Add hourly_time_index
        self.hourly_time_index = np.arange(
            f"{self.weather_year}",
            f"{self.weather_year + 1}",
            dtype="datetime64[h]",
        )[:-24]  # Removing 1 day to match ReEDS convention and converting into a vector
        self.daily_time_index = np.arange(
            f"{self.weather_year}",
            f"{self.weather_year + 1}",
            dtype="datetime64[D]",
        )[:-1]  # Removing 1 day to match ReEDS convention and converting into a vector

    def build_system(self) -> System:
        """Create IS system for the ReEDS model."""
        solve_year_found = self._check_solve_year()
        if not solve_year_found:
            msg = (
                "Solve year not found on scenario. "
                f"Select one of the available modeled years = {self.solve_years}"
            )
            raise R2XParserError(msg)
        self.system = System(
            name=self.config.name,
            auto_add_composed_components=True,
            description=(
                f"ReEDS translation for {self.reeds_config.solve_year=} and {self.reeds_config.weather_year=}"
            ),
        )

        # Construct transmission network and buses
        self._construct_buses()
        self._construct_reserves()
        self._construct_branches()
        self._construct_tx_interfaces()
        self._construct_generators()

        # Construct additional objects
        self._construct_emissions()

        # Time series construction
        self._construct_load()
        self._construct_hydro_budgets()
        self._construct_hydro_rating_profiles()
        self._construct_cf_time_series()
        self._construct_reserve_provision()
        self._construct_hybrid_systems()

        return self.system

    def _check_solve_year(self) -> bool:
        solve_years = self.get_data("years")
        years = list(solve_years.columns)
        years_int = [int(x) for x in years]
        self.solve_years = years_int
        if self.reeds_config.solve_year not in years_int:
            return False
        return True

    # NOTE: Rename to create topology
    def _construct_buses(self):
        logger.info("Creating bus objects.")
        bus_data = self.get_data("hierarchy")
        zones = bus_data["transmission_region"].unique()
        for zone in zones:
            self.system.add_component(self._create_model_instance(LoadZone, name=zone))

        for area in bus_data["state"].unique():
            self.system.add_component(self._create_model_instance(Area, name=area))

        for idx, bus in enumerate(bus_data.iter_rows(named=True)):
            self.system.add_component(
                self._create_model_instance(
                    ACBus,
                    number=idx + 1,
                    name=bus["region"],
                    area=self.system.get_component(Area, name=bus["state"]),
                    load_zone=self.system.get_component(LoadZone, name=bus["transmission_region"]),
                    bus_type=ACBusTypes.PV,
                )
            )

    def _construct_reserves(self):
        logger.info("Creating reserves objects.")
        bus_data = self.get_data("hierarchy")

        reserves = bus_data["transmission_region"].unique()
        for reserve in reserves:
            for name in self.reeds_config.defaults["default_reserve_types"]:
                reserve_duration = self.reeds_config.defaults["reserve_duration"].get(name)
                time_frame = self.reeds_config.defaults["reserve_time_frame"].get(name)
                # load_risk = self.reeds_config.defaults["reserve_load_risk"].get(name)
                vors = self.reeds_config.defaults["reserve_vors"].get(name)
                reserve_area = self.system.get_component(LoadZone, name=reserve)
                self.system.add_component(
                    self._create_model_instance(
                        Reserve,
                        name=f"{reserve}_{name}",
                        region=reserve_area,
                        reserve_type=ReserveType[name],
                        vors=vors,
                        duration=reserve_duration,
                        # load_risk=load_risk,
                        time_frame=time_frame,
                        direction=ReserveDirection.UP,
                    )
                )
        # Add reserve map
        self.system.add_component(self._create_model_instance(ReserveMap, name="reserve_map"))

    def _construct_branches(self):
        logger.info("Creating branch objects.")
        branch_data = self.get_data("tx_cap")
        tx_loss = self.get_data("tx_losses")

        branch_data = pl_left_multi_join(branch_data, tx_loss)
        ext = {"Wheeling Charge": 0.001, "Wheeling Charge Back": 0.001}
        reverse_lines = set()
        for idx, branch in enumerate(branch_data.iter_rows(named=True)):
            from_bus = self.system.get_component(ACBus, branch["from_bus"])
            to_bus = self.system.get_component(ACBus, branch["to_bus"])
            branch_name = f"{idx + 1:>04}-{branch['from_bus']}-{branch['to_bus']}"
            reverse_key = (branch["kind"], branch["from_bus"], branch["to_bus"])
            if reverse_key in reverse_lines:
                continue

            # NOTE: Calulate the inverse branch to add it as a single line
            # inverse_line_mask = (pl.col("to_bus") == from_bus.name) & (pl.col("from_bus") == to_bus.name)
            # if not (branch_data.filter(inverse_line_mask).is_empty()):
            #     rating_down = branch_data.filter(inverse_line_mask)["rating"]
            reverse_row = branch_data.filter(
                (pl.col("kind") == branch["kind"])
                & (pl.col("from_bus") == branch["to_bus"])
                & (pl.col("to_bus") == branch["from_bus"])
            ).to_dicts()

            if reverse_row:
                reverse_row_dict = reverse_row[0]
                rating_down = -reverse_row_dict["max_active_power"] * ureg.MW
                reverse_lines.add(
                    (reverse_row_dict["kind"], reverse_row_dict["from_bus"], reverse_row_dict["to_bus"])
                )
            else:
                rating_down = -branch["max_active_power"] * ureg.MW

            rating_up = branch["max_active_power"] * ureg.MW
            losses = branch["losses"] if branch["losses"] else 0
            self.system.add_component(
                self._create_model_instance(
                    MonitoredLine,
                    category=branch["kind"],
                    name=branch_name,
                    from_bus=from_bus,
                    to_bus=to_bus,
                    active_power_flow=0.0,
                    reactive_power_flow=0.0,
                    losses=losses * ureg.percent,
                    flow_limits=FromTo_ToFrom(from_to=rating_down, to_from=rating_up),
                    ext=ext,
                ),
            )

    def _construct_tx_interfaces(self):
        logger.info("Creating transmission interfaces objects.")
        interface_lines = self.system.get_components(
            MonitoredLine, filter_func=lambda x: x.from_bus.load_zone.name != x.to_bus.load_zone.name
        )
        interfaces = defaultdict(dict)  # Holder of interfaces
        tx_interface_map = self._create_model_instance(TransmissionInterfaceMap, name="transmission_map")
        for line in interface_lines:
            zone_from = line.from_bus.load_zone.name
            zone_to = line.to_bus.load_zone.name
            zone_pair = tuple(sorted((zone_from, zone_to)))
            zone_pair_name = f"{zone_pair[0]}_{zone_pair[1]}"
            if (zone_from, zone_to) == zone_pair:
                positive_flow, negative_flow = (
                    line.flow_limits.from_to.magnitude,
                    line.flow_limits.to_from.magnitude,
                )
            else:
                positive_flow, negative_flow = (
                    -line.flow_limits.to_from.magnitude,
                    -line.flow_limits.from_to.magnitude,
                )

            if "positive_flow" not in interfaces[zone_pair] or "negative_flow" not in interfaces[zone_pair]:
                interfaces[zone_pair]["positive_flow"] = positive_flow
                interfaces[zone_pair]["negative_flow"] = negative_flow
            else:
                interfaces[zone_pair]["positive_flow"] += positive_flow
                interfaces[zone_pair]["negative_flow"] += negative_flow

            tx_interface_map.mapping[zone_pair_name].append(line.label)

        for interface in interfaces:
            interface_name = f"{interface[0]}_{interface[1]}"
            interface_values = interfaces[interface]

            # The inferface transmission flow is defined as the sum of the rating of the lines.
            # In the case that the rate up/down does not match, we take the max and set it in both directions.
            max_power_flow = max(interface_values["positive_flow"], abs(interface_values["negative_flow"]))

            # Ramp multiplier defines the MW/min ratio for the interface
            ramp_multiplier = self.reeds_config.defaults["interface_max_ramp_up_multiplier"]
            self.system.add_component(
                self._create_model_instance(
                    TransmissionInterface,
                    name=interface_name,
                    active_power_flow_limits=MinMax(min=-max_power_flow, max=max_power_flow),
                    direction_mapping={},  # TBD
                    ext={
                        "ramp_up": max_power_flow * ramp_multiplier * ureg.Unit("MW/min"),
                        "ramp_down": max_power_flow * ramp_multiplier * ureg.Unit("MW/min"),
                    },
                )
            )
        self.system.add_component(tx_interface_map)

    def _construct_emissions(self) -> None:
        """Construct emission objects."""
        logger.info("Creating emission objects")
        emit_rates = self.get_data("emission_rates")

        emit_rates = emit_rates.with_columns(
            pl.concat_str([pl.col("tech"), pl.col("tech_vintage"), pl.col("region")], separator="_").alias(
                "generator_name"
            ),
            pl.concat_str(
                [
                    pl.col("tech"),
                    pl.col("tech_vintage"),
                    pl.col("region"),
                    pl.col("emission_type"),
                ],
                separator="_",
            ).alias("name"),
        )

        for generator in self.system.get_components(
            Generator, filter_func=lambda x: x.name in emit_rates["generator_name"]
        ):
            generator_emission = emit_rates.filter(
                (pl.col("generator_name") == generator.name) & (pl.col("emission_source") == "combustion")
            )
            for row in generator_emission.iter_rows(named=True):
                row["rate"] = EmissionRate(row["rate"], "kg/MWh")
                row["emission_type"] = get_enum_from_string(row["emission_type"], EmissionType)
                emission_model = self._create_model_instance(Emission, **row)
                self.system.add_supplemental_attribute(generator, emission_model)

    def _construct_generators(self) -> None:  # noqa: C901
        """Construct generators objects."""
        logger.info("Creating generator objects.")
        capacity_data = self.get_data("online_capacity")
        generator_fuel = self.get_data("fuels")

        # Fuel price requires two input files
        fuel_price_input = self.get_data("fuel_price")
        bfuel_price_output = (
            self.get_data("bfuel_price").with_columns(fuel=pl.lit("biomass")).join(generator_fuel, on="fuel")
        ).select(pl.exclude("fuel"))

        if bfuel_price_output.is_empty():
            fuel_price = fuel_price_input
        else:
            fuel_price = pl.concat([fuel_price_input, bfuel_price_output], how="diagonal")

        heat_rate = self.get_data("heat_rate")
        cost_vom = self.get_data("cost_vom")
        forced_outages = self.get_data("forced_outages")
        planned_outages = self.get_data("planned_outages")
        storage_duration = self.get_data("storage_duration")
        storage_eff = self.get_data("storage_eff")
        category_map = self.reeds_config.defaults.get("tech_categories", None)

        # NOTE: Temp unit definition. This should be read from the mapping file?
        unit_definition = {
            "fuel_price": "usd/MMBtu",
            "heat_rate": "MMBtu/MWh",
            "planned_outage_rate": "",
            "forced_outage_rate": "",
            "vom_price": "usd/MWh",
            "active_power": "MW",
            "pump_efficiency": "",
            "charge_efficiency": "",
            "discharge_efficiency": "",
            "pump_load": "MW",
            "storage_capacity": "MWh",
            "storage_duration": "h",
            "initial_energy": "%",
            "initial_volume": "MWh",
        }

        # Combine all the generator dataset in a single frame
        gen_data = pl_left_multi_join(
            capacity_data,
            generator_fuel,
            fuel_price,
            heat_rate,
            cost_vom,
            storage_duration,
            storage_eff,
            forced_outages,
            planned_outages,
        )

        # NOTE: Populate fuel_price information for technologies that use bio_fuel
        gen_data = gen_data.with_columns(
            category=pl.col("tech").map_elements(
                lambda row: match_category(row, category_map), return_dtype=pl.String
            )
        )

        # Adding extra columns
        gen_data = gen_data.with_columns(
            [
                (pl.col("active_power") * pl.col("storage_duration")).alias("storage_capacity"),
                (
                    pl.col("active_power")
                    * pl.col("storage_duration")
                    / self.reeds_config.defaults[
                        "initial_volume_divisor"
                    ]  # Storage start at half of its capacity
                ).alias("initial_volume"),
                (pl.lit(100) / self.reeds_config.defaults["initial_volume_divisor"]).alias(
                    "initial_energy"
                ),  # 50%
                (pl.col("active_power")).alias("pump_load"),
                (pl.col("charge_efficiency")).alias("pump_efficiency"),
                (
                    pl.when(pl.col("tech").is_in(self.reeds_config.defaults["commit_technologies"]))
                    .then(1)
                    .otherwise(None)
                ).alias("must_run"),
            ]
        )

        # NOTE: ReEDS exports some technologies that have a online_capacity of zero.
        # Once it is fixed on main we can remove this line over here.
        gen_data = gen_data.filter(pl.col("active_power") > 0)

        # Check that we mapped all categories
        categories = gen_data["category"].unique()
        for category in categories:
            device_map = self.device_map.get(category, "")
            if getattr(R2X_MODELS, device_map, None) is None:
                logger.warning(
                    "Could not parse category {}. Check that the type map is including this category.",
                    category,
                )
        non_cf_generators = gen_data.filter(
            ~pl.col("category").is_in(self.reeds_config.defaults["vre_categories"])
        )
        cf_generators = gen_data.filter(
            pl.col("category").is_in(self.reeds_config.defaults["vre_categories"])
        )
        cf_generators = self._aggregate_renewable_generators(cf_generators)

        combined_data = pl.concat([non_cf_generators, cf_generators], how="align")

        for row in combined_data.iter_rows(named=True):
            category = row["category"]

            if category in self.excluded_categories:
                msg = "`{}` in excluded categories. Skipping it."
                logger.debug(msg, category)
                continue

            device_map = self.device_map.get(category, "")
            if getattr(R2X_MODELS, device_map, None) is None:
                msg = "Could not find device model for `{}`. Skipping it."
                logger.warning(msg, category)
                continue

            gen_model = getattr(R2X_MODELS, device_map)
            for key, value in row.items():
                if key in unit_definition:
                    if value:
                        row[key] = value * ureg.Unit(unit_definition[key])
            # NOTE: We can uncomment this if we define the units onf the REEDS mapping.
            #     if key in self.config.fmap:
            #         units = self.config.fmap[key].get("units", "")
            #         if value is not None:
            #             row[key] = ureg.Quantity(value, units)

            # EXTRACT THIS NAME CONVENTION TO THE CONFIGURATION
            match gen_model.__name__:
                case "RenewableDispatch" | "RenewableNonDispatch":
                    name = row["tech"] + "_" + row["region"]
                case _:
                    name = row["tech"] + "_" + row["tech_vintage"] + "_" + row["region"]
                # case "":

            row["name"] = name

            if not (fuel_pm := self.tech_to_fuel_pm.get(row["category"])) and not self.skip_validation:
                msg = (
                    f"Could not find a fuel and prime mover map for `{row['category']}`."
                    " Check `reeds_input_config.json`"
                )
                raise R2XParserError(msg)

            row["prime_mover_type"] = (
                get_enum_from_string(fuel_pm["type"], PrimeMoversType) if fuel_pm.get("type") else None
            )
            if issubclass(gen_model, ThermalGen) and fuel_pm.get("fuel"):
                row["fuel"] = get_enum_from_string(fuel_pm["fuel"], ThermalFuels)

            if gen_model.__name__ == "EnergyReservoirStorage":
                row["storage_technology_type"] = StorageTechs.OTHER_CHEM
                row["initial_storage_capacity_level"] = 0.5
                row["input_active_power_limits"] = MinMax(min=0, max=row["active_power"].magnitude)
                row["output_active_power_limits"] = MinMax(min=0, max=row["active_power"].magnitude)
                row["efficiency"] = InputOutput(input=0.9, output=0.9)

            if gen_model.__name__ == "HydroPumpedStorage":
                row["storage_capacity"] = UpDown(
                    up=row["storage_capacity"].magnitude, down=row["storage_capacity"].magnitude
                )

            bus = self.system.get_component(ACBus, name=row["region"])
            row["bus"] = bus
            bus_load_zone = bus.load_zone
            assert bus_load_zone is not None

            # Add services to generator if they are not excluded
            row["services"] = []
            if row["tech"] not in self.reeds_config.defaults["excluded_reserve_techs"]:
                row["services"].extend(
                    list(
                        self.system.get_components(
                            Reserve,
                            filter_func=lambda x: x.region.name == bus_load_zone.name,
                        )
                    )
                )
                reserve_map = self.system.get_component(ReserveMap, name="reserve_map")
                for reserve_type in row["services"]:
                    reserve_map.mapping[reserve_type.name].append(row["name"])

            # Add operational cost data
            # ReEDS model all the thermal generators assuming an average heat rate
            vom_price = row.get("vom_price", None) or 0.0
            if isinstance(vom_price, Quantity):
                vom_price = vom_price.magnitude
            fuel_price = row.get("fuel_price", None) or 0.0
            if isinstance(fuel_price, Quantity):
                fuel_price = fuel_price.magnitude
            if issubclass(gen_model, RenewableGen):
                row["operation_cost"] = RenewableGenerationCost()
            if issubclass(gen_model, Storage):
                row["operation_cost"] = StorageCost()
            if issubclass(gen_model, ThermalGen):
                if heat_rate := row.get("heat_rate"):
                    if isinstance(heat_rate, Quantity):
                        heat_rate = heat_rate.magnitude
                    heat_rate_curve = AverageRateCurve(
                        function_data=LinearFunctionData(
                            proportional_term=heat_rate,
                            constant_term=0,
                        ),
                        initial_input=heat_rate,
                    )
                    fuel_curve = FuelCurve(
                        value_curve=heat_rate_curve,
                        vom_cost=LinearCurve(vom_price),
                        fuel_cost=fuel_price,
                        power_units=UnitSystem.NATURAL_UNITS,
                    )
                    row["operation_cost"] = ThermalGenerationCost(
                        variable=fuel_curve,
                    )
                else:
                    row["operation_cost"] = ThermalGenerationCost()
            if issubclass(gen_model, HydroGen):
                row["operation_cost"] = HydroGenerationCost(
                    variable=CostCurve(
                        value_curve=LinearCurve(vom_price),
                        power_units=UnitSystem.NATURAL_UNITS,
                    )
                )

            # NOTE: If there is a point when ReEDs enforces minimum capacity for a technology here is where we
            # will need to change it.
            row["active_power_limits"] = MinMax(min=0, max=row["active_power"].magnitude)

            row["ext"] = {}
            row["ext"] = {
                "tech": row["tech"],
                "reeds_tech": row["tech"],
                "reeds_vintage": row["tech_vintage"],
            }
            self.system.add_component(self._create_model_instance(gen_model, **row))

    def _construct_load(self):
        logger.info("Adding load time series.")

        bus_data = self.get_data("hierarchy")
        load_df = self.get_data("load").collect()
        start = load_df["datetime"].item(0)
        resolution = timedelta(hours=1)

        for _, bus_data in enumerate(bus_data.iter_rows(named=True)):
            bus_name = bus_data["region"]
            bus = self.system.get_component(ACBus, name=bus_name)
            ts = SingleTimeSeries.from_array(
                data=ActivePower(load_df[bus_name].to_numpy(), "MW"),
                name="max_active_power",
                initial_timestamp=start,
                resolution=resolution,
            )
            user_dict = {"solve_year": self.reeds_config.weather_year, "weather_year": self.weather_year}
            max_load = np.max(ts.data)
            load = self._create_model_instance(
                PowerLoad, name=f"{bus.name}", bus=bus, max_active_power=max_load
            )
            self.system.add_component(load)
            self.system.add_time_series(ts, load, **user_dict)

    def _construct_cf_time_series(self):
        logger.info("Adding cf time series")
        if not self.weather_year:
            raise AttributeError("Missing weather year from the configuration class.")

        cf_data = self.get_data("cf").collect()
        cf_adjustment = self.get_data("cf_adjustment")
        # NOTE: We take the median of  the seasonal adjustment since we
        # aggregate the generators by technology vintage
        cf_adjustment = cf_adjustment.group_by("tech").agg(pl.col("cf_adj").median())
        ilr = self.get_data("ilr")
        ilr = dict(
            ilr.group_by("tech").agg(pl.col("ilr").sum()).iter_rows()
        )  # Dict is more useful here than series
        start = cf_data["datetime"].item(0)
        resolution = timedelta(hours=1)

        counter = 0
        # NOTE: At some point, I would like to create a single time series per
        # BA instead of attaching one per generator. We would need to invert
        # the order of the loop and just use that to attach it to the different
        for generator in self.system.get_components(RenewableDispatch, RenewableNonDispatch):
            profile_name = generator.name  # .rsplit("_", 1)[0]
            if "|" in cf_data.columns[1]:
                profile_name = "|".join(profile_name.rsplit("_", 1))
            if profile_name not in cf_data.columns:
                msg = (
                    f"{generator.__class__.__name__}:{generator.name} do not "
                    f"have a corresponding time series `{profile_name}`. "
                    " Consider changing the model to `RenewableGen`"
                )
                logger.warning(msg)
                continue

            cf_adj = cf_adjustment.filter(pl.col("tech") == generator.ext["reeds_tech"])["cf_adj"]
            ilr_value = ilr.get(generator.ext["reeds_tech"], 1)
            rating_profile = generator.active_power * ilr_value * cf_adj * cf_data[profile_name].to_numpy()
            ts = SingleTimeSeries.from_array(
                data=rating_profile,
                name="max_active_power",
                initial_timestamp=start,
                resolution=resolution,
            )
            user_dict = {"weather_year": self.weather_year}
            self.system.add_time_series(ts, generator, **user_dict)
            counter += 1
        logger.debug("Added {} time series objects", counter)

    def _construct_reserve_provision(self):
        # NOTE: We need to re-think this chunk of code. The code is bad.
        # Provision is just based on wind/solar and load for the given region.
        logger.debug("Creating reserve provision")

        # We assume that they all start at the same time, so they have the same
        # resolution of the generator time series
        start = datetime(year=self.weather_year, month=1, day=1)
        resolution = timedelta(hours=1)
        for reserve in self.system.get_components(Reserve):
            region = reserve.region
            provision_objects = {}
            provision_objects["solar"] = [
                component
                for component in self.system.get_components(
                    RenewableDispatch,
                    filter_func=lambda x: x.bus.load_zone.name == region.name
                    and (
                        x.prime_mover_type == PrimeMoversType.PVe
                        or x.prime_mover_type == PrimeMoversType.RTPV
                    ),
                )
                if self.system.has_time_series(component)
            ]
            provision_objects["wind"] = [
                component
                for component in self.system.get_components(
                    RenewableDispatch,
                    filter_func=lambda x: x.bus.load_zone.name == region.name
                    and (
                        x.prime_mover_type == PrimeMoversType.WT or x.prime_mover_type == PrimeMoversType.WS
                    ),
                )
                if self.system.has_time_series(component)
            ]
            provision_objects["load"] = [
                component
                for component in self.system.get_components(
                    PowerLoad, filter_func=lambda x: x.bus.load_zone.name == region.name
                )
                if self.system.has_time_series(component)
            ]
            solar_names = list(map(attrgetter("name"), provision_objects["solar"]))
            wind_names = list(map(attrgetter("name"), provision_objects["wind"]))
            load_names = list(map(attrgetter("name"), provision_objects["load"]))
            solar_reserves = list(
                map(
                    getattr,
                    map(
                        getattr,
                        map(self.system.get_time_series, provision_objects["solar"]),
                        repeat("data"),
                    ),
                    repeat("magnitude"),
                )
            )
            solar_capacity = list(
                map(
                    lambda component: self.system.get_component_by_label(
                        component.label
                    ).active_power.magnitude,
                    provision_objects["solar"],
                )
            )
            wind_reserves = list(
                map(
                    getattr,
                    map(
                        getattr,
                        map(self.system.get_time_series, provision_objects["wind"]),
                        repeat("data"),
                    ),
                    repeat("magnitude"),
                )
            )
            load_reserves = list(
                map(
                    getattr,
                    map(
                        getattr,
                        map(self.system.get_time_series, provision_objects["load"]),
                        repeat("data"),
                    ),
                    repeat("magnitude"),
                )
            )
            wind_provision = (
                pa.Table.from_arrays(wind_reserves, names=wind_names)
                .to_pandas()
                .sum(axis=1)
                .mul(self.reeds_config.defaults["wind_reserves"].get(reserve.reserve_type.name, 0.01))
            )
            solar_provision = (
                pa.Table.from_arrays(solar_reserves, names=solar_names)
                .to_pandas()
                .sum(axis=1)
                .apply(lambda x: 1 if x != 0 else 0)
                .mul(sum(solar_capacity))
                .mul(self.reeds_config.defaults["solar_reserves"].get(reserve.reserve_type.name, 0.01))
            )
            load_provision = (
                pa.Table.from_arrays(load_reserves, names=load_names)
                .to_pandas()
                .sum(axis=1)
                .mul(self.reeds_config.defaults["load_reserves"].get(reserve.reserve_type.name, 0.01))
            )
            total_provision = load_provision.add(solar_provision, fill_value=0).add(
                wind_provision, fill_value=0
            )
            if total_provision.empty:
                msg = (
                    f"Reserve provision for {reserve=} is zero."
                    "Check that renewable devices contribute to the reserve"
                )
                logger.warning(msg)
            self.system.add_time_series(
                SingleTimeSeries.from_array(
                    total_provision.to_numpy(),
                    name="requirement",
                    initial_timestamp=start,
                    resolution=resolution,
                ),
                reserve,
            )
            # Add total provision as requirement
            setattr(reserve, "max_requirement", total_provision.sum())

    def _construct_hydro_budgets(self) -> None:
        """Hydro budgets in ReEDS."""
        logger.debug("Adding hydro budgets.")
        month_hrs = read_csv("month_hrs.csv").collect()
        month_hrs = month_hrs.filter(pl.col("model") == self.config.input_model)
        month_map = self.reeds_config.defaults["month_map"]

        hydro_cf = self.get_data("hydro_cf")
        hydro_cf = hydro_cf.with_columns(
            month=pl.col("month").map_elements(lambda row: month_map.get(row, row), return_dtype=pl.String)
        )
        month_hrs = month_hrs.rename({"szn": "season"})
        hydro_data = pl_left_multi_join(
            hydro_cf,
            month_hrs,
        )
        month_of_day = np.array(
            [dt.astype("datetime64[M]").astype(int) % 12 + 1 for dt in self.daily_time_index]
        )
        initial_timestamp = datetime(self.weather_year, 1, 1)
        for generator in self.system.get_components(HydroDispatch):
            # NOTE: Canadian imports need another file for the ratings, but we process it as
            # HydroEnergyReservoir since it is the way ReEDS model it.
            if generator.category == "can-imports":
                continue
            tech = generator.ext["reeds_tech"]
            generator_bus = generator.bus
            assert generator_bus
            region = generator_bus.name
            hydro_ratings = hydro_data.filter((pl.col("tech") == tech) & (pl.col("region") == region))

            hourly_time_series = np.zeros(len(month_of_day), dtype=float)

            for row in hydro_ratings.iter_rows(named=True):
                month = row["month"]
                if isinstance(month, str):
                    month = int(month.removeprefix("M"))

                month_max_budget = (
                    generator.active_power * Percentage(row["hydro_cf"], "") * Time(row["hrs"], "h")
                )
                daily_max_budget = month_max_budget / (row["hrs"] / 24)
                hourly_time_series[month_of_day == month] = daily_max_budget.magnitude

            ts = SingleTimeSeries.from_array(
                Energy(hourly_time_series / 1e3, "GWh"),
                "hydro_budget",
                initial_timestamp=initial_timestamp,
                resolution=timedelta(days=1),
            )
            self.system.add_time_series(ts, generator)

        return None

    def _construct_hydro_rating_profiles(self) -> None:
        logger.debug("Adding hydro rating profiles.")
        month_hrs = read_csv("month_hrs.csv").collect()
        month_hrs = month_hrs.filter(pl.col("model") == self.config.input_model).rename({"szn": "season"})
        month_map = self.reeds_config.defaults["month_map"]

        hydro_cf = self.get_data("hydro_cf")
        hydro_cf = hydro_cf.with_columns(
            month=pl.col("month").map_elements(lambda row: month_map.get(row, row), return_dtype=pl.String)
        )
        hydro_data = pl_left_multi_join(
            hydro_cf,
            month_hrs,
        )
        month_of_hour = np.array(
            [dt.astype("datetime64[M]").astype(int) % 12 + 1 for dt in self.hourly_time_index]
        )
        initial_timestamp = datetime(self.weather_year, 1, 1)
        for generator in self.system.get_components(HydroEnergyReservoir):
            tech = generator.ext["reeds_tech"]
            generator_bus = generator.bus
            assert generator_bus is not None
            region = generator_bus.name
            generator.inflow = 0.0
            generator.initial_storage = generator.initial_energy
            generator.storage_capacity = Energy(0.0, "MWh")
            generator.storage_target = Energy(0.0, "MWh")

            hourly_time_series = np.zeros(len(month_of_hour), dtype=float)
            hydro_ratings = hydro_data.filter((pl.col("tech") == tech) & (pl.col("region") == region))
            for row in hydro_ratings.iter_rows(named=True):
                month = row["month"]
                if isinstance(month, str):
                    month = int(month.removeprefix("M"))
                month_indices = month_of_hour == month
                rating = generator.active_power * Percentage(row["hydro_cf"], "")
                hourly_time_series[month_indices] = rating.magnitude
            ts = SingleTimeSeries.from_array(
                ActivePower(hourly_time_series, "MW"),
                "max_active_power",
                initial_timestamp=initial_timestamp,
                resolution=timedelta(hours=1),
            )
            self.system.add_time_series(ts, generator)
        return None

    def _construct_hybrid_systems(self):
        """Create hybrid storage units and add them to the system."""
        hybrids = list(
            self.system.get_components(RenewableDispatch, filter_func=lambda x: "pvb" in x.ext["tech"])
        )

        for device in hybrids:
            hybrid_values = device.model_dump()
            hybrid_name = hybrid_values.pop("name")

            ext_dict = device.ext

            # The only two required fields to create the new units are
            # `active_power` and the `bus`. We add some validation on both to
            # guarantee that the parser is correctly adding those into the ext
            # dictionary.
            bus: ACBus = device.bus
            msg = "Bus object not found for hybtid system. Check ingestion of the model inputs"
            assert bus is not None and isinstance(bus, Bus), msg

            # Create storage asset for hybrid.
            storage_unit_fields = {
                key: value for key, value in ext_dict.items() if key in EnergyReservoirStorage.model_fields
            }
            storage_unit_fields["prime_mover_type"] = PrimeMoversType.BA

            # If at some point we change the power of the storage it should be here
            storage_unit = self._create_model_instance(
                EnergyReservoirStorage,
                name=f"{hybrid_name}",
                active_power=device.active_power,  # Assume same power for the battery
                category="pvb-storage",
                bus=bus,
                ext=ext_dict,
            )
            self.system.add_component(storage_unit)

            # Updating name of the renewable component
            new_device = self.system.copy_component(device, name=f"{device.name}", attach=True)
            ts = self.system.get_time_series(device)
            self.system.add_time_series(ts, new_device)
            self.system.remove_component(device)
            hybrid_construct = self._create_model_instance(
                HybridSystem, name=f"{hybrid_name}", renewable_unit=new_device, storage_unit=storage_unit
            )
            self.system.add_component(hybrid_construct)

    def _aggregate_renewable_generators(self, data: pl.DataFrame) -> pl.DataFrame:
        return data.group_by(["tech", "region"]).agg(
            [pl.col("active_power").sum(), pl.exclude("active_power").first()]
        )

    def _create_model_instance(self, model_class, **kwargs):
        return create_model_instance(model_class, skip_validation=self.skip_validation, **kwargs)
