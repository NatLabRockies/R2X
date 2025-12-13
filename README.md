### R2X

> Model translation parsing tool (ReEDS to X)
>
> [![image](https://img.shields.io/pypi/v/r2x.svg)](https://pypi.python.org/pypi/r2x) > [![image](https://img.shields.io/pypi/l/r2x.svg)](https://pypi.python.org/pypi/r2x) > [![image](https://img.shields.io/pypi/pyversions/r2x.svg)](https://pypi.python.org/pypi/r2x) > [![CI](https://github.com/NREL/r2x/actions/workflows/CI.yaml/badge.svg)](https://github.com/NREL/r2x/actions/workflows/CI.yaml) > [![codecov](https://codecov.io/gh/NREL/r2x/branch/main/graph/badge.svg)](https://codecov.io/gh/NREL/r2x) > [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) > [![Documentation](https://github.com/NREL/R2X/actions/workflows/docs-build.yaml/badge.svg?branch=main)](https://nrel.github.io/R2X/)

## Table of contents

- [Installation](#installation)
- [Features](#features)
- [Documentation](#documentation)
- [Roadmap](#roadmap)
- [Compatibility](#compatibility)

## Installation

Install R2X on your local Python installation from PyPi

```console
python -m pip install r2x
```

Or use it as standalone tool,

```console
uvx r2x --help
```

## Quick Start

Use of Sienna parser.

```python
import json

from r2x_sienna.config import SiennaConfig
from r2x_sienna.parser import SiennaParser
from r2x_sienna.upgrader.data_upgrader import SiennaUpgrader
from r2x_core.logger import setup_logging
from r2x_core.store import DataStore
from r2x_core.upgrader_utils import run_upgrade_step

# Use for debugging and see parser/exporter progress
setup_logging(level="DEBUG")

# Use for level info and store logging results to file
setup_logging(level="INFO", log_file="debug.log")

path_to_sys = "path/to/sienna_sys.json"

# Required if upgrading a psy4 to psy5 system
upgrader = SiennaUpgrader(path=path_to_sys)
result = None
with open(path_to_sys) as f:
    loaded_sys = json.load(f)

for step in upgrader.list_steps():
    result = run_upgrade_step(step, data=loaded_sys, upgrader_context={"info": "value"})

config = SiennaConfig(
    model_year=2029,
    system_name="Sienna System",
    json_path=path_to_sys,
    scenario="Base",
    system_base_power=100.0,
    skip_validation=False,
)
data_store = DataStore()
parser = SiennaParser(
    config=config,
    data_store=data_store,
    name=sys_name,
    skip_validation=False,
)
stdin_payload = json.dumps(loaded_sys)
sienna_sys = parser.build_system(stdin_payload=stdin_payload)
```

See the `examples/` directory for more usage patterns including validation, dry-run previews, and custom configuration.

## Features

- Simple, functional API with Result[T, E] pattern
- Validation before translation with helpful error messages
- Dry-run mode to preview translations
- I/O helpers for stdin/stdout workflows
- [PowerSystem.jl](https://github.com/NREL-Sienna/PowerSystems.jl) model representations
- Translate [ReEDS](https://github.com/NREL/ReEDS-2.0) models to PCM models like [Sienna](https://github.com/NREL-Sienna) or PLEXOS
- Translate from PLEXOS XML's to Sienna
- Comprehensive PLEXOS XML parser

## Documentation

R2X documentation is available at [https://nrel.github.io/R2X/](https://nrel.github.io/R2X/)

## Roadmap

If you're curious about what we're working on, check out the roadmap:

- [Active issues](https://github.com/NREL/R2X/issues?q=is%3Aopen+is%3Aissue+label%3A%22Working+on+it+%F0%9F%92%AA%22+sort%3Aupdated-asc): Issues that we are actively working on.
- [Prioritized backlog](https://github.com/NREL/R2X/issues?q=is%3Aopen+is%3Aissue+label%3ABacklog): Issues we'll be working on next.
- [Nice-to-have](https://github.com/NREL/R2X/labels/Optional): Nice to have features or Issues to fix. Anyone can start working on (please let us know before you do).
- [Ideas](https://github.com/NREL/R2X/issues?q=is%3Aopen+is%3Aissue+label%3AIdea): Future work or ideas for R2X.

## Model compatibility

| R2X Version | Supported Input Model Versions | Supported Output Model Versions |
| ----------- | ------------------------------ | ------------------------------- |
| 1.0         | ReEDS (v2024.8.0)              | PLEXOS (9.0, 9.2, 10)           |
|             | Sienna (PSY 3.0)               | Sienna (PSY 3.0, 4.0)           |
|             | PLEXOS (9.0, 9.2, 10)          |                                 |

### Licence

R2X is released under a BSD 3-Clause License.

R2X was developed under software record SWR-24-91 at the National Renewable Energy Laboratory (NREL).
