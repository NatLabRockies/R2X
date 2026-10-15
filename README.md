<img src="./docs/src/assets/r2x-logo-full-square.svg" alt="R2X framework logo" align="left" width="220px" height="220px" hspace="10"/>

#### R2X
<p><small>Translation plugins for ReEDS, PLEXOS, and Sienna.</small></p>

[![CI](https://github.com/NatLabRockies/R2X/actions/workflows/ci.yaml/badge.svg)](https://github.com/NatLabRockies/R2X/actions/workflows/ci.yaml) [![PyPI](https://img.shields.io/pypi/v/r2x.svg)](https://pypi.org/project/r2x/) [![Python](https://img.shields.io/pypi/pyversions/r2x.svg)](https://pypi.org/project/r2x/) [![Docs](https://img.shields.io/badge/docs-guides-0079c2?style=flat-square)](https://natlabrockies.github.io/R2X/) [![License](https://img.shields.io/pypi/l/r2x.svg)](./LICENSE.txt)

<br clear="left">

R2X maps parsed power-system components and time series into a target model.
The [`r2x-cli`](https://github.com/NatLabRockies/r2x-cli) manages plugins and runs
pipelines. [`r2x-core`](https://github.com/NatLabRockies/r2x-core) supplies the
shared system, configuration, and rule APIs.

## Quick Start

Install [r2x-cli](https://github.com/NatLabRockies/r2x-cli#install) and Python
3.11, 3.12, or 3.13. Install the translation plugin for your workflow:

```bash
r2x install r2x-reeds-to-plexos
```

The CLI installs the plugin and its dependencies into its managed environment.
To manage your own Python environment instead:

```bash
python -m pip install r2x-reeds-to-plexos
```

## Documentation

Use the guide that matches your task:

- [Installation](https://natlabrockies.github.io/R2X/getting-started/installation/): prerequisites, published packages, and verification.
- [First CLI pipeline](https://natlabrockies.github.io/R2X/tutorials/getting-started/): run and inspect your first pipeline.
- [Translation workflows](https://natlabrockies.github.io/R2X/how-to/): parse, translate, and export a model.
- [Property reference](https://natlabrockies.github.io/R2X/reference/reeds-to-plexos-properties/): inspect mappings and their source rules.
- [Architecture](https://natlabrockies.github.io/R2X/explanation/architecture/): understand package boundaries.
- [Development](https://natlabrockies.github.io/R2X/how-to/development/): run checks and maintain translations.

The site includes searchable current documentation and release archives.

## Translation Plugins

| Package | Direction |
| --- | --- |
| [`r2x-reeds-to-plexos`](packages/r2x-reeds-to-plexos) | ReEDS → PLEXOS |
| [`r2x-reeds-to-sienna`](packages/r2x-reeds-to-sienna) | ReEDS → Sienna |
| [`r2x-plexos-to-sienna`](packages/r2x-plexos-to-sienna) | PLEXOS → Sienna |
| [`r2x-sienna-to-plexos`](packages/r2x-sienna-to-plexos) | Sienna → PLEXOS |

## Development

From the repository root, install the development environment and run its checks:

```bash
uv sync && uv run prek run --all-files --hook-stage pre-push
```

See [Development](docs/src/content/docs/how-to/development.mdx) for focused checks
and [the documentation README](docs/README.md) for the site build.

## License

BSD-3-Clause. See [LICENSE.txt](./LICENSE.txt).
