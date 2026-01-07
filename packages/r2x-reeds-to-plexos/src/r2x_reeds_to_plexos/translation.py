from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from r2x_plexos import PLEXOSConfig
from r2x_plexos.exporter import PLEXOSExporter
from r2x_reeds import ReEDSConfig, ReEDSParser, ReEDSUpgrader

from r2x_core import DataStore, Rule, System, TranslationContext, apply_rules_to_context, run_upgrade_step

from .getters_utils import (
    attach_region_load_time_series,
    attach_reserve_time_series,
    attach_time_series_to_generators,
)
from .plugin_config import ReedsToPlexosConfig

if TYPE_CHECKING:
    from r2x_core import Rule, TranslationContext


class ReedsToPlexosTranslation:
    def __init__(
        self,
        run_path: str,
        output_folder: str,
        case_name: str,
        solve_year: int = 2030,
        weather_year: int = 2012,
    ):
        """
        Initialize the ReEDS to PLEXOS translation.

        Args:
            run_path: Path to ReEDS run folder
            output_folder: Path to the directory where output files will be saved
            case_name: Name of the case (used for output file naming)
            solve_year: The solve year for the ReEDS data (default: 2030)
            weather_year: The weather year for time series data (default: 2012)
        """
        self.run_path = run_path
        self.output_folder = output_folder
        self.case_name = case_name
        self.solve_year = solve_year
        self.weather_year = weather_year

    def run_reeds_upgrader(self):
        """Run the ReEDS upgrader on the run path."""
        upgrader = ReEDSUpgrader(path=Path(self.run_path))
        for step in upgrader.list_steps():
            result = run_upgrade_step(step, data=Path(self.run_path)).unwrap_or_raise()
        return result

    def run(self, run_upgrader: bool = False):
        """
        Execute the ReEDS to PLEXOS translation.

        Args:
            run_upgrader: Whether to run the ReEDS upgrader before parsing (default: False)
        """
        if run_upgrader:
            self.run_reeds_upgrader()

        config = ReEDSConfig(
            solve_year=self.solve_year,
            weather_year=self.weather_year,
            case_name=self.case_name,
        )

        tmp_dir = Path(self.output_folder) / f"{self.case_name}_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        data_store = DataStore.from_plugin_config(path=self.run_path, plugin_config=config)

        parser = ReEDSParser(
            config,
            store=data_store,
            name="ReEDS_System",
        )
        reeds_sys = parser.build_system()

        reeds_sys.convert_storage(
            time_series_directory=tmp_dir,
            time_series_storage_type=TimeSeriesStorageType.ARROW,
            permanent=True,
        )

        rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
        rules = Rule.from_records(json.loads(rules_path.read_text()))

        connection = create_in_memory_db()
        ts_manager = TimeSeriesManager(
            connection,
            time_series_directory=tmp_dir,
            time_series_storage_type=TimeSeriesStorageType.ARROW,
            permanent=True,
        )

        plexos_sys = System(
            name="PLEXOS",
            auto_add_composed_components=True,
            time_series_manager=ts_manager,
        )
        context = TranslationContext(
            source_system=reeds_sys,
            target_system=plexos_sys,
            config=ReedsToPlexosConfig(),
            rules=rules,
        )
        apply_rules_to_context(context)
        attach_reserve_time_series(context)
        attach_time_series_to_generators(context)
        attach_region_load_time_series(context)

        output_path = Path(self.output_folder) / f"{self.case_name}_results"
        output_path.mkdir(parents=True, exist_ok=True)

        plexos_config = PLEXOSConfig(
            model_name=self.case_name,
            timeseries_dir=str(output_path),
        )
        exporter = PLEXOSExporter(
            plexos_config,
            plexos_sys,
            output_path=str(output_path),
            solve_year=self.solve_year,
            weather_year=self.weather_year,
        )

        result = exporter.export()

        return result
