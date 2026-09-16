# Getting started

R2X provides translation plugins for ReEDS, PLEXOS, and Sienna. The plugins are
published as separate Python packages and are orchestrated by the
[r2x-cli](https://github.com/NatlabRockies/r2x-cli) ecosystem.

## Prerequisites

Use Python 3.11, 3.12, or 3.13. For a managed environment, install
[uv](https://docs.astral.sh/uv/). For the command-line workflow, install
[r2x-cli](https://github.com/NatlabRockies/r2x-cli) using its
[installation instructions](https://github.com/NatLabRockies/r2x-cli#installation)
before running the `r2x` commands below.

## Install a translation plugin

The CLI installs a plugin and its required parser, exporter, and core packages:

```bash
r2x install r2x-reeds-to-plexos
r2x install r2x-reeds-to-sienna
r2x install r2x-plexos-to-sienna
r2x install r2x-sienna-to-plexos
```

To manage the environment yourself, install a published package with `pip`:

```bash
python -m pip install r2x-reeds-to-plexos
```

See the [workflow guides](dev_workflow.md) for package-specific setup and
examples. Package READMEs may contain older examples while their APIs are being
aligned.

## Choose a workflow

| Source | Target | Guide |
| --- | --- | --- |
| ReEDS | PLEXOS | [ReEDS to PLEXOS](reeds_to_plexos.md) |
| ReEDS | Sienna | [ReEDS to Sienna](reeds_to_sienna.md) |
| PLEXOS | Sienna | [PLEXOS to Sienna](plexos_to_sienna.md) |
| Sienna | PLEXOS | [Sienna to PLEXOS](sienna_to_plexos.md) |

Every workflow needs a parser for the source model, the matching R2X
translation package, and an exporter for the target model. Keep the parser and
exporter versions compatible with the translation package version.

## Run the Python API

The public translation functions accept an `r2x_core.System` and a typed plugin
configuration. A minimal translation call looks like this:

```python
from r2x_core import System
from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig
from r2x_reeds_to_plexos.translation import reeds_to_plexos

source_system = System(name="reeds-source", auto_add_composed_components=True)
translated_system = reeds_to_plexos(source_system, ReedsToPlexosConfig())
```

The source system must contain the component types expected by the selected
translation. Use the workflow guides for parser setup, input paths, time-series
storage, and exporter configuration.

## Verify a local checkout

From a checkout of this repository, install the development environment and run
the tests:

```bash
uv sync
uv run pytest
```

See [development](development.md) for the documentation commands and the
translation-package maintenance workflow.
