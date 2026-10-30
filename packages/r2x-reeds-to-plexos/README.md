<img src="../../docs/src/assets/r2x-logo-full-square.svg" alt="R2X framework logo" align="left" width="220px" height="220px" hspace="10"/>
<img align="left" alt="" width="0" height="220px" hspace="10"/>

#### r2x-reeds-to-plexos
<p><small>Translate parsed ReEDS systems into PLEXOS models.</small></p>

[![PyPI](https://img.shields.io/pypi/v/r2x-reeds-to-plexos.svg)](https://pypi.org/project/r2x-reeds-to-plexos/) [![Python](https://img.shields.io/pypi/pyversions/r2x-reeds-to-plexos.svg)](https://pypi.org/project/r2x-reeds-to-plexos/) [![Docs](https://img.shields.io/badge/docs-guides-0079c2?style=flat-square)](https://natlabrockies.github.io/R2X/how-to/reeds-to-plexos/) [![License](https://img.shields.io/pypi/l/r2x-reeds-to-plexos.svg)](../../LICENSE.txt)

<br clear="left">

`r2x-reeds-to-plexos` applies component mapping rules and attaches time series to a parsed
ReEDS system. The public `reeds_to_plexos(system, config)` function returns
a target system; the PLEXOS exporter writes native output files. Parsing,
translation, and export are separate steps.

## Install

In an activated Python environment supported by this package:

```bash
python -m pip install r2x-reeds-to-plexos
python -m pip check
```

For a CLI-managed environment, use `r2x install r2x-reeds-to-plexos` instead. See
[installation](https://natlabrockies.github.io/R2X/getting-started/installation/)
for runtime selection and plugin discovery.

## Verify the configuration

This example runs without model input files. It checks the public configuration
and the packaged mapping rules before you prepare a full translation:

```pycon
>>> import json
>>> from importlib.resources import files
>>> from r2x_reeds_to_plexos.plugin_config import ReedsToPlexosConfig
>>> config = ReedsToPlexosConfig()
>>> assert config.hydro_budget_ts == 'daily'
>>> assert "r2x_reeds.models" in config.models
>>> rules = json.loads(files("r2x_reeds_to_plexos.config").joinpath("rules.json").read_text())
>>> assert isinstance(rules, list) and len(rules) > 0
```

Continue with the [complete ReEDS → PLEXOS workflow](https://natlabrockies.github.io/R2X/how-to/reeds-to-plexos/)
for input requirements, parsing, translation, and export. A translation requires
real source components and their companion time-series files; configuration
validation alone does not validate a model.

<span id="basic-example"></span>
<span id="define-level-of-printing-to-show-progress"></span>
<span id="initialize-the-translation"></span>
<span id="overview"></span>
<span id="parameters"></span>
<span id="run-the-translation"></span>
<span id="run-with-upgrader-if-needed-to-upgrade-reeds-data-format"></span>
<span id="translation-rules"></span>
<span id="usage"></span>

## Mapping and API

- [Function and configuration reference](https://natlabrockies.github.io/R2X/reference/python-api/#reeds_to_plexos)
- [Property mappings](https://natlabrockies.github.io/R2X/reference/reeds-to-plexos-properties/)
- [Translation source](src/r2x_reeds_to_plexos/translation.py) and [packaged rules](src/r2x_reeds_to_plexos/config/rules.json)
- [Troubleshooting](https://natlabrockies.github.io/R2X/troubleshooting/)

## Startup Costs

ReEDS `startup_cost` and PCM startup defaults are coefficients in dollars per MW.
Keep this coefficient unchanged when applying PCM defaults or splitting generators.
Translation multiplies it once by the final generator capacity to produce PLEXOS
Start Cost in dollars. Each translated generator has `Units = 1`.

For example, a $68/MW coefficient produces $6,800 for 100 MW and $21,760 for
320 MW. A 700 MW gas-cc generator split into 320, 320, and 60 MW units with the
$79/MW PCM default produces $25,280, $25,280, and $4,740.

> [!WARNING]
> `r2x-reeds-to-plexos` 0.2.1 and `r2x-reeds` 0.9.0 and 0.9.2 can produce
> incorrect startup costs through missing or duplicated capacity scaling.
> The coordinated corrections are tracked in
> [ReEDS #114](https://github.com/NatLabRockies/r2x-reeds/pull/114) and
> [R2X #340](https://github.com/NatLabRockies/R2X/pull/340).

## Hydro Budget Resolution

Set `hydro_budget_ts` on the translation plugin to control the PLEXOS hydro
energy constraint resolution. Supported values are `hourly`, `daily`, `weekly`,
and `monthly`; the default is `daily`, which preserves ReEDS daily hydro flexibility.

```yaml
config:
    r2x-reeds-to-plexos.reeds-to-plexos:
        solve_year: ${solve_year}
        hydro_budget_ts: monthly
```

The ReEDS capacity-factor series is combined with generator capacity to create
energy totals for the selected PLEXOS constraint period.
