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
