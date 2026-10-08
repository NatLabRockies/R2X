# ReEDS → Sienna

Cloning the necessary packages for each translation is important.

## Mapping Overview

ReEDS technologies are translated into Sienna component families. Several
ReEDS classes intentionally map to the same Sienna class, while demand and
storage classes use dedicated target types.

```{mermaid}
flowchart LR
    region[ReEDSRegion] --> bus[ACBus]
    region --> area[Area]
    reserve[ReEDSReserve] --> spinning[VariableReserve]
    reserve --> nonSpinning[VariableReserveNonSpinning]
    thermal[ReEDSThermalGenerator] --> thermalTarget[ThermalStandard]
    variable[ReEDSVariableGenerator] --> renewable[RenewableDispatch]
    variable --> nonDispatch[RenewableNonDispatch]
    hydro[ReEDSHydroGenerator] --> hydroDispatch[HydroDispatch]
    hydro --> hydroNonDispatch[RenewableNonDispatch]
    storage[ReEDSStorage] --> battery[EnergyReservoirStorage]
    storage --> pump[HydroPumpTurbine]
    storage --> reservoir[HydroReservoir]
    demand[ReEDSDemand] --> load[PowerLoad]
    electro[ReEDSElectrolyzerDemand] --> standardLoad[StandardLoad]
    smr[ReEDSSteamMethaneReformingDemand] --> standardLoad
    datacenter[ReEDSDataCenterDemand] --> standardLoad
    consuming[ReEDSConsumingTechnology] --> standardLoad
    transmission[ReEDSTransmissionLine] --> line[Line / MonitoredLine / HVDC]
    interface[ReEDSInterface] --> interchange[AreaInterchange]

    click thermal "https://github.com/NatLabRockies/R2X/blob/main/packages/r2x-reeds-to-sienna/src/r2x_reeds_to_sienna/config/rules.json" "Open ReEDS-to-Sienna rules"
    click demand "#demand-and-storage" "Read demand mappings"
    click storage "#demand-and-storage" "Read storage mappings"
```

### Demand and Storage

The demand-specific classes (`ReEDSElectrolyzerDemand`,
`ReEDSSteamMethaneReformingDemand`, `ReEDSDataCenterDemand`, and
`ReEDSConsumingTechnology`) become `StandardLoad`. Their time series and
annual demand information are attached by the translation helpers.

For field-by-field mappings, see [ReEDS to Sienna property mappings](reeds_to_sienna_properties.md).

## Setup

```bash
uv sync --upgrade
uv add --editable /path/to/r2x-reeds
uv add --editable /path/to/r2x-sienna
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
from r2x_reeds import ReEDSConfig, ReEDSParser
from r2x_reeds_to_sienna.getter_utils import add_generator_emissions
from r2x_sienna.exporter import SiennaExporter
from r2x_sienna.plugin_config import SiennaConfig

from r2x_core import DataStore, PluginContext, Rule, System, apply_rules_to_context  # type: ignore
from r2x_core.logger import setup_logging  # type: ignore

setup_logging(verbosity=2)

case_name = "reeds_run_folder_name"
base_path = "/path/to/reeds/runs"
run_path = Path(base_path) / case_name

# =====================================
# ReEDS PARSER
# =====================================
solve_year = 2035
weather_year = 2012
scenario = "base"
reeds_config = ReEDSConfig(
    solve_year=solve_year,
    weather_year=weather_year,
    case_name=case_name,
    scenario=scenario,
    models=("r2x_reeds.models", "r2x_sienna.models"),
)

store = DataStore.from_plugin_config(reeds_config, path=run_path)
context = PluginContext(config=reeds_config, store=store)

parser = cast(ReEDSParser, ReEDSParser.from_context(context))
reeds_sys = parser.run()
reeds_sys = reeds_sys.system
context.source_system = reeds_sys
# breakpoint()
tmp_dir = reeds_sys.get_time_series_directory()

reeds_sys.convert_storage(
    time_series_directory=tmp_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True,
)

# =====================================
# Rules Definition
# =====================================
rules_path = files("r2x_reeds_to_sienna.config") / "rules.json"
rules = Rule.from_records(json.loads(rules_path.read_text()))
context.rules = rules

# =====================================
# ReEDS to Sienna (TRANSLATION)
# =====================================
connection = create_in_memory_db()
ts_manager = TimeSeriesManager(
    connection,
    time_series_directory=tmp_dir,
    time_series_storage_type=TimeSeriesStorageType.ARROW,
    permanent=True
)

sienna_sys = System(
    name="Sienna",
    auto_add_composed_components=True,
    time_series_manager=ts_manager,
    system_base=100.0,
)
context.target_system = sienna_sys
apply_rules_to_context(context)
add_generator_emissions(context)

# =====================================
# Sienna Exporter
# =====================================
results_dir = Path(base_path) / f"{case_name}_results"
results_dir.mkdir(exist_ok=True)

exported_system = f"{case_name}.json"
output_file = results_dir / exported_system
sienna_config = SiennaConfig(
    model_year=solve_year,
    system_name=exported_system,
    output_path=str(output_file),
    system_base_power=100.0,
    scenario=scenario,
)

exporter_context = PluginContext(
    config=sienna_config,
    system=sienna_sys,
)
exporter = SiennaExporter.from_context(exporter_context)
exporter.on_export()
```
