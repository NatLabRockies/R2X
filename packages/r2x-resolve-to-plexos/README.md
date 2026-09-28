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
| Every `InvestmentComponent` | `PLEXOSGenerator` with `max_capacity` from `capacity`, category from the technology label, `units` 0 when capacity is 0, and a Generator.Nodes membership to its zone. Battery and pumped storage are generators for now; Resolve has no energy capacity for them. Wind and solar `max_active_power` profiles carry over (exported as Rating). |
| `ResolveFuel` | `PLEXOSFuel` with the annual `price` and category from `fuel_type`. |
| `ResolveTransmissionLine` | `PLEXOSLine` with Max Flow = `from_to` and Min Flow = -`to_from`, plus NodeFrom and NodeTo memberships. |
| `ResolveGroupedInterface` | `PLEXOSInterface` with Max Flow = forward limit and Min Flow = -reverse limit (a missing limit is unlimited), plus Interface.Lines memberships. Line directions stay in `ext["line_directions"]`. |

Generator.Fuels memberships:

| Resolve units | Fuel |
| --- | --- |
| `Gas & FO` gas units and new builds | Natural gas priced for the zone (`NG_NYISO_J`, `NG_NYISO_A-E`, ...) |
| `Gas & FO` oil units (`resource_type` `FO_ST`, `FO_CT`) | Residual fuel oil priced for the zone (`RFO_NYISO_J`, ...) |
| `Zero-Carbon Firm` | `RNG_Tier_1` |
| `Nuclear` | `Nuclear` |
| `Biomass` | `Biomass` |

The per-pair `ResolveInterface` has no PLEXOS counterpart; its line carries the limits.

## Not yet translated

- Monthly fuel price series: the PLEXOS exporter does not link Fuel time series.
- Interface line directions: the exporter cannot write the Interface.Lines Flow
  Coefficient, so directions stay in `ext`.

## Validation

Before returning, the transform checks that every Resolve zone produced one Node
and one Region, and every generator, fuel, line, and grouped interface one PLEXOS
component. A mismatch raises a `ValueError` naming the category and counts.
