# r2x-resolve-to-plexos

Translate `r2x-resolve` systems into PLEXOS component models.

## Public API

```python
from r2x_resolve_to_plexos import ResolveToPlexosConfig, resolve_to_plexos

plexos_system = resolve_to_plexos(resolve_system, ResolveToPlexosConfig())
```

## Mapping

Declarative mappings live in the packaged `config/translation_rules.json`;
`attach.py` handles the steps the one-to-one rules cannot express.

| Resolve | PLEXOS |
| --- | --- |
| `ResolveZone` | `PLEXOSNode` and `PLEXOSRegion` of the same name, joined by a Node.Region membership. Zones with `ext["external"]` (e.g. `PJM_W`, `IESO`) get category `external-zone`, the rest `resolve-zone`. |
| `ResolveLoad` | The zone Region's `load` (peak MW) plus the hourly `demand` series, which is net of distributed PV. |
| Every `InvestmentComponent` (`ResolveGenerator`, `ResolveBatteryStorage`, `ResolvePumpedStorage`) | `PLEXOSGenerator` with `max_capacity` from `capacity`, a category naming its type (below), `units` 0 when capacity is 0, and a Generator.Nodes membership to its zone. Battery and pumped storage are generators for now; Resolve has no energy capacity for them. Wind and solar `max_active_power` profiles carry over (exported as Rating). |
| `ResolveFuelPrice` | `PLEXOSFuel` with the annual `price`, category from `fuel_type` (`NATURAL_GAS`, `FUEL_OIL`, `RNG`, ...), and the monthly `fuel_price` series at its own dates (exported as Price; requires an r2x-plexos exporter that writes non-sequential series). |
| `ResolveTransmissionLine` | `PLEXOSLine` with Max Flow = `from_to` and Min Flow = -`to_from`, plus NodeFrom and NodeTo memberships. |
| `ResolveGroupedInterface` | `PLEXOSInterface` with Max Flow = forward limit and Min Flow = -reverse limit (a missing limit is unlimited), plus Interface.Lines memberships. Lines against the interface direction (`ext["line_directions"]` -1) get a Flow Coefficient of -1 on their membership; +1 is the PLEXOS default (requires an r2x-plexos exporter that writes membership properties). |
| `ResolveReserve` | `PLEXOSReserve` with Type 1 (raise) for Up reserves and 2 (lower) for Down, Min Provision from the hourly `requirement` series, and category `resolve-reserve`. Only types 1 and 2 are used, so no capacity counts toward two reserve types. Every Generator (including battery and pumped storage) can provide every reserve through Reserve.Generators memberships. |

Generator categories:

| Resolve units | Category |
| --- | --- |
| `Gas & FO` units split by existing type, by fuel and prime mover | `Gas CC`, `Gas ST`, `Gas CT`, `Oil ST`, `Oil CT` |
| `Gas & FO` new builds and unsplit units (mixed fuel) | `Gas & FO` |
| `In-State Hydro` | `Hydro` |
| `Hydro Imports (Existing)`, `Hydro Imports (New)` | `Hydro Imports` |
| Every other technology | Its Resolve label (`Nuclear`, `Zero-Carbon Firm`, `Wind Imports`, `Offshore Wind`, `Battery Storage`, ...) |

r2x-plexos chooses default properties by category: `Hydro` falls in its hydro-dispatch group (ramp
limits rather than thermal start and up/down-time properties); every other category is treated as
thermal.

Generator.Fuels memberships come from r2x-resolve: each `ResolveGeneratorFuel` becomes one
membership, so a generator that can burn several fuels (new `Gas & FO`: zone gas, distillate, and
residual oil; `Zero-Carbon Firm`: `RNG_Tier_1` and `RNG_Tier_2`) lists each and PLEXOS chooses
among them.

The per-pair `ResolveInterface` has no PLEXOS counterpart; its line carries the limits.

## Validation

Before returning, the transform checks that every Resolve zone produced one Node
and one Region, and every generator, fuel, line, and grouped interface one PLEXOS
component. A mismatch raises a `ValueError` naming the category and counts.
