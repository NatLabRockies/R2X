# r2x-sienna-to-plexos

Translate Sienna systems into PLEXOS models.

## Overview

This package provides a translation plugin to convert Sienna system models into PLEXOS XML format. The translation applies mapping rules and getters to transform Sienna components (generators, buses, lines, transformers, etc.) into their PLEXOS equivalents.

## Usage

### Basic Example

```python
import json
from importlib.resources import files
from pathlib import Path
from typing import cast

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from r2x_plexos import PLEXOSConfig
from r2x_plexos.exporter import PLEXOSExporter
from r2x_sienna.parser import SiennaParser
from r2x_sienna.plugin_config import SiennaConfig
from r2x_sienna_to_plexos.getters_utils import (
    ensure_battery_node_memberships,
    ensure_generator_node_memberships,
    ensure_head_storage_generator_membership,
    ensure_interface_line_memberships,
    ensure_node_zone_memberships,
    ensure_region_node_memberships,
    ensure_reserve_battery_memberships,
    ensure_reserve_generator_memberships,
    ensure_tail_storage_generator_membership,
    ensure_transformer_node_memberships,
)

from r2x_core import PluginContext, Rule, System, apply_rules_to_context
from r2x_core.logger import setup_logging
from r2x_core.store import DataStore

setup_logging(verbosity=2)

# =====================================
# Paths
# =====================================
sys_name = "MySystem"
sys = Path("path/to/sys" / f"{sys_name}.json")

# =====================================
# Sienna Parser
# =====================================
weather_year = 2012
model_year = 2029
json_path = Path(sys)
sienna_config = SiennaConfig(
    json_path=str(json_path),
    model_year=model_year,
    system_name=sys_name,
    skip_validation=True,
    models=("r2x_sienna.models", "r2x_plexos.models"),
)
store = DataStore.from_data_files([], path=json_path.parent)
context = PluginContext(
    config=sienna_config,
    store=store,
    skip_validation=True,
)
parser = cast(SiennaParser, SiennaParser.from_context(context))

sienna_sys = parser.run()
sienna_sys = sienna_sys.system
context.source_system = sienna_sys

tmp_dir = sienna_sys.get_time_series_directory()
sienna_sys.convert_storage(
    time_series_directory=tmp_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True,
)

# =====================================
# Rules Definition
# =====================================
rules_path = files("r2x_sienna_to_plexos.config") / "rules.json"
rules = Rule.from_records(json.loads(rules_path.read_text()))
context.rules = rules

# =====================================
# Sienna to PLEXOS (Translation)
# =====================================
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
context.target_system = plexos_sys

apply_rules_to_context(context)
ensure_region_node_memberships(context)
ensure_generator_node_memberships(context)
ensure_battery_node_memberships(context)
ensure_node_zone_memberships(context)
ensure_reserve_battery_memberships(context)
ensure_reserve_generator_memberships(context)
ensure_transformer_node_memberships(context)
ensure_interface_line_memberships(context)
ensure_head_storage_generator_membership(context)
ensure_tail_storage_generator_membership(context)

# =====================================
# PLEXOS Exporter
# =====================================
results_dir = "path/to/output_dir"
results_dir.mkdir(exist_ok=True)

plexos_config = PLEXOSConfig(
    model_name=case_name,
    timeseries_dir=output_path,
    horizon_year=weather_year,
)
exporter_context = PluginContext(
    config=plexos_config,
    system=plexos_sys,
)
exporter = PLEXOSExporter.from_context(exporter_context)
exporter.output_path = results_dir
exporter.solve_year = model_year
exporter.weather_year = weather_year

exporter.on_export()
```

### Parameters

#### `SiennaConfig`

- **`json_path`** (str): Path to the Sienna system JSON file (e.g., `"/path/to/MySystem/MySystem.json"`).
- **`model_year`** (int, optional): Model year for the simulation. Default is `2029`.
- **`system_name`** (str): Name of the system (used for file naming and identification).
- **`skip_validation`** (bool, optional): Skip validation during parsing. Default is `False`.
- **`models`** (tuple, optional): Model namespaces to load. Default includes `r2x_sienna.models` and `r2x_plexos.models`.

#### `PLEXOSConfig`

- **`model_name`** (str): Name of the PLEXOS model (used for output file naming).
- **`timeseries_dir`** (str): Path to the directory where time series and output files will be saved.

## Translation Rules

Translation rules are defined in `config/rules.json`. These rules specify how Sienna components are mapped to PLEXOS components, including field mappings, getters, and filters.

## Membership Utilities

After applying the main translation rules, the following membership helpers must be called to wire up component relationships in the PLEXOS system:

| Function | Description |
|---|---|
| `ensure_region_node_memberships` | Links regions to their child nodes |
| `ensure_generator_node_memberships` | Links generators to their buses |
| `ensure_battery_node_memberships` | Links batteries to their buses |
| `ensure_node_zone_memberships` | Links nodes to their load zones |
| `ensure_reserve_generator_memberships` | Links reserves to contributing generators |
| `ensure_reserve_battery_memberships` | Links reserves to contributing batteries |
| `ensure_transformer_node_memberships` | Links transformers to their from/to nodes |
| `ensure_interface_line_memberships` | Links interfaces to their member lines |
| `ensure_head_storage_generator_membership` | Links head storage to its generator |
| `ensure_tail_storage_generator_membership` | Links tail storage to its generator |
