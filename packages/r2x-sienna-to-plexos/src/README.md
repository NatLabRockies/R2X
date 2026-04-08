# r2x-sienna-to-plexos

Translate Sienna systems into PLEXOS models.

## Overview

This package provides a translation plugin to convert Sienna system models into PLEXOS XML format. The translation applies mapping rules and getters to transform Sienna components (generators, buses, lines, etc.) into their PLEXOS equivalents.

## Usage

### Basic Example

```python
from r2x_sienna_to_plexos.translation import SiennaToPlexosTranslation

from r2x_core.logger import setup_logging

# Run translation with custom logging level
setup_logging(level="DEBUG")

# Initialize the translation
translation = SiennaToPlexosTranslation(
    sienna_file="/path/to/sienna/system.json",
    output_folder="/path/to/output",
    case_name="my_case"
)

# Run the translation
translation.run(run_upgrader=True)
```

### Parameters

- **`sienna_file`** (str): Path to the Sienna system JSON file containing the input data.
- **`output_folder`** (str): Path to the directory where output files will be saved.
- **`case_name`** (str): Name of the case (used for output file naming).

Translation rules are defined in `config/rules.json`. These rules specify how Sienna components are mapped to PLEXOS components, including field mappings, getters, and filters.
