import json
from importlib.resources import files
from pathlib import Path

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_sienna.config import SiennaConfig
from r2x_sienna.exporter import SiennaExporter

from r2x_core import DataStore, PluginConfig, Rule, System, TranslationContext, apply_rules_to_context


class ReedsToSiennaTranslation:
    def __init__(self, run_path, output_folder, case_name, solve_year, weather_year):
        self.run_path = run_path
        self.output_folder = output_folder
        self.case_name = case_name
        self.solve_year = solve_year
        self.weather_year = weather_year

    def run(self):
        config = ReEDSConfig(
            solve_year=self.solve_year,
            weather_year=self.weather_year,
            case_name=self.case_name
        )
        data_store = DataStore.from_plugin_config(path=self.run_path, plugin_config=config)
        connection = create_in_memory_db()
        ts_manager = TimeSeriesManager(
            connection,
            time_series_directory=Path(f"{self.output_folder}/{self.case_name}_tmp"),
            time_series_storage_type=TimeSeriesStorageType.ARROW,
            permanent=True
        )
        parser = ReEDSParser(
            config,
            store=data_store,
            name=self.case_name,
            time_series_manager=ts_manager
        )
        reeds_sys = parser.build_system()

        rules_path = files("r2x_reeds_to_sienna.config") / "translation_rules.json"
        rules = Rule.from_records(json.loads(rules_path.read_text()))

        sienna_sys = System(
            name="Sienna",
            auto_add_composed_components=True,
            time_series_manager=ts_manager
        )
        plugin_config = PluginConfig(models=("r2x_reeds.models", "r2x_sienna.models", "r2x_reeds_to_sienna.getters"))
        context = TranslationContext(
            source_system=reeds_sys,
            target_system=sienna_sys,
            config=plugin_config,
            rules=rules
        )
        apply_rules_to_context(context)

        system_name = f"{self.case_name}_ToSienna"
        sienna_config = SiennaConfig(model_name=system_name)
        output_file = f"{self.output_folder}/{system_name}.json"
        exporter = SiennaExporter(
            sienna_config,
            sienna_sys,
            output_path=output_file,
        )
        exporter.export()
