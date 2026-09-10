# R2X documentation

Translation plugins for ReEDS, PLEXOS, and Sienna model interoperability.

This repository contains the translation layer in the
[r2x-cli](https://github.com/NatlabRockies/r2x-cli) ecosystem. For the shared
plugin architecture, rule engine, `System`, `DataStore`, and units, see
[r2x-core](https://nrel.github.io/r2x-core/).

## Start here

- [Getting started](getting_started.md) explains installation and how to choose
  a translation workflow.
- [Translation workflows](dev_workflow.md) contains end-to-end Python examples.
- [Architecture](architecture.md) explains the parser, translation, and
  exporter boundaries.
- [Development](development.md) covers checks, adding translation directions,
  and maintaining translated documentation.

## Translation plugins

| Package | Direction | Rules |
| --- | --- | ---: |
| [`r2x-reeds-to-plexos`](https://github.com/NatlabRockies/R2X/tree/main/packages/r2x-reeds-to-plexos) | [ReEDS → PLEXOS](reeds_to_plexos.md) · [properties](reeds_to_plexos_properties.md) | 34 |
| [`r2x-reeds-to-sienna`](https://github.com/NatlabRockies/R2X/tree/main/packages/r2x-reeds-to-sienna) | [ReEDS → Sienna](reeds_to_sienna.md) · [properties](reeds_to_sienna_properties.md) | — |
| [`r2x-plexos-to-sienna`](https://github.com/NatlabRockies/R2X/tree/main/packages/r2x-plexos-to-sienna) | [PLEXOS → Sienna](plexos_to_sienna.md) · [properties](plexos_to_sienna_properties.md) | 21 |
| [`r2x-sienna-to-plexos`](https://github.com/NatLabRockies/R2X/tree/main/packages/r2x-sienna-to-plexos) | [Sienna → PLEXOS](sienna_to_plexos.md) · [properties](sienna_to_plexos_properties.md) | 44 |

## Model compatibility

| R2X version | Supported inputs | Supported outputs |
| --- | --- | --- |
| 2.0 | ReEDS (v2024.8.0) | PLEXOS (9.0, 9.2, 10, 11) |
|     | Sienna (PSY 4.0) | Sienna (PSY 4.0, 5.0) |
|     | PLEXOS (9.0, 9.2, 10, 11) | |

## Ecosystem

| Package | Description |
| --- | --- |
| [r2x-cli](https://github.com/NatLabRockies/r2x-cli) | CLI that discovers, installs, and runs r2x plugins |
| [r2x-core](https://github.com/NatLabRockies/r2x-core) | Shared plugin framework and rule engine |
| [r2x-reeds](https://github.com/NatLabRockies/r2x-reeds) | ReEDS parser, transform plugins, and component models |
| [r2x-plexos](https://github.com/NatLabRockies/r2x-plexos) | PLEXOS parser/exporter and component models |
| [r2x-sienna](https://github.com/NREL-Sienna/r2x-sienna) | Sienna parser/exporter and compatible component models |
| [infrasys](https://github.com/NatLabRockies/infrasys) | Foundational `System` container and time-series management |
| [plexosdb](https://github.com/NatLabRockies/plexosdb) | Standalone PLEXOS XML database reader/writer |

## Roadmap

- [Active issues](https://github.com/NatlabRockies/R2X/issues?q=is%3Aopen+is%3Aissue+label%3A%22Working+on+it+%F0%9F%92%AA%22+sort%3Aupdated-asc)
- [Prioritized backlog](https://github.com/NatlabRockies/R2X/issues?q=is%3Aopen+is%3Aissue+label%3ABacklog)
- [Nice-to-have](https://github.com/NatlabRockies/R2X/labels/Optional)
- [Ideas](https://github.com/NatlabRockies/R2X/issues?q=is%3Aopen+is%3Aissue+label%3AIdea)

```{toctree}
:hidden: true
getting_started.md
dev_workflow.md
architecture.md
development.md
CHANGELOG.md
plexos_to_sienna_properties.md
reeds_to_plexos_properties.md
reeds_to_sienna_properties.md
sienna_to_plexos_properties.md
```
