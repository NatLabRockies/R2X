---
title: ReEDS translation reference for Sienna and PLEXOS
description: Compare component mappings, time series, and modeling assumptions across the ReEDS translators.
---

This reference provides a side-by-side view of how R2X translates ReEDS concepts and technologies into Sienna and PLEXOS.
It summarizes their physical roles, target component types, timeseries treatment and important modeling assumptions and limitations.

## System structure and demand

| ReEDS model element | Model role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| Model zone (`ReEDSRegion`) | Electrical region | `Area` and `ACBus` | `PLEXOSRegion` and `PLEXOSNode` |
| Electricity demand (`ReEDSDemand`) | Inflexible electricity demand | `PowerLoad` | Load timeseries on `PLEXOSRegion` |
| Transmission region (`transreg`) | Aggregation of ReEDS model zones | No separate component; used for reserve grouping | `PLEXOSZone` |

## Electricity-consuming technologies

| ReEDS technology or demand type | Model role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| `electrolyzer` | Electricity consumption for hydrogen production | `StandardLoad` | `PLEXOSPurchaser` |
| `smr` | Electricity consumption associated with steam methane reforming | `StandardLoad` | `PLEXOSPurchaser` |
| `smr_ccs` | Electricity consumption associated with steam methane reforming with carbon capture | `StandardLoad` | `PLEXOSPurchaser` |
| Optimally sited data-center load (`data-center`) | Electricity demand | `StandardLoad` | `PLEXOSPurchaser` |
| Other technology in the `CONSUME` subset (`ReEDSConsumingTechnology`) | Technology-specific electricity consumption | `StandardLoad` | `PLEXOSGenerator` |

## Thermal and hydrogen generation

| ReEDS technology or technology subset | Model role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| Conventional thermal generation | Dispatchable electricity generation | `ThermalStandard` | `PLEXOSGenerator` |
| `h2-cc` family, such as `gas-cc_h2-cc` | Hydrogen-fueled combined-cycle electricity generation | `ThermalStandard` | `PLEXOSGenerator` |
| `h2-ct` family, such as `gas-ct_h2-ct` | Hydrogen-fueled combustion-turbine electricity generation | `ThermalStandard` | `PLEXOSGenerator` |
| `nuclear-smr` | Small modular nuclear electricity generation | `ThermalStandard` | `PLEXOSGenerator` |

## Variable and distributed generation

| ReEDS technology or technology subset | Model role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| Utility-scale PV in the `UPV` subset | Curtailable variable generation | `RenewableDispatch` | `PLEXOSGenerator` |
| Onshore wind in the `ONSWIND` subset | Curtailable variable generation | `RenewableDispatch` | `PLEXOSGenerator` |
| Offshore wind in the `OFSWIND` subset | Curtailable variable generation | `RenewableDispatch` | `PLEXOSGenerator` |
| Distributed PV in the `distpv` subset | Nondispatchable distributed generation | `RenewableNonDispatch` | `PLEXOSGenerator` with an availability profile |

## Conventional hydro

| ReEDS technology subset | Model role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| Dispatchable conventional hydro in `HYDRO_D` | Dispatchable generation with a water-energy budget | `HydroDispatch` | `PLEXOSGenerator` with energy and hourly power limits |
| Nondispatchable conventional hydro in `HYDRO_ND` | Fixed hydro generation derived from water availability | `RenewableNonDispatch` | `PLEXOSGenerator` with `Fixed Load` |

The ReEDS technology subset membership is the authoritative distinction between dispatchable and nondispatchable conventional hydro.
Technology-name prefixes alone are not sufficient for classification.

Dispatchable hydro retains an hourly generation decision.
Its power limit is derived from installed capacity and the applicable hydro capacity adjustment.
Its energy budget is derived from installed capacity, hydro capacity factor and the duration of the budget interval.

Nondispatchable hydro does not receive a flexible energy budget.
Its hourly output is installed capacity multiplied by the applicable hydro capacity factor.

The target budget interval is separate from the simulation timestep.
An hourly simulation can enforce a daily, weekly or monthly energy budget.

