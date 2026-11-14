# r2x-reeds-to-sienna

Translate ReEDS systems into Sienna models.

## Overview

This package provides a translation plugin to convert ReEDS run outputs into Sienna system models. The translation applies mapping rules and getters to transform ReEDS components (generators, transmission lines, etc.) into their Sienna equivalents.

## Usage

### Basic Example

```python
from r2x_reeds_to_sienna.translation import ReedsToSiennaTranslation
from r2x_core.logger import setup_logging

# Inspect translation process by logging level
setup_logging(level="DEBUG")

# Initialize the translation
translation = ReedsToSiennaTranslation(
    run_path="/path/to/reeds/run",
    folder_path="/path/to/output",
    case_name="my_case",
    solve_year=2030,
    weather_year=2012
)

# Run the translation
translation.run(run_upgrader=True)
```

### Parameters

- **`run_path`** (str): Path to the ReEDS run folder containing the input data.
- **`folder_path`** (str): Path to the directory where output files will be saved.
- **`case_name`** (str): Name of the case (used for output file naming).
- **`solve_year`** (int, optional): The solve year for the ReEDS data.
- **`weather_year`** (int, optional): The weather year for time series data.

### Translation rules

Defined in `config/translation_rules.json`. These rules specify how ReEDS components are mapped to Sienna components, including field mappings, getters, and filters.

## Ramp Rates

Thermal and hydro ReEDS generator `ramp_rate` values are fractions of installed
generator capacity per minute. Parsed inputs and PCM defaults must preserve this
fraction through generator splitting.

Sienna `ramp_limits` are per-unit/min on the generator's device base. Translation
multiplies the fractional rate by the final generator capacity to obtain MW/min,
then divides by that same capacity to obtain device-base per-unit/min. There is
no hour-to-minute conversion. A `0.05` fraction/min rate therefore yields
`up = down = 0.05` per-unit/min on both a 320 MW unit and a 60 MW remainder.

When the source rate is missing, the existing `max_ramp_up_percentage` fallback
is also a fractional rate per minute (e.g., `0.05`, not `5`). Default lookup and
missing-rate behavior are unchanged by this unit correction.

Previously saved ReEDS systems containing capacity-scaled PCM ramp values must
be rebuilt from inputs with the corrected r2x-reeds implementation. The translator
does not infer the representation from the magnitude of an incoming number.
