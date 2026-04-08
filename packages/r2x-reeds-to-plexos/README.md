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
