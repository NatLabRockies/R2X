import json
import os
from importlib.resources import files
from pathlib import Path

from plexosdb import PlexosDB
from plexosdb.enums import ClassEnum
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
    def __init__(self, folder_path: str, xml_filename: str):
        self.folder_path = Path(folder_path)
        self.xml_filename = xml_filename

    def run(self):
        result_path = self.folder_path / "results"
        xml_path = self.folder_path / self.xml_filename
        db = PlexosDB.from_xml(xml_path)
        model_names = db.list_objects_by_class(ClassEnum.Model)
        model_name = model_names[0] if model_names else "Base"
        config = PLEXOSConfig(model_name=model_name, reference_year=2030)
        data_file = DataFile(name="xml_file", fpath=xml_path)
        store = DataStore(path=self.folder_path)
        store.add_data(data_file)
        parser = PLEXOSParser(config, store)
        plexos_sys = parser.build_system()

        rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
        rules = Rule.from_records(json.loads(rules_path.read_text()))

        sienna_sys = System(
            name="Sienna",
            auto_add_composed_components=True,
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
