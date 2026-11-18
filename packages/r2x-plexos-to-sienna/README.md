<img src="../../docs/src/assets/r2x-logo-full-square.svg" alt="R2X framework logo" align="left" width="220px" height="220px" hspace="10"/>
<img align="left" alt="" width="0" height="220px" hspace="10"/>

#### r2x-plexos-to-sienna
<p><small>Translate parsed PLEXOS systems into Sienna models.</small></p>

[![PyPI](https://img.shields.io/pypi/v/r2x-plexos-to-sienna.svg)](https://pypi.org/project/r2x-plexos-to-sienna/) [![Python](https://img.shields.io/pypi/pyversions/r2x-plexos-to-sienna.svg)](https://pypi.org/project/r2x-plexos-to-sienna/) [![Docs](https://img.shields.io/badge/docs-guides-0079c2?style=flat-square)](https://natlabrockies.github.io/R2X/how-to/plexos-to-sienna/) [![License](https://img.shields.io/pypi/l/r2x-plexos-to-sienna.svg)](../../LICENSE.txt)

<br clear="left">

`r2x-plexos-to-sienna` applies component mapping rules and attaches time series to a parsed
PLEXOS system. The public `plexos_to_sienna(system, config)` function returns
a target system; the Sienna exporter writes native output files. Parsing,
translation, and export are separate steps.

## Install

In an activated Python environment supported by this package:

```bash
python -m pip install r2x-plexos-to-sienna
python -m pip check
```

For a CLI-managed environment, use `r2x install r2x-plexos-to-sienna` instead. See
[installation](https://natlabrockies.github.io/R2X/getting-started/installation/)
for runtime selection and plugin discovery.

## Verify the configuration

This example runs without model input files. It checks the public configuration
and the packaged mapping rules before you prepare a full translation:

```pycon
>>> import json
>>> from importlib.resources import files
>>> from r2x_plexos_to_sienna.plugin_config import PlexosToSiennaConfig
>>> config = PlexosToSiennaConfig()
>>> assert config.technology_mapping == {}
>>> assert "r2x_plexos.models" in config.models
>>> rules = json.loads(files("r2x_plexos_to_sienna.config").joinpath("rules.json").read_text())
>>> assert isinstance(rules, list) and len(rules) > 0
```

Continue with the [complete PLEXOS → Sienna workflow](https://natlabrockies.github.io/R2X/how-to/plexos-to-sienna/)
for input requirements, parsing, translation, and export. A translation requires
real source components and their companion time-series files; configuration
validation alone does not validate a model.

<span id=""></span>
<span id="----fmtgreentimeyyyy-mm-dd-hhmmssgreen-levelextrashort_level4level-message"></span>
<span id="----leveldebug"></span>
<span id="----log_filedebuglog"></span>
<span id="advanced-logging"></span>
<span id="basic-translation"></span>
<span id="configuration"></span>
<span id="create-translator-instance"></span>
<span id="define-input-file"></span>
<span id="output"></span>
<span id="r2x-plexos-to-sienna-translator"></span>
<span id="run-the-translation"></span>
<span id="setup_logging"></span>
<span id="step-to-extract-desired-model-name-important-to-locate-time-series-otherwise-sets-a-default"></span>
<span id="usage"></span>

## Mapping and API

- [Function and configuration reference](https://natlabrockies.github.io/R2X/reference/python-api/#plexos_to_sienna)
- [Property mappings](https://natlabrockies.github.io/R2X/reference/plexos-to-sienna-properties/)
- [Translation source](src/r2x_plexos_to_sienna/translation.py) and [packaged rules](src/r2x_plexos_to_sienna/config/rules.json)
- [Troubleshooting](https://natlabrockies.github.io/R2X/troubleshooting/)
