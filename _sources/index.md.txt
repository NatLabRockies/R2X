# R2X Translation Plugins

Translation plugins for power system models.
ReEDS, PLEXOS, Sienna — any direction.

This repo houses the translation plugins for the
[r2x-cli](https://github.com/NatlabRockies/r2x-cli) ecosystem.
For the core framework (plugin architecture, rules engine, System,
DataStore, units), see
[r2x-core](https://nrel.github.io/r2x-core/).

## Translation Plugins

| Package | Direction | Rules |
| --- | --- | ---: |
| [`r2x-reeds-to-plexos`](https://github.com/NatlabRockies/R2X/tree/main/packages/r2x-reeds-to-plexos) | ReEDS → PLEXOS | 34 |
| [`r2x-reeds-to-sienna`](https://github.com/NatlabRockies/R2X/tree/main/packages/r2x-reeds-to-sienna) | ReEDS → Sienna | — |
| [`r2x-plexos-to-sienna`](https://github.com/NatlabRockies/R2X/tree/main/packages/r2x-plexos-to-sienna) | PLEXOS → Sienna | 21 |
| [`r2x-sienna-to-plexos`](https://github.com/NatlabRockies/R2X/tree/main/packages/r2x-sienna-to-plexos) | Sienna → PLEXOS | 44 |

## Model Compatibility

| R2X Version | Supported Inputs | Supported Outputs |
| --- | --- | --- |
| 2.0 | ReEDS (v2024.8.0) | PLEXOS (9.0, 9.2, 10, 11) |
|     | Sienna (PSY 4.0) | Sienna (PSY 4.0, 5.0) |
|     | PLEXOS (9.0, 9.2, 10, 11) | |

## Ecosystem

| Package | Description |
| --- | --- |
| [r2x-cli](https://github.com/NatlabRockies/r2x-cli) | Rust CLI that discovers, installs, and runs any r2x plugin |
| [r2x-core](https://github.com/NatlabRockies/r2x-core) | Shared plugin framework: `PluginContext`, `Rule`, `System`, `@getter` registry |
| [r2x-reeds](https://github.com/NatlabRockies/r2x-reeds) | ReEDS parser, transform plugins, and component models |
| [r2x-plexos](https://github.com/NatlabRockies/r2x-plexos) | PLEXOS parser/exporter and component models |
| [r2x-sienna](https://github.com/NREL-Sienna/r2x-sienna) | Sienna parser/exporter and PowerSystems.jl-compatible models |
| [infrasys](https://github.com/NatlabRockies/infrasys) | Foundational System container and time series management |
| [plexosdb](https://github.com/NatlabRockies/plexosdb) | Standalone PLEXOS XML database reader/writer |

## Roadmap

- [Active issues](https://github.com/NatlabRockies/R2X/issues?q=is%3Aopen+is%3Aissue+label%3A%22Working+on+it+%F0%9F%92%AA%22+sort%3Aupdated-asc):
  Currently in progress.
- [Prioritized backlog](https://github.com/NatlabRockies/R2X/issues?q=is%3Aopen+is%3Aissue+label%3ABacklog):
  Up next.
- [Nice-to-have](https://github.com/NatlabRockies/R2X/labels/Optional):
  Community contributions welcome.
- [Ideas](https://github.com/NatlabRockies/R2X/issues?q=is%3Aopen+is%3Aissue+label%3AIdea):
  Future directions for R2X.

```{toctree}
:hidden: true
CHANGELOG.md
```
