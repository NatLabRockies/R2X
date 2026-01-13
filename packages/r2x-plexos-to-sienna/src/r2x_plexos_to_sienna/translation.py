import json
import os
from importlib.resources import files
from pathlib import Path

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from r2x_plexos import PLEXOSParser
from r2x_plexos.config import PLEXOSConfig
from r2x_sienna.config import SiennaConfig
from r2x_sienna.exporter import SiennaExporter

from r2x_core import (
    DataFile,
    DataStore,
    Rule,
    System,
    TranslationContext,
    apply_rules_to_context,
)
from r2x_plexos_to_sienna.plugin_config import PlexosToSiennaConfig


class PlexosToSiennaTranslation:
    def __init__(self, xml_path: str, model_name: str = "Base"):
        self.xml_path = Path(xml_path)
        self.model_name = model_name

    def run(self):
        result_path = self.xml_path.parent / "results"
        config = PLEXOSConfig(model_name=self.model_name, reference_year=2012)
        data_file = DataFile(name="xml_file", fpath=self.xml_path)
        store = DataStore(path=self.xml_path.parent)
        store.add_data(data_file)
        parser = PLEXOSParser(config, store)
        plexos_sys = parser.build_system()

        tmp_dir = self.xml_path.parent / f"{self.xml_path.parent.name}_tmp"
        plexos_sys.convert_storage(
            time_series_directory=tmp_dir,
            time_series_storage_type=TimeSeriesStorageType.ARROW,
            permanent=True,
        )

        rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
        rules = Rule.from_records(json.loads(rules_path.read_text()))

        connection = create_in_memory_db()
        ts_manager = TimeSeriesManager(
            connection,
            time_series_directory=tmp_dir,
            time_series_storage_type=TimeSeriesStorageType.ARROW,
            permanent=True,
        )

        sienna_sys = System(
            name="Sienna",
            auto_add_composed_components=True,
            time_series_manager=ts_manager,
        )
        context = TranslationContext(
            source_system=plexos_sys, target_system=sienna_sys, config=PlexosToSiennaConfig(), rules=rules
        )
        apply_rules_to_context(context)

        output_dir = os.path.dirname(result_path)
        os.makedirs(output_dir, exist_ok=True)
        exported_system_name = f"{self.folder_path.name}_ToSienna"
        config = SiennaConfig(model_name=exported_system_name)
        output_file = self.folder_path / f"{exported_system_name}.json"
        exporter = SiennaExporter(
            config,
            sienna_sys,
            output_path=output_file,
        )
        export_result = exporter.export()
        return export_result
