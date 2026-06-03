# Sienna → PLEXOS

Cloning the necessary packages for each translation is important.

## Setup

```bash
uv sync --upgrade
uv add --editable /path/to/r2x-sienna
uv add --editable /path/to/r2x-plexos
```

## Example Script

```python
import json
from importlib.resources import files
from pathlib import Path
from typing import cast

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from loguru import logger
from r2x_plexos import PLEXOSConfig
from r2x_plexos.exporter import PLEXOSExporter
from r2x_sienna.parser import SiennaParser
from r2x_sienna.plugin_config import SiennaConfig
from r2x_sienna_to_plexos.getters_utils import (
    ensure_battery_node_memberships,
    ensure_generator_node_memberships,
    ensure_generator_time_series,
    ensure_head_storage_generator_membership,
    ensure_interface_line_memberships,
    ensure_line_node_memberships,
    ensure_pumped_hydro_storages_created,
    ensure_reference_node_memberships,
    ensure_region_node_memberships,
    ensure_reserve_battery_memberships,
    ensure_reserve_generator_memberships,
    ensure_tail_storage_generator_membership,
    ensure_transformer_node_memberships,
)

from r2x_core import PluginContext, Rule, System, apply_rules_to_context
from r2x_core.logger import setup_logging
from r2x_core.store import DataStore

setup_logging(verbosity=1)

base_path = Path("/path/to/sienna-to-plexos")
sys_name = "EI_PCM_2023_2012"
sys_folder = base_path / sys_name

# =====================================
# Sienna PARSER
# =====================================
model_year=2023
weather_year=2012
json_path = sys_folder / f"{sys_name}.json"
sienna_config = SiennaConfig(
                json_path=str(json_path),
                model_year=model_year,
                system_name=sys_name,
                skip_validation=True,
                models=("r2x_sienna.models", "r2x_plexos.models", "r2x_sienna_to_plexos.getters"),
            )
store = DataStore.from_data_files([], path=json_path.parent)
context = PluginContext(
    config=sienna_config,
    store=store,
    skip_validation=True
)
parser = cast(SiennaParser, SiennaParser.from_context(context))
sienna_sys = parser.run()
sienna_sys = sienna_sys.system
context.source_system = sienna_sys

log_stage_timing("Sienna parser")

# =====================================
# Define Time Series Storage
# =====================================
tmp_dir = sienna_sys.get_time_series_directory()

sienna_sys.convert_storage(
    time_series_directory=tmp_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True,
)

log_stage_timing("Time Series Storage")

# =====================================
# Rules Definition
# =====================================
rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
rules = Rule.from_records(json.loads(rules_path.read_text()))
context.rules = rules


# =====================================
# Sienna to PLEXOS (TRANSLATION)
# =====================================
connection = create_in_memory_db()
ts_manager = TimeSeriesManager(
    connection,
    time_series_directory=tmp_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True
)

plexos_sys = System(
    name="PLEXOS",
    auto_add_composed_components=True,
    time_series_manager=ts_manager
)
context.target_system = plexos_sys

apply_rules_to_context(context)
ensure_generator_time_series(context)
ensure_region_node_memberships(context)
ensure_reference_node_memberships(context)
ensure_generator_node_memberships(context)
ensure_battery_node_memberships(context)
ensure_reserve_battery_memberships(context)
ensure_reserve_generator_memberships(context)
ensure_transformer_node_memberships(context)
ensure_line_node_memberships(context)
ensure_interface_line_memberships(context)
ensure_head_storage_generator_membership(context)
ensure_tail_storage_generator_membership(context)
ensure_pumped_hydro_storages_created(context)

# =====================================
# PLEXOS Exporter
# =====================================
results_dir = base_path / f"{sys_name}_results"
results_dir.mkdir(exist_ok=True)
plexos_config = PLEXOSConfig(
    model_name=sys_name,
    timeseries_dir=str(results_dir),
    horizon_year=model_year
)
exporter_context = PluginContext(
    config=plexos_config,
    system=plexos_sys
)

exporter = PLEXOSExporter.from_context(exporter_context)
exporter.output_path = results_dir
exporter.solve_year = model_year
exporter.weather_year = weather_year

exporter.on_export()

```
