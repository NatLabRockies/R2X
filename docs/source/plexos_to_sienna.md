# PLEXOS → Sienna

Cloning the necessary packages for each translation is important.

## Setup

```bash
uv sync --upgrade
uv add --editable /path/to/r2x-plexos
uv add --editable /path/to/r2x-sienna
```

## Example Script

```python
import json
import os
from importlib.resources import files
from pathlib import Path

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from plexosdb import PlexosDB
from plexosdb.enums import ClassEnum
from r2x_plexos import PLEXOSConfig, PLEXOSParser
from r2x_sienna import SiennaConfig
from r2x_sienna.exporter import SiennaExporter

from r2x_core import (
    DataFile,
    DataStore,
    PluginContext,
    Rule,
    System,
    apply_rules_to_context,
)
from r2x_core.logger import setup_logging

setup_logging(verbosity=2)

case_name = "20241018_2023system_EI_ba"
folder_path = Path(f"/path/to/{case_name}")

# =====================================
# PLEXOS PARSER
# =====================================
xml_path = folder_path / "20241018_2023system_EI_ba.xml"
db = PlexosDB.from_xml(xml_path)
# Examining first the models in the plexos run would be helpful when trying
# to translate from PLEXOS to Sienna
model_names = db.list_objects_by_class(ClassEnum.Model)
model_name = model_names[1] if model_names else "Base"

plexos_config = PLEXOSConfig(
    model_name=model_name,
    horizon_year=2012,
    models=("r2x_plexos.models", "r2x_sienna.models"),)
data_file = DataFile(name="xml_file", fpath=xml_path)
store = DataStore(path=folder_path)
store.add_data([data_file])

context = PluginContext(
    config=plexos_config,
    store=store
)
parser = PLEXOSParser.from_context(context)
plexos_sys_result = parser.run()
plexos_sys = plexos_sys_result.system
context.source_system = plexos_sys

tmp_dir = plexos_sys.get_time_series_directory()

plexos_sys.convert_storage(
    time_series_directory=tmp_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True,
)

# =====================================
# Rules Definition
# =====================================
rules_path = files("r2x_plexos_to_sienna.config") / "rules.json"
rules = Rule.from_records(json.loads(rules_path.read_text()))
context.rules = rules

connection = create_in_memory_db()
ts_manager = TimeSeriesManager(
    connection,
    time_series_directory=tmp_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True
)

# =====================================
# PLEXOS to Sienna (TRANSLATION)
# =====================================
sienna_sys = System(
    name="Sienna",
    auto_add_composed_components=True,
    time_series_manager=ts_manager,
    system_base=100.0,
)
context.target_system = sienna_sys
apply_rules_to_context(context)

# =====================================
# Sienna Exporter
# =====================================
result_path = folder_path / "results"
output_dir = os.path.dirname(result_path)
os.makedirs(output_dir, exist_ok=True)
output_file = f"{folder_path}/{case_name}.json"
sienna_config = SiennaConfig(model_name=case_name, output_path=output_file)

exporter_context = PluginContext(
    config=sienna_config,
    system=sienna_sys,
)
exporter = SiennaExporter.from_context(exporter_context)

exporter.on_export()
```
