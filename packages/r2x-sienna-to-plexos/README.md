# r2x-sienna-to-plexos

Translate Sienna systems into PLEXOS models.

## Overview

This package provides a translation plugin to convert Sienna system models into PLEXOS XML format. The translation applies mapping rules and getters to transform Sienna components (generators, buses, lines, transformers, etc.) into their PLEXOS equivalents.

## Usage

### Basic Example

```python
from r2x_sienna_to_plexos.translation import SiennaToPlexosTranslation

from r2x_core.logger import setup_logging

# Define level of printing to show progress
setup_logging(level="DEBUG")

# Initialize the translation
translation = SiennaToPlexosTranslation(
    sienna_file="/path/to/sienna/system.json",
    output_folder="/path/to/output",
    case_name="my_case",
    model_year=2029,
    scenario="Base",
    system_base_power=100.0,
)

# Run the translation
translation.run()

# Run with upgrader (if needed to upgrade Sienna data from psy4 to psy5 format)
translation.run(run_upgrader=True)
```

### Parameters

- **`sienna_file`** (str): Path to the Sienna system JSON file containing the input data.
- **`output_folder`** (str): Path to the directory where output files will be saved.
- **`case_name`** (str): Name of the case (used for output file naming).
- **`model_year`** (int, optional): Model year for the Sienna system. Default is `2029`.
- **`scenario`** (str, optional): Scenario name. Default is `"Base"`.
- **`system_base_power`** (float, optional): System base power in MVA. Default is `100.0`.
- **`skip_validation`** (bool, optional): Skip validation during parsing. Default is `False`.
- **`exclude_defaults`** (bool, optional): Exclude default values in PLEXOS export. Default is `True`.

## Translation Rules

Translation rules are defined in `config/rules.json`. These rules specify how Sienna components are mapped to PLEXOS components, including field mappings, getters, and filters.