:::note
Nondispatchable hydro could be serialized as a [PowerSystems.jl](https://sienna-platform.github.io/PowerSystems.jl/stable/) hydro component.
However [PowerSimulations.jl](https://sienna-platform.github.io/PowerSimulations.jl/stable/) assigns one `DeviceModel` formulation to each component type in a simulation template.
If both hydro categories used `HydroDispatch`, a single simulation template could not assign `HydroDispatchRunOfRiverBudget` to dispatchable hydro and `FixedOutput` to nondispatchable hydro at the same time.
The translator therefore uses `HydroDispatch` for dispatchable hydro and `RenewableNonDispatch` for nondispatchable hydro.
:::

:::note
`HydroDispatch` can represent the ReEDS generation VOM as a hydro generation cost.
`RenewableNonDispatch` does not provide the same operating-cost representation.
The translator preserves the original nondispatchable hydro VOM as `ext["reeds_vom_cost"]`.
:::

## Pumped hydro

| ReEDS technology | Model role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| `pumped-hydro` technology in the `PSH` subset | Storage with pumping and turbine generation | `HydroPumpTurbine` with linked head and tail `HydroReservoir` components | `PLEXOSGenerator` with linked head and tail `PLEXOSStorage` objects |

ReEDS classifies pumped hydro through its storage framework rather than the conventional-hydro framework.
The target representation preserves pumping, turbine generation, stored energy and the relationship between the head and tail reservoirs.

The Sienna translator uses explicit ReEDS `energy_capacity` in MWh when available,
falling back to `capacity × storage_duration`. The PLEXOS translator calculates
reservoir `Max Volume` as `capacity × storage_duration / 1000` in GWh and does not
use explicit `energy_capacity`. For example, 100 MW with a four-hour duration and
an explicit 600 MWh capacity produces 600 MWh in Sienna and 0.4 GWh (400 MWh) in PLEXOS.
The ReEDS storage efficiency is applied during pumping while turbine efficiency remains one.

Initial head and tail levels use translator assumptions because ReEDS does not provide a fixed initial state.

:::note
PLEXOS can apply ReEDS VOM to turbine generation.
[HydroPowerSimulations.jl](https://sienna-platform.github.io/HydroPowerSimulations.jl/stable/) uses the `HydroPumpTurbine` operation cost for both generation and pumping, while ReEDS applies this VOM only to generation.
The Sienna translator therefore sets the pumped-hydro operation cost to zero to avoid applying a generation-only cost during pumping.
It preserves the original value as `ext["reeds_vom_cost"]`.
:::

:::note
ReEDS does not provide external water inflow for this pumped-hydro representation.
Sienna therefore requires explicit zero inflow profiles on both reservoirs to satisfy the HydroPowerSimulations formulation.
:::

## Storage

| ReEDS technology or technology subset | Model role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| Battery technologies in the `BATTERY` subset | Electrochemical storage | `EnergyReservoirStorage` | `PLEXOSBattery` |
| Other non-pumped technologies in the `STORAGE` subset | Generic energy storage | `EnergyReservoirStorage` | No generic target rule |

## Transmission and interfaces

| ReEDS transmission capacity type or interface | Model role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| `AC` transmission capacity type | Directional AC transfer capability | `MonitoredLine` | `PLEXOSLine` |
| `VSC` transmission capacity type | Directional HVDC transfer capability | `TwoTerminalGenericHVDCLine` | `PLEXOSLine` |
| `LCC` transmission capacity type | Directional HVDC transfer capability | `TwoTerminalGenericHVDCLine` | `PLEXOSLine` |
| `B2B` transmission capacity type | Directional back-to-back transfer capability | `TwoTerminalGenericHVDCLine` | `PLEXOSLine` |
| Interzonal interface (`ReEDSInterface`) | Aggregate transfer interface | `AreaInterchange` | `PLEXOSInterface` |

## Reserves

| ReEDS operating reserve concept | Sienna representation | PLEXOS representation |
|---|---|---|
| Spinning, regulation and flexibility reserve products | `VariableReserve` | `PLEXOSReserve` |
| `NON_SPINNING` reserve product | `VariableReserveNonSpinning` | `PLEXOSReserve` |
| Reserve direction | Reserve direction | Encoded in the reserve `Type` property |
| Translated reserve eligibility | Service membership | Reserve membership |
| Hourly requirement | Requirement timeseries | `Min Provision` timeseries |


## Related references and implementation

For pipeline setup and component diagrams, see [ReEDS to Sienna](/R2X/how-to/reeds-to-sienna/)
and [ReEDS to PLEXOS](/R2X/how-to/reeds-to-plexos/). For individual properties, see
the [Sienna mappings](/R2X/reference/reeds-to-sienna-properties/) and
[PLEXOS mappings](/R2X/reference/reeds-to-plexos-properties/).

The following implementation links refer to the verified code at commit
`39be9d19a1833b3e736e9039b29292a4e6819778`:

- [Sienna component-selection rules](https://github.com/NatLabRockies/R2X/blob/39be9d19a1833b3e736e9039b29292a4e6819778/packages/r2x-reeds-to-sienna/src/r2x_reeds_to_sienna/config/rules.json).
- [Sienna property getters, including storage capacity and hydro costs](https://github.com/NatLabRockies/R2X/blob/39be9d19a1833b3e736e9039b29292a4e6819778/packages/r2x-reeds-to-sienna/src/r2x_reeds_to_sienna/getters.py).
- [Sienna time-series post-processing, including pumped-hydro inflow](https://github.com/NatLabRockies/R2X/blob/39be9d19a1833b3e736e9039b29292a4e6819778/packages/r2x-reeds-to-sienna/src/r2x_reeds_to_sienna/getter_utils.py).
- [PLEXOS component-selection and property rules](https://github.com/NatLabRockies/R2X/blob/39be9d19a1833b3e736e9039b29292a4e6819778/packages/r2x-reeds-to-plexos/src/r2x_reeds_to_plexos/config/rules.json).
- [PLEXOS property getters, including reservoir maximum volume](https://github.com/NatLabRockies/R2X/blob/39be9d19a1833b3e736e9039b29292a4e6819778/packages/r2x-reeds-to-plexos/src/r2x_reeds_to_plexos/getters.py).
- [PLEXOS time-series handling, including hydro budgets](https://github.com/NatLabRockies/R2X/blob/39be9d19a1833b3e736e9039b29292a4e6819778/packages/r2x-reeds-to-plexos/src/r2x_reeds_to_plexos/getters_utils.py).
