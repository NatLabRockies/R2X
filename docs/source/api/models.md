# Component Models

## Topology components

```{eval-rst}
.. autopydantic_model:: r2x.models.Area
   :inherited-members: Component

.. autopydantic_model:: r2x.models.LoadZone

.. autopydantic_model:: r2x.models.ACBus
   :inherited-members: Bus

.. autopydantic_model:: r2x.models.DCBus
   :inherited-members: Bus

.. autopydantic_model:: r2x.models.DCBranch
   :inherited-members: Branch

.. autopydantic_model:: r2x.models.ACBranch
   :inherited-members: Branch

.. autopydantic_model:: r2x.models.AreaInterchange
   :inherited-members: Branch

.. autopydantic_model:: r2x.models.Line
   :inherited-members: ACBranch

.. autopydantic_model:: r2x.models.MonitoredLine
   :inherited-members: ACBranch

.. autopydantic_model:: r2x.models.Transformer2W
   :inherited-members: ACBranch

.. autopydantic_model:: r2x.models.TapTransformer
   :inherited-members: ACBranch

.. autopydantic_model:: r2x.models.PhaseShiftingTransformer
   :inherited-members: ACBranch

.. autopydantic_model:: r2x.models.TwoTerminalHVDCLine
   :inherited-members: ACBranch

.. autopydantic_model:: r2x.models.TModelHVDCLine
   :inherited-members: DCBranch
```

## Load components

```{eval-rst}
.. autopydantic_model:: r2x.models.PowerLoad

.. autopydantic_model:: r2x.models.StandardLoad

.. autopydantic_model:: r2x.models.InterruptiblePowerLoad

.. autopydantic_model:: r2x.models.FixedAdmittance
```


## Generator models

```{eval-rst}
.. autopydantic_model:: r2x.models.Generator
   :inherited-members: RenewableGen

.. autopydantic_model:: r2x.models.RenewableDispatch
   :inherited-members: RenewableGen

.. autopydantic_model:: r2x.models.RenewableNonDispatch
   :inherited-members: RenewableGen

.. autopydantic_model:: r2x.models.ThermalStandard
   :inherited-members: ThermalGen

.. autopydantic_model:: r2x.models.ThermalMultiStart
   :inherited-members: ThermalGen

.. autopydantic_model:: r2x.models.HydroDispatch
   :inherited-members: HydroGen

.. autopydantic_model:: r2x.models.HydroEnergyReservoir
   :inherited-members: HydroGen

.. autopydantic_model:: r2x.models.HydroTurbine
   :inherited-members: HydroGen
```


## Storage models

```{eval-rst}
.. autopydantic_model:: r2x.models.Storage
   :inherited-members: Generator

.. autopydantic_model:: r2x.models.EnergyReservoirStorage
   :inherited-members: Storage

.. autopydantic_model:: r2x.models.HydroPumpedStorage
   :inherited-members: HydroGen

.. autopydantic_model:: r2x.models.HydroPumpTurbine
   :inherited-members: HydroGen
```

## Hybrid representation

```{eval-rst}
.. autopydantic_model:: r2x.models.HybridSystem
```

## Services

```{eval-rst}
.. autopydantic_model:: r2x.models.Emission
   :inherited-members: Service

.. autopydantic_model:: r2x.models.Reserve
   :inherited-members: Service

.. autopydantic_model:: r2x.models.TransmissionInterface
   :inherited-members: Service
```
