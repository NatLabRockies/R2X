# ReEDS translation reference

This page describes how ReEDS concepts and technologies map to Sienna and PLEXOS through the R2X translation packages.
It focuses on physical role, component type, timeseries behavior and known limitations.

## System structure and demand

| ReEDS concept | ReEDS role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| `ReEDSRegion` | Electrical region | `Area` and `ACBus` | `PLEXOSRegion`, `PLEXOSZone` and `PLEXOSNode` |
| `ReEDSDemand` | Inflexible electricity demand | `PowerLoad` | Regional load with node membership |
| Transmission region | Aggregation of ReEDS regions | `Area` metadata and associations | `PLEXOSZone` |

## Electricity-consuming technologies

| ReEDS identifier or family | ReEDS role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| `electrolyzer` | Electricity consumption for hydrogen production | `InterruptiblePowerLoad` | `PLEXOSPurchaser` |
| `smr` | Electricity consumption associated with steam methane reforming | `InterruptiblePowerLoad` | `PLEXOSPurchaser` |
| `smr_ccs` | Electricity consumption associated with steam methane reforming with carbon capture | `InterruptiblePowerLoad` | `PLEXOSPurchaser` |
| Data center | Electricity demand | `PowerLoad` | `PLEXOSPurchaser` |
| Other `ReEDSConsumingTechnology` | Technology-specific electricity consumption | Generic consuming load | `PLEXOSPurchaser` |

## Thermal and hydrogen generation

| ReEDS identifier or family | ReEDS role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| Conventional thermal generation | Dispatchable electricity generation | `ThermalStandard` | `PLEXOSGenerator` |
| `h2-cc` | Hydrogen-fueled combined-cycle electricity generation | `ThermalStandard` | `PLEXOSGenerator` |
| `nuclear-smr` | Small modular nuclear electricity generation | `ThermalStandard` | `PLEXOSGenerator` |

## Variable and distributed generation

| ReEDS identifier or family | ReEDS role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| Utility-scale PV | Curtailable variable generation | `RenewableDispatch` | `PLEXOSGenerator` |
| Onshore wind | Curtailable variable generation | `RenewableDispatch` | `PLEXOSGenerator` |
| Offshore wind | Curtailable variable generation | `RenewableDispatch` | `PLEXOSGenerator` |
| Distributed PV | Nondispatchable distributed generation | `RenewableNonDispatch` | `PLEXOSGenerator` with an availability profile |

## Conventional hydro

| ReEDS category | ReEDS role | Sienna representation | PLEXOS representation |
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
It should not receive operating-reserve memberships.

The target budget interval is separate from the simulation timestep.
An hourly simulation can enforce a daily, weekly or monthly energy budget.

:::{note}
Nondispatchable hydro could be serialized as a [PowerSystems.jl](https://sienna-platform.github.io/PowerSystems.jl/stable/) hydro component.
However [PowerSimulations.jl](https://sienna-platform.github.io/PowerSimulations.jl/stable/) assigns one `DeviceModel` formulation to each component type in a simulation template.
If both hydro categories used `HydroDispatch`, the model could not apply `HydroDispatchRunOfRiverBudget` to dispatchable hydro and `FixedOutput` to nondispatchable hydro at the same time.
The translator therefore uses `HydroDispatch` for dispatchable hydro and `RenewableNonDispatch` for nondispatchable hydro.
:::

:::{note}
`HydroDispatch` can represent the ReEDS generation VOM as a hydro generation cost.
`RenewableNonDispatch` does not provide the same operating-cost representation.
The translator preserves the original nondispatchable hydro VOM as `ext["reeds_vom_cost"]`.
:::

## Pumped hydro

| ReEDS representation | ReEDS role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| `ReEDSStorage` with `pumped-hydro` technology | Storage with pumping and turbine generation | `HydroPumpTurbine` with linked head and tail `HydroReservoir` components | `PLEXOSGenerator` with linked head and tail `PLEXOSStorage` objects |

ReEDS classifies pumped hydro through its storage framework rather than the conventional-hydro framework.
The target representation preserves pumping, turbine generation, stored energy and the relationship between the head and tail reservoirs.

The translated energy capacity uses the explicit ReEDS value when available.
The ReEDS storage efficiency is applied during pumping while turbine efficiency remains one.

Initial head and tail levels use translator assumptions because ReEDS does not provide a fixed initial state.

:::{note}
PLEXOS can apply ReEDS VOM to turbine generation.
[HydroPowerSimulations.jl](https://sienna-platform.github.io/HydroPowerSimulations.jl/stable/) uses the `HydroPumpTurbine` operation cost for both generation and pumping while ReEDS applies this VOM only to generation.
The Sienna translator therefore sets the pumped-hydro operation cost to zero to avoid applying a generation-only cost during pumping.
It preserves the original value as `ext["reeds_vom_cost"]`.
:::

:::{note}
ReEDS does not provide external water inflow for this pumped-hydro representation.
Sienna therefore requires explicit zero inflow profiles on both reservoirs to satisfy the HydroPowerSimulations formulation.
:::

## Storage

| ReEDS identifier or family | ReEDS role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| Lithium-ion battery | Electrochemical storage | `EnergyReservoirStorage` | `PLEXOSBattery` |
| Other supported `ReEDSStorage` technologies | Generic energy storage | `EnergyReservoirStorage` | Storage-specific PLEXOS component |

## Transmission and interfaces

| ReEDS line or interface type | ReEDS role | Sienna representation | PLEXOS representation |
|---|---|---|---|
| AC corridor | Directional AC transfer capability | `MonitoredLine` | `PLEXOSLine` |
| VSC corridor | Directional HVDC transfer capability | `TwoTerminalGenericHVDCLine` | `PLEXOSLine` |
| LCC corridor | Directional HVDC transfer capability | `TwoTerminalGenericHVDCLine` | `PLEXOSLine` |
| B2B corridor | Directional back-to-back transfer capability | `TwoTerminalGenericHVDCLine` | `PLEXOSLine` |
| `ReEDSInterface` | Aggregate transfer interface | `AreaInterchange` | `PLEXOSInterface` |

## Reserves

| ReEDS reserve information | Sienna representation | PLEXOS representation |
|---|---|---|
| Reserve product | `VariableReserve` | `PLEXOSReserve` |
| Reserve direction | Reserve direction | Reserve type and direction properties |
| Regional eligibility | Service membership | Reserve memberships |
| Hourly requirement | Requirement timeseries | `Min Provision` timeseries |
