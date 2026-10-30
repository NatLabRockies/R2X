# r2x-sienna-to-plexos

Translate Sienna systems into PLEXOS models.

<span id="overview"></span>
<span id="usage"></span>
<span id="basic-example"></span>
<span id="parameters"></span>

See the [package README](../README.md) for installation and executable configuration
checks, and the [central Sienna to PLEXOS workflow](https://natlabrockies.github.io/R2X/how-to/sienna-to-plexos/)
for parsing, translation, and export. The public translation function is
[`sienna_to_plexos`](r2x_sienna_to_plexos/translation.py); it accepts a parsed system
and `SiennaToPlexosConfig`. Mapping rules are packaged in
[`config/rules.json`](r2x_sienna_to_plexos/config/rules.json).
