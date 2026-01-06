# r2x-reeds-to-sienna

Translate ReEDS systems into Sienna models.

## Overview

This package provides a translation plugin to convert ReEDS run outputs into Sienna system models. The translation applies mapping rules and getters to transform ReEDS components (generators, transmission lines, etc.) into their Sienna equivalents.

## Usage

### Basic Example

```python
from r2x_reeds_to_sienna.translation import ReedsToSiennaTranslation

# Initialize the translation
translation = ReedsToSiennaTranslation(
    run_path="/path/to/reeds/run",          # Path to ReEDS run folder
    folder_path="/path/to/output",          # Path for output files
    case_name="my_case",                    # Name of the case
    solve_year=2030,                        # Year to solve (default: 2030)
    weather_year=2012                       # Weather year (default: 2012)
)

# Run the translation
translation.run()
```

### Parameters

- **`run_path`** (str): Path to the ReEDS run folder containing the input data.
- **`folder_path`** (str): Path to the directory where output files will be saved.
- **`case_name`** (str): Name of the case (used for output file naming).
- **`solve_year`** (int, optional): The solve year for the ReEDS data. Default is `2030`.
- **`weather_year`** (int, optional): The weather year for time series data. Default is `2012`.

Translation rules are defined in `config/translation_rules.json`. These rules specify how ReEDS components are mapped to Sienna components, including field mappings, getters, and filters.
