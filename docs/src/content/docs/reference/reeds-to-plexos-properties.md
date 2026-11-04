---
title: ReEDS to PLEXOS Property Mappings
---

See the [ReEDS translation comparison](/R2X/reference/reeds-translation-reference/)
for side-by-side component mappings, time-series treatment, and modeling limitations.

This page documents property-level mappings for `r2x-reeds-to-plexos`. The
class-level flow is shown in [ReEDS to PLEXOS](/R2X/how-to/reeds-to-plexos/). The
[authoritative rules](https://github.com/NatLabRockies/R2X/blob/main/packages/r2x-reeds-to-plexos/src/r2x_reeds_to_plexos/config/rules.json)
contain the complete field maps, getters, defaults, and filters.

## Component conversion

These diagrams summarize selected rule families, not a one-to-one copy of every
field. Blue source nodes feed either a conversion step or an explicitly filtered
branch; dark nodes show the target classes and representative properties.
The tables below retain the full property reference.

### Generation and flexible demand

Thermal, variable and hydro generators converge on `PLEXOSGenerator`. Their
identity and capacity fields are mapped, while technology-specific getters
compute operating properties. Consuming technologies use that generator route
only when their technology is not `electrolyzer`, `data-center`, `smr` or `smr_ccs`.
Electrolyzer, steam-methane-reforming and data-center demand classes instead
become purchasers.

```mermaid
flowchart LR
  accTitle: ReEDS generation and demand conversion
  accDescr: Thermal, variable and hydro generator families use field maps and operating getters to create PLEXOSGenerator. Three flexible demand classes create PLEXOSPurchaser. Separate rule filters apply to consuming technologies.
  G["ReEDSThermalGenerator<br/>ReEDSVariableGenerator<br/>ReEDSHydroGenerator"] --> C["Map identity + capacity<br/>Compute operating properties" ]
  C --> P["PLEXOSGenerator<br/>max_capacity, commitment<br/>costs + technology-specific limits"]
  D["ReEDSElectrolyzerDemand<br/>ReEDSSteamMethaneReformingDemand<br/>ReEDSDataCenterDemand"] --> U["Map demand fields<br/>Compute units"]
  U --> Q["PLEXOSPurchaser<br/>max_load + units"]
  class G,D source
  class C,U process
  class P,Q target
  classDef source fill:#d9effa,stroke:#0079c2,color:#003a69,stroke-width:2px
  classDef process fill:#f4f7f9,stroke:#7890a0,color:#293d4d
  classDef target fill:#003a69,stroke:#0079c2,color:#ffffff,stroke-width:2px
```

### Storage selection

`ReEDSStorage` follows the battery branch only when its technology starts with
`battery` (case-insensitive); `pumped-hydro` follows the generator branch.
The reservoir rules are separate: they read `ReEDSGenerator` with technology
`pumped-hydro` and create the upper and lower `PLEXOSStorage` objects. Do not
interpret the storage branches as an unconditional conversion to both targets.

```mermaid
flowchart LR
  accTitle: ReEDS storage and pumped hydro selection
  accDescr: ReEDSStorage with battery technology creates PLEXOSBattery; pumped-hydro technology creates PLEXOSGenerator. Separate ReEDSGenerator pumped-hydro rules create upper and lower PLEXOSStorage reservoirs.
  B["ReEDSStorage"] --> F{"Technology filter"}
  F -->|"starts with battery"| T["PLEXOSBattery<br/>max_power + capacity<br/>efficiency + SOC limits"]
  F -->|"pumped-hydro"| G["PLEXOSGenerator<br/>pump efficiency + load"]
  H["ReEDSGenerator"] --> K["technology = pumped-hydro"]
  K --> R["PLEXOSStorage<br/>upper + lower reservoirs<br/>volume + natural inflow"]
  class B,H source
  class F,K process
  class T,G,R target
  classDef source fill:#d9effa,stroke:#0079c2,color:#003a69,stroke-width:2px
  classDef process fill:#f4f7f9,stroke:#7890a0,color:#293d4d
  classDef target fill:#003a69,stroke:#0079c2,color:#ffffff,stroke-width:2px
```

## Generator and Demand Properties

| Source class | Target class | Direct fields | Computed properties |
| --- | --- | --- | --- |
| `ReEDSThermalGenerator` | `PLEXOSGenerator` | `name`, `uuid`, `category`, `max_capacity`, `fom_charge`, `vom_charge`, `fuel_price`, `heat_rate`, `ext` | `commitment`, outage/maintenance rates, `ramp_limits`, `minimum_levels`, `start_cost`, `units` |
| `ReEDSVariableGenerator` | `PLEXOSGenerator` | `name`, `uuid`, `category`, `max_capacity`, `fom_charge`, `vom_charge`, `ext` | `commitment`, outage/maintenance rates, `rating`, `load_subtracter`, `start_cost`, `units` |
| `ReEDSHydroGenerator` | `PLEXOSGenerator` | `name`, `uuid`, `category`, `max_capacity`, `fom_charge`, `vom_charge`, `ext` | `commitment`, `energy/day`, outage/maintenance rates, `ramps`, `minimum_levels`, `start_cost`, `units` |
| `ReEDSConsumingTechnology` | `PLEXOSGenerator` | `name`, `uuid`, `category`, `max_capacity`, `fom_charge`, `vom_charge`, `fuel_price`, `heat_rate`, `ext` | `commitment`, outage/maintenance rates, `ramps`, `minimum_levels`, `start_cost`, `units` |
| `ReEDSElectrolyzerDemand` | `PLEXOSPurchaser` | `name`, `category`, `max_load`, `ext` | `units` |
| `ReEDSSteamMethaneReformingDemand` | `PLEXOSPurchaser` | `name`, `category`, `max_load`, `ext` | `units` |
| `ReEDSDataCenterDemand` | `PLEXOSPurchaser` | `name`, `category`, `max_load`, `ext` | `units` |

All generator families use `PLEXOSGenerator`; the source technology category is
preserved so PLEXOS can distinguish the exported technology where its model
allows it. Purchaser profiles are attached separately by the time-series
helpers.

## Storage and Hydro Properties

| Source class | Target class | Direct fields | Computed properties |
| --- | --- | --- | --- |
| `ReEDSStorage` | `PLEXOSBattery` | `name`, `category`, `max_power`, `ext` | build/capital cost, `capacity`, charge/discharge efficiency, `duration`, `SOC` limits, outage/maintenance rates, `units`, variable cost |
| `ReEDSStorage` | `PLEXOSGenerator` | `name`, `category`, `max_capacity`, `ext` | `commitment`, outage/maintenance rates, `minimum_level`, pump efficiency/load, `units`, variable cost |
| `ReEDSGenerator` | `PLEXOSGenerator` | `name`, `uuid`, `category`, `max_capacity`, `ext`, `fuel_price`, `heat_rate`, `vom_charge` | `commitment`, outage/maintenance rates, `ramps`, `minimum_levels`, pump efficiency/load, `start_cost`, `units` |
| `ReEDSGenerator` | `PLEXOSStorage` | `name`, `category`, `ext` | `initial_volume`, `maximum_volume`, `natural_inflow`, `units` |

## Topology and Other Components

| Source class | Target class | Property highlights |
| --- | --- | --- |
| `ReEDSRegion` | `PLEXOSRegion` | `name`/`category`/`ext`, `load`, `units` |
| `ReEDSRegion` | `PLEXOSZone` | `name`/`category`, `units` |
| `ReEDSRegion` | `PLEXOSNode` | `name`/`category`/`ext`, `load_participation_factor`, `units` |
| `ReEDSTransmissionLine` | `PLEXOSLine` | `name`/`category`, `min`/`max_flow`, `losses`, `wheeling_charges`, `units` |
| `ReEDSReserve` | `PLEXOSReserve` | `name`/`category`, `duration`, `minimum_provision`, `timeframe`, `type`, `VORS`, `ext` |
| `ReEDSInterface` | `PLEXOSInterface` | `name`, `min`/`max_flow`, `units`, `ext` |

Membership rules then connect the generated PLEXOS objects to the target
network topology. The property rules select the applicable output with filters
for hydro/storage variants and other technology-specific cases.

## Fuel objects (opt-in)

When `ReedsToPlexosConfig(use_fuel_objects=True)` is set, fuel data is moved off
the generators onto shared `PLEXOSFuel` objects after the rules above run. The
option is disabled by default, and the generator-level `fuel_price` mapping in
the tables above applies unchanged.

```mermaid
flowchart LR
  accTitle: ReEDS fuel data to PLEXOS Fuel objects
  accDescr: Thermal and generic ReEDS generators with a fuel type are grouped by fuel type, price, and fuel price time series. Each group creates a PLEXOSFuel with Price, and each generator is linked to its Fuel through a Generator.Fuels membership. Heat rate stays on the generator.
  G["ReEDSThermalGenerator<br/>ReEDSGenerator<br/>with fuel_type"] --> K{"Group by<br/>fuel_type + fuel_price<br/>+ fuel_price time series"}
  K --> F["PLEXOSFuel<br/>category = fuel_type<br/>Price + price time series"]
  K --> P["PLEXOSGenerator<br/>heat_rate kept<br/>fuel_price cleared"]
  P -->|"Generator.Fuels"| F
  class G source
  class K process
  class F,P target
  classDef source fill:#d9effa,stroke:#0079c2,color:#003a69,stroke-width:2px
  classDef process fill:#f4f7f9,stroke:#7890a0,color:#293d4d
  classDef target fill:#003a69,stroke:#0079c2,color:#ffffff,stroke-width:2px
```

### Applicable generators

Only source classes whose rules map `fuel_price` onto `PLEXOSGenerator` and that
carry a `fuel_type` are linked:

| Source class | Linked to a Fuel |
| --- | --- |
| `ReEDSThermalGenerator` | Yes |
| `ReEDSGenerator` (generic, imports, exports) | Only when `fuel_type` is set |
| `ReEDSConsumingTechnology` | No; keeps generator-level `fuel_price` |
| Variable, hydro, and storage generators | No; they have no fuel price mapping |

### Property routing

Each fuel-related property is written where PLEXOS defines it:

| ReEDS source | PLEXOS scope | PLEXOS property | Disabled (default) |
| --- | --- | --- | --- |
| `fuel_price` (scalar) | Fuel object | `Fuel.Price` | `Generator.Fuel Price` |
| `fuel_price` time series | Fuel object | `Fuel.Price` (data file) | Not copied for thermal generators |
| `fuel_type` | Fuel object | Fuel `category` | Not used |
| `heat_rate` | Generator | `Generator.Heat Rate` | `Generator.Heat Rate` |
| Generator to fuel link | Membership | `Generator.Fuels` | No membership |

No `Generator.Fuels` membership properties are written. Those properties (for
example `Ratio`, `Max Ratio`, or a per-fuel `Heat Rate`) only matter for
multi-fuel generators, and each ReEDS generator has one fuel.

### Fuel identity and naming

Two generators share a Fuel only when all of these match:

- `fuel_type`
- scalar `fuel_price` (missing prices are treated as `0`)
- every `fuel_price` time series, compared by type, features, timestamps,
  resolution, and values

Generators in different regions share a Fuel when their data is identical, and
fuels whose regional or time-varying data differs are never merged.

Names are deterministic and do not depend on component order:

| Case | Fuel name | Example |
| --- | --- | --- |
| One variant for the fuel type | `<fuel_type>` | `naturalgas` |
| Several variants for the fuel type | `<fuel_type>_<first region>`, using the alphabetically first region that uses the variant | `naturalgas_p1`, `naturalgas_p2` |
| Two variants share the same first region | A numeric suffix is appended in sorted order | `naturalgas_p1_2` |
