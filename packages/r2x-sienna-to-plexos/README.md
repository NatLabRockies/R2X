<img src="../../docs/src/assets/r2x-logo-full-square.svg" alt="R2X framework logo" align="left" width="220px" height="220px" hspace="10"/>
<img align="left" alt="" width="0" height="220px" hspace="10"/>

#### r2x-sienna-to-plexos
<p><small>Translate parsed Sienna systems into PLEXOS models.</small></p>

[![PyPI](https://img.shields.io/pypi/v/r2x-sienna-to-plexos.svg)](https://pypi.org/project/r2x-sienna-to-plexos/) [![Python](https://img.shields.io/pypi/pyversions/r2x-sienna-to-plexos.svg)](https://pypi.org/project/r2x-sienna-to-plexos/) [![Docs](https://img.shields.io/badge/docs-guides-0079c2?style=flat-square)](https://natlabrockies.github.io/R2X/how-to/sienna-to-plexos/) [![License](https://img.shields.io/pypi/l/r2x-sienna-to-plexos.svg)](../../LICENSE.txt)

<br clear="left">

`r2x-sienna-to-plexos` applies component mapping rules and attaches time series to a parsed
Sienna system. The public `sienna_to_plexos(system, config)` function returns
a target system; the PLEXOS exporter writes native output files. Parsing,
translation, and export are separate steps.

## Install

In an activated Python environment supported by this package:

```bash
python -m pip install r2x-sienna-to-plexos
python -m pip check
```

For a CLI-managed environment, use `r2x install r2x-sienna-to-plexos` instead. See
[installation](https://natlabrockies.github.io/R2X/getting-started/installation/)
for runtime selection and plugin discovery.

## Verify the configuration

This example runs without model input files. It checks the public configuration
and the packaged mapping rules before you prepare a full translation:

```pycon
>>> import json
>>> from importlib.resources import files
>>> from r2x_sienna_to_plexos.plugin_config import SiennaToPlexosConfig
>>> config = SiennaToPlexosConfig()
>>> assert config.hydro_budget_ts == 'weekly'
>>> assert "r2x_sienna.models" in config.models
>>> rules = json.loads(files("r2x_sienna_to_plexos.config").joinpath("rules.json").read_text())
>>> assert isinstance(rules, list) and len(rules) > 0
```

Continue with the [complete Sienna → PLEXOS workflow](https://natlabrockies.github.io/R2X/how-to/sienna-to-plexos/)
for input requirements, parsing, translation, and export. A translation requires
real source components and their companion time-series files; configuration
validation alone does not validate a model.

<span id=""></span>
<span id="basic-example"></span>
<span id="membership-utilities"></span>
<span id="overview"></span>
<span id="parameters"></span>
<span id="paths"></span>
<span id="plexos-exporter"></span>
<span id="plexosconfig"></span>
<span id="rules-definition"></span>
<span id="sienna-parser"></span>
<span id="sienna-to-plexos-translation"></span>
<span id="siennaconfig"></span>
<span id="translation-rules"></span>
<span id="usage"></span>

## Mapping and API

- [Function and configuration reference](https://natlabrockies.github.io/R2X/reference/python-api/#sienna_to_plexos)
- [Property mappings](https://natlabrockies.github.io/R2X/reference/sienna-to-plexos-properties/)
- [Translation source](src/r2x_sienna_to_plexos/translation.py) and [packaged rules](src/r2x_sienna_to_plexos/config/rules.json)
- [Troubleshooting](https://natlabrockies.github.io/R2X/troubleshooting/)
