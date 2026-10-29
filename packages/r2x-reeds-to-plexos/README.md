# r2x-reeds-to-plexos

Translate ReEDS systems into PLEXOS models.

## Overview

This package provides a translation plugin to convert ReEDS run outputs into PLEXOS XML format. The translation applies mapping rules and getters to transform ReEDS components (generators, transmission lines, regions, etc.) into their PLEXOS equivalents.

## Usage

### Basic Example

```python
from r2x_reeds_to_plexos.translation import ReedsToPlexosTranslation

from r2x_core.logger import setup_logging

# Define level of printing to show progress
setup_logging(level="DEBUG")

# Initialize the translation
translation = ReedsToPlexosTranslation(
    run_path="/path/to/reeds/run",
    output_folder="/path/to/output",
    case_name="my_case",
    solve_year=2030,
    weather_year=2012
)

# Run the translation
translation.run()

# Run with upgrader (if needed to upgrade ReEDS data format)
translation.run(run_upgrader=True)
```

### Parameters

- **`run_path`** (str): Path to the ReEDS run folder containing the input data.
- **`output_folder`** (str): Path to the directory where output files will be saved.
- **`case_name`** (str): Name of the case (used for output file naming).
- **`solve_year`** (int, optional): The solve year for the ReEDS data. Default is `2030`.
- **`weather_year`** (int, optional): The weather year for time series data. Default is `2012`.

## Translation Rules

Translation rules are defined in `config/rules.json`. These rules specify how ReEDS components are mapped to PLEXOS components, including field mappings, getters, and filters.

## Startup Costs

ReEDS `startup_cost` and PCM startup defaults are coefficients in dollars per MW.
Keep this coefficient unchanged when applying PCM defaults or splitting generators.
Translation multiplies it once by the final generator capacity to produce PLEXOS
Start Cost in dollars. Each translated generator has `Units = 1`.

For example, a $68/MW coefficient produces $6,800 for 100 MW and $21,760 for
320 MW. A 700 MW gas-cc generator split into 320, 320, and 60 MW units with the
$79/MW PCM default produces $25,280, $25,280, and $4,740.

> [!WARNING]
> `r2x-reeds-to-plexos` 0.2.1 and `r2x-reeds` 0.9.0 and 0.9.2 can produce
> incorrect startup costs through missing or duplicated capacity scaling.
> The coordinated corrections are tracked in
> [ReEDS #114](https://github.com/NatLabRockies/r2x-reeds/pull/114) and
> [R2X #340](https://github.com/NatLabRockies/R2X/pull/340).

## Hydro Budget Resolution

Set `hydro_budget_ts` on the translation plugin to control the PLEXOS hydro
energy constraint resolution. Supported values are `hourly`, `daily`, `weekly`,
and `monthly`; the default is `daily`, which preserves ReEDS daily hydro flexibility.

```yaml
config:
    r2x-reeds-to-plexos.reeds-to-plexos:
        solve_year: ${solve_year}
        hydro_budget_ts: monthly
```

The ReEDS capacity-factor series is combined with generator capacity to create
energy totals for the selected PLEXOS constraint period.
