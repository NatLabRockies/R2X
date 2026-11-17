# r2x-reeds-to-plexos

Translate ReEDS systems into PLEXOS models.

## Overview

This package provides a translation plugin to convert ReEDS run outputs into PLEXOS XML format. The translation applies mapping rules and getters to transform ReEDS components (generators, transmission lines, regions, etc.) into their PLEXOS equivalents.

## Usage

### Basic Example

```python
from r2x_reeds_to_plexos.translation import ReedsToPlexosTranslation

from r2x_core.logger import setup_logging

# Define level of printing to show progress
setup_logging(level="DEBUG")

# Initialize the translation
translation = ReedsToPlexosTranslation(
    run_path="/path/to/reeds/run",
    output_folder="/path/to/output",
    case_name="my_case",
    solve_year=2030,
    weather_year=2012
)

# Run the translation
translation.run()

# Run with upgrader (if needed to upgrade ReEDS data format)
translation.run(run_upgrader=True)
```

### Parameters

- **`run_path`** (str): Path to the ReEDS run folder containing the input data.
- **`output_folder`** (str): Path to the directory where output files will be saved.
- **`case_name`** (str): Name of the case (used for output file naming).
- **`solve_year`** (int, optional): The solve year for the ReEDS data. Default is `2030`.
- **`weather_year`** (int, optional): The weather year for time series data. Default is `2012`.
- **`missing_ramp_rate_fraction_per_minute`** (float or None, optional): Ramp rate in fraction of capacity per minute to be applied to generators with missing ramp rates. `None` causes the translation to fail explicitly on any missing ramp rates. Default is `1`.

## Translation Rules

Translation rules are defined in `config/rules.json`. These rules specify how ReEDS components are mapped to PLEXOS components, including field mappings, getters, and filters.

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

## Ramp Rates

Thermal and hydro ReEDS generator `ramp_rate` values are fractions of installed
generator capacity per minute. Parsed inputs and PCM defaults must preserve this
fraction through generator splitting. Translation multiplies by the final
generator capacity exactly once to obtain PLEXOS Max Ramp Up and Max Ramp Down
in MW/min; no division by 60 is needed.

For example, a `0.05` fraction/min rate produces 16 MW/min on a 320 MW unit and
3 MW/min on a 60 MW remainder. Each translated generator has `Units = 1`.

### Resolution and precedence

For each ramp direction, translation uses the first available value:

1. A populated source `ramp_rate`, multiplied by final generator capacity.
   It supplies both directions, and an explicit zero is retained.
2. A positive directional translator default, `ramp_rate_up` or `ramp_rate_down`.
   These are absolute MW/min values and are not capacity-scaled.
3. A positive `max_ramp_up_percentage` translator default, multiplied by final
   capacity. Despite its name, this is a fraction/min (e.g., `0.05`, not `5`).
   The same key serves both directions.
4. `missing_ramp_rate_fraction_per_minute`, multiplied by final capacity.
   This configured fallback is used only when the source rate and usable
   translator defaults are unavailable.
5. If the configured fallback is `None` (YAML `null`), fail translation instead.

Absolute up/down defaults can differ, and only one direction may need the
configured fallback. Zero directional/fractional translator defaults do not
provide a usable default; this differs from an explicit source zero or an
explicitly configured zero fallback.

The upstream ReEDS parser resolves explicit upgrade destinations and
dispatchable-hydro inheritance before translation. An unresolved source rate
remains `None`, but an earlier `add-pcm-defaults` step may populate it. A value
populated by that step is treated as the source field here; the configured
translator fallback does not override it. Review PCM override settings when
tracing the origin of a rate.

### Configure missing-rate behavior

| Parameter | Default | Meaning |
| --- | --- | --- |
| `missing_ramp_rate_fraction_per_minute` | `1.0` | Fraction of final capacity per minute used when source/default rates are unavailable |
| Set the parameter to `null` | No fallback | Fail on an applicable generator with an unresolved ramp direction |

For example, configure a fallback of `0.2` fraction/min:

```yaml
config:
    r2x-reeds-to-plexos.reeds-to-plexos:
        missing_ramp_rate_fraction_per_minute: 0.2
```

Alternatively, require usable source or translator-default rates:

```yaml
config:
    r2x-reeds-to-plexos.reeds-to-plexos:
        missing_ramp_rate_fraction_per_minute: null
```

Python configuration uses `ReedsToPlexosConfig` with the same parameter; use
`None` for strict mode. The parameter accepts finite nonnegative numbers,
including zero and values greater than one. Booleans (`false`/`False` included),
negative values, NaN, and infinity are rejected.

The default `1.0` means 100% of installed capacity per minute: 320 MW/min for
a 320 MW generator. It is not an unlimited-ramp flag or a calibrated
technology-specific rate. Zero explicitly produces a zero fallback ramp limit.
Existing workflows that previously received zero for an unresolved rate now
receive the configured fallback.

### Scope, preflight, and diagnostics

Missing-rate handling follows source translation rules that use the ramp getters,
not a thermal/hydro-only class list. The current rules apply it to thermal,
hydro, and generic generators in the `reeds-generator`, `imports`, and `exports`
categories. Variable/storage rules without ramp getters are excluded from this
policy, not from translation.

Before target construction, preflight selects generators using rule source types
and filters, resolves both ramp directions once per generator, and caches the
results in the translation context. Ramp getters read those results to populate
PLEXOS Max Ramp Up and Max Ramp Down. Source generator objects are not modified.

With translation logging enabled, configured fallback use produces one warning
per affected generator, identifying its name, technology, capacity, affected
directions, configured fraction/min, and resulting MW/min limits. Strict mode
logs and raises an aggregated error for unresolved generators before constructing
the target system. A successful strict check means usable source/default rates
exist; it does not require every rate to come directly from ReEDS.

ReEDS uses its ramp parameter for operating-reserve capability, whereas these
PLEXOS properties constrain dispatch ramps. Preserving the rate's units does not
make those modeling uses equivalent.

Previously saved ReEDS systems containing capacity-scaled PCM ramp values must
be rebuilt from inputs with the corrected r2x-reeds implementation; the
translator does not guess whether an incoming number is fractional or absolute.

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
