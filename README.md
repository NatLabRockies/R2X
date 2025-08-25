### R2X
> Model translation parsing tool (ReEDS to X)
>
> [![image](https://img.shields.io/pypi/v/r2x.svg)](https://pypi.python.org/pypi/r2x)
> [![image](https://img.shields.io/pypi/l/r2x.svg)](https://pypi.python.org/pypi/r2x)
> [![image](https://img.shields.io/pypi/pyversions/r2x.svg)](https://pypi.python.org/pypi/r2x)
> [![CI](https://github.com/NREL/r2x/actions/workflows/CI.yaml/badge.svg)](https://github.com/NREL/r2x/actions/workflows/CI.yaml)
> [![codecov](https://codecov.io/gh/NREL/r2x/branch/main/graph/badge.svg)](https://codecov.io/gh/NREL/r2x)
> [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
> [![Documentation](https://github.com/NREL/R2X/actions/workflows/docs-build.yaml/badge.svg?branch=main)](https://nrel.github.io/R2X/)


## Table of contents
* [Installation](#installation)
* [Features](#features)
* [Documentation](#documentation)
* [Roadmap](#roadmap)
* [Compatibility](#compatibility)


## Installation

Install R2X on your local Python installation from PyPi

```console
python -m pip install r2x
```

Or use it as standalone tool,

```console
uvx r2x --help
```

## Features

- [PowerSystem.jl](https://github.com/NREL-Sienna/PowerSystems.jl) model representations
- Translate [ReEDS](https://github.com/NREL/ReEDS-2.0) models to PCM models like [Sienna](https://github.com/NREL-Sienna) or PLEXOS,
- Translate from PLEXOS XML's to Sienna,
- Comprehensive PLEXOS XML parser,

## Documentation

R2X documentation is available at [https://nrel.github.io/R2X/](https://nrel.github.io/R2X/)


## Roadmap

If you're curious about what we're working on, check out the roadmap:

- [Active issues](https://github.com/NREL/R2X/issues?q=is%3Aopen+is%3Aissue+label%3A%22Working+on+it+%F0%9F%92%AA%22+sort%3Aupdated-asc): Issues that we are actively working on.
- [Prioritized backlog](https://github.com/NREL/R2X/issues?q=is%3Aopen+is%3Aissue+label%3ABacklog): Issues we'll be working on next.
- [Nice-to-have](https://github.com/NREL/R2X/labels/Optional): Nice to have features or Issues to fix. Anyone can start working on (please let us know before you do).
- [Ideas](https://github.com/NREL/R2X/issues?q=is%3Aopen+is%3Aissue+label%3AIdea): Future work or ideas for R2X.


## Model compatibility

| R2X Version  | Supported Input Model Versions           | Supported Output Model Versions          |
|--------------|----------------------------------------- |----------------------------------------- |
|     1.0      | ReEDS (v2024.8.0)                        | PLEXOS (9.0, 9.2, 10)                    |
|              | Sienna (PSY 3.0)                         | Sienna (PSY 3.0, 4.0)                    |
|              | PLEXOS (9.0, 9.2, 10)                    |                                          |

### Licence

R2X is released under a BSD 3-Clause License.

R2X was developed under software record SWR-24-91 at the National Renewable Energy Laboratory (NREL).
