# ReEDS → PLEXOS

Cloning the necessary packages for each translation is important.

## Setup

```bash
uv sync --upgrade
uv add --editable /path/to/r2x-reeds
uv add --editable /path/to/r2x-plexos
```

## Example Script

```python
from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path
from typing import cast

from infrasys.time_series_manager import TimeSeriesManager
from infrasys.time_series_models import TimeSeriesStorageType
from infrasys.utils.sqlite import create_in_memory_db
from loguru import logger
from r2x_plexos import PLEXOSConfig
from r2x_plexos.exporter import PLEXOSExporter  # type: ignore
from r2x_reeds import ReEDSConfig, ReEDSParser  # type: ignore
from r2x_reeds.sysmod.break_gens import BreakGensConfig, break_generators  # type: ignore
from r2x_reeds.sysmod.purchaser_load import PurchaserLoadConfig, add_purchaser_load  # type: ignore
from r2x_reeds_to_plexos import (
    attach_region_load_time_series,
    attach_reserve_time_series,
    attach_time_series_to_generators,
)
from r2x_reeds_to_plexos.getters_utils import attach_time_series_to_purchasers

from r2x_core import DataStore, PluginContext, Rule, System, apply_rules_to_context  # type: ignore
from r2x_core.logger import setup_logging  # type: ignore


logger.enable("r2x_reeds")
setup_logging(verbosity=2)

case_name = "test_Pacific"
base_path = "/Users/mvelasqu/Documents/marck/GDO/test-r2x-translations/reeds-to-plexos"

# =====================================
# ReEDS PARSER
# =====================================
run_path = Path(base_path) / case_name
solve_year = 2050
weather_year = 2012
reeds_config = ReEDSConfig(
    solve_year=solve_year,
    weather_year=weather_year,
    case_name=case_name,
    scenario="base",
    models=("r2x_reeds.models", "r2x_plexos.models"),
)
store = DataStore.from_plugin_config(reeds_config, path=run_path)
context = PluginContext(config=reeds_config, store=store)

parser = cast(ReEDSParser, ReEDSParser.from_context(context))
parser.on_prepare()
parser.on_upgrade()

reeds_sys = parser.run()
reeds_sys = reeds_sys.system
context.source_system = reeds_sys

# ===========================================
# ReEDS System Modifier: Add purchaser loads
# ==========================================
inputs_case_path = run_path / "inputs_case"
ouputs_case_path = run_path / "outputs"
purchaser_load_config = PurchaserLoadConfig(
    models=("r2x_reeds.models", "r2x_plexos.models"),
    solve_year=solve_year,
    weather_year=weather_year,
    hydrogen_production_capacity_fpath=ouputs_case_path / "cap.csv",
    consume_characteristics_fpath=inputs_case_path / "consume_char.csv",
    hydrogen_production_load_fpath=ouputs_case_path / "prod_load.csv",
    hydrogen_production_annual_load_fpath=ouputs_case_path / "prod_load_ann.csv",
    loadsite_op_fpath=ouputs_case_path / "loadsite_op.csv",
    hour_map_myr_fpath=inputs_case_path / "rep" / "hmap_myr.csv",
)
purchaser_load_result = add_purchaser_load(reeds_sys, purchaser_load_config)
if purchaser_load_result.is_err():
    raise RuntimeError(f"Failed to add purchaser loads: {purchaser_load_result.unwrap_err()}")

reeds_sys = purchaser_load_result.unwrap()
context.source_system = reeds_sys

# ==========================================
# ReEDS System Modifier: Break generators
# ==========================================
break_gens_config = BreakGensConfig(
    models=("r2x_reeds.models", "r2x_plexos.models"),
    reference_units=None,
    drop_capacity_threshold=5,
    skip_categories=None,
    break_category="category",
    include_regions=None,
    include_generators=[
        "biopower_init-1_p103",
        "biopower_init-1_p123",
    ],
    include_technologies=["coal-new", "coaloldscr"],
)
break_gens_result = break_generators(reeds_sys, break_gens_config)
if break_gens_result.is_err():
    raise RuntimeError(f"Failed to break selected generators/technologies: {break_gens_result.unwrap_err()}")

reeds_sys = break_gens_result.unwrap()
context.source_system = reeds_sys

# =========================================================
# Handle time series path dynamically based on ReEDS config
# =========================================================

tmp_dir = reeds_sys.get_time_series_directory()

reeds_sys.convert_storage(
    time_series_directory=tmp_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True,
)

# =====================================
# Rules Definition (r2x-core)
# =====================================
rules_path = files("r2x_reeds_to_plexos.config") / "rules.json"
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
# ReEDS to PLEXOS (TRANSLATION) (r2x-reeds-to-plexos)
# =====================================
plexos_sys = System(
    name="PLEXOS",
    auto_add_composed_components=True,
    time_series_manager=ts_manager
)
context.target_system = plexos_sys

apply_rules_to_context(context)
attach_reserve_time_series(context)
attach_time_series_to_generators(context)
attach_region_load_time_series(context)
attach_time_series_to_purchasers(context)

# =====================================
# PLEXOS Exporter (r2x-plexos)
# =====================================
output_path = base_path + f"/{case_name}_results"
os.makedirs(output_path, exist_ok=True)

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
exporter.output_path = output_path
exporter.solve_year = solve_year
exporter.weather_year = weather_year

exporter.on_export()
```

The purchaser-load modifier reads hydrogen-production technologies from `cap.csv`. Positive
`electrolyzer`, `smr`, and `smr_ccs` rows for the configured solve year create
`ReEDSElectrolyzerDemand` or `ReEDSSteamMethaneReformingDemand` components. Their hourly profiles
come from `prod_load.csv`, with annual totals from `prod_load_ann.csv`, and are translated to PLEXOS
purchasers by the ReEDS-to-PLEXOS rules.
