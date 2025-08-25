"""Models for generator devices."""

from typing import Annotated, Any

from pint import Quantity
from pydantic import Field, NonNegativeFloat, field_serializer

from r2x.enums import PrimeMoversType, StorageTechs, ThermalFuels
from r2x.models.core import Device
from r2x.models.costs import HydroGenerationCost, RenewableGenerationCost, StorageCost, ThermalGenerationCost
from r2x.models.load import PowerLoad
from r2x.models.named_tuples import InputOutput, MinMax, UpDown, StartShut, StartTimeLimits
from r2x.models.topology import ACBus
from r2x.units import (
    ActivePower,
    ApparentPower,
    Energy,
    Percentage,
    PowerRate,
    Time,
    VOMPrice,
    ureg,
)


class Generator(Device):
    """Abstract generator class."""

    bus: Annotated[ACBus, Field(description="Bus where the generator is connected.")] | None = None
    rating: Annotated[
        ApparentPower | None,
        Field(ge=0, description="Maximum output power rating of the unit (MVA)."),
    ] = ApparentPower(1, "MVA")
    active_power: Annotated[
        ActivePower,
        Field(
            description=(
                "Initial active power set point of the unit in MW. For power flow, this is the steady "
                "state operating point of the system."
            ),
        ),
    ] = ActivePower(0.0, "MW")
    reactive_power: Annotated[
        ApparentPower | None,
        Field(
            description=(
                "Reactive power set point of the unit in MW. For power flow, this is the steady "
                "state operating point of the system."
            ),
        ),
    ] = ApparentPower(0.0, "MVA")
    base_mva: float = 1
    base_power: Annotated[
        ApparentPower | None,
        Field(
            gt=0,
            description="Base power of the unit (MVA) for per unitization.",
        ),
    ] = None
    must_run: Annotated[int | None, Field(description="If we need to force the dispatch of the device.")] = (
        None
    )
    vom_price: Annotated[VOMPrice, Field(description="Variable operational price $/MWh.")] | None = None
    prime_mover_type: (
        Annotated[PrimeMoversType, Field(description="Prime mover technology according to EIA 923.")] | None
    ) = None
    unit_type: Annotated[
        PrimeMoversType | None, Field(description="Prime mover technology according to EIA 923.")
    ] = None
    min_rated_capacity: Annotated[ActivePower, Field(description="Minimum rated power generation.")] = (
        0 * ureg.MW
    )
    ramp_up: (
        Annotated[
            PowerRate,
            Field(description="Ramping rate on the positve direction."),
        ]
        | None
    ) = None
    ramp_down: (
        Annotated[
            PowerRate,
            Field(description="Ramping rate on the negative direction."),
        ]
        | None
    ) = None
    min_up_time: (
        Annotated[
            Time,
            Field(ge=0, description="Minimum up time in hours for UC decision."),
        ]
        | None
    ) = None
    min_down_time: (
        Annotated[
            Time,
            Field(ge=0, description="Minimum down time in hours for UC decision."),
        ]
        | None
    ) = None
    mean_time_to_repair: (
        Annotated[
            Time,
            Field(gt=0, description="Total hours to repair after outage occur."),
        ]
        | None
    ) = None
    forced_outage_rate: (
        Annotated[
            Percentage,
            Field(description="Expected level of unplanned outages in percent."),
        ]
        | None
    ) = None
    planned_outage_rate: (
        Annotated[
            Percentage,
            Field(description="Expected level of planned outages in percent."),
        ]
        | None
    ) = None
    startup_cost: Annotated[NonNegativeFloat, Field(description="Cost in $ of starting a unit.")] | None = (
        None
    )
    shutdown_cost: (
        Annotated[NonNegativeFloat, Field(description="Cost in $ of shuting down a unit.")] | None
    ) = None
    active_power_limits: Annotated[
        MinMax | None, Field(description="Maximum output power rating of the unit (MVA).")
    ] = None
    reactive_power_limits: Annotated[
        MinMax | None, Field(description="Maximum output power rating of the unit (MVA).")
    ] = None

    @field_serializer("active_power_limits")
    def serialize_active_power_limits(self, min_max: MinMax | dict | None) -> dict[str, Any] | None:
        if min_max is None:
            return None
        if not isinstance(min_max, MinMax):
            min_max = MinMax(**min_max)
        if min_max is not None:
            return {
                "min": min_max.min.magnitude if isinstance(min_max.min, Quantity) else min_max.min,
                "max": min_max.max.magnitude if isinstance(min_max.max, Quantity) else min_max.max,
            }


class RenewableGen(Generator):
    """Abstract class for renewable generators."""


class RenewableDispatch(RenewableGen):
    """Curtailable renewable generator.

    This type of generator have a hourly capacity factor profile.
    """

    power_factor: float = 1.0
    operation_cost: RenewableGenerationCost | None = None


class RenewableNonDispatch(RenewableGen):
    """Non-curtailable renewable generator.

    Renewable technologies w/o operational cost.
    """

    power_factor: float = 1.0


class HydroGen(Generator):
    """Hydroelectric generator."""


class HydroDispatch(HydroGen):
    """Class representing flexible hydro generators."""

    operation_cost: HydroGenerationCost | None = None
    ramp_up: (
        Annotated[
            PowerRate,
            Field(ge=0, description="Ramping rate on the positve direction."),
        ]
        | None
    ) = None
    ramp_down: (
        Annotated[
            PowerRate,
            Field(ge=0, description="Ramping rate on the negative direction."),
        ]
        | None
    ) = None


class HydroFix(HydroGen):
    """Class representing unflexible hydro."""


class HydroEnergyReservoir(HydroGen):
    """Class representing hydro system with reservoirs."""

    ramp_limits: UpDown | None = None
    time_limits: UpDown | None = None
    operation_cost: HydroGenerationCost | None = None
    inflow: float | None = None
    initial_energy: (
        Annotated[NonNegativeFloat, Field(description="Initial water volume or percentage.")] | None
    ) = 0
    initial_storage: float | None = None
    storage_capacity: (
        Annotated[
            Energy,
            Field(description="Total water volume or percentage."),
        ]
        | None
    ) = None
    min_storage_capacity: (
        Annotated[
            Energy,
            Field(description="Minimum water volume or percentage."),
        ]
        | None
    ) = None
    storage_target: (
        Annotated[
            Energy,
            Field(description="Maximum energy limit."),
        ]
        | None
    ) = None


class HydroPumpedStorage(HydroGen):
    """Class representing pumped hydro generators."""

    operation_cost: HydroGenerationCost | StorageCost | None = None
    storage_duration: (
        Annotated[
            Time,
            Field(description="Storage duration in hours."),
        ]
        | None
    ) = None
    initial_volume: (
        Annotated[Energy, Field(gt=0, description="Initial water volume or percentage.")] | None
    ) = None
    storage_capacity: Annotated[
        UpDown,
        Field(description="Total water volume or percentage."),
    ]
    min_storage_capacity: (
        Annotated[
            Energy,
            Field(description="Minimum water volume or percentage."),
        ]
        | None
    ) = None
    pump_efficiency: Annotated[Percentage, Field(ge=0, le=1, description="Pumping efficiency.")] | None = None
    pump_load: (
        Annotated[
            ActivePower,
            Field(description="Load related to the usage of the pump."),
        ]
        | None
    ) = None

    @classmethod
    def example(cls) -> "HydroPumpedStorage":
        return HydroPumpedStorage(
            name="HydroPumpedStorage",
            active_power=ActivePower(100, "MW"),
            pump_load=ActivePower(100, "MW"),
            bus=ACBus.example(),
            prime_mover_type=PrimeMoversType.PS,
            storage_duration=Time(10, "h"),
            storage_capacity=UpDown(up=100, down=100),
            min_storage_capacity=Energy(10, "MWh"),
            pump_efficiency=Percentage(85, "%"),
            initial_volume=Energy(500, "MWh"),
            ext={"description": "Pumped hydro unit with 10 hour of duration"},
        )


class ThermalGen(Generator):
    """Class representing fuel based thermal generator."""

    fuel: Annotated[str, Field(description="Fuel category")] | None = None
    operation_cost: ThermalGenerationCost | None = None


class ThermalStandard(ThermalGen):
    """Class representing a standard thermal generator."""

    status: bool = True
    ramp_limits: UpDown | None = None
    time_limits: UpDown | None = None
    fuel: ThermalFuels = ThermalFuels.OTHER

    @classmethod
    def example(cls) -> "ThermalStandard":
        return ThermalStandard(
            name="ThermalStandard",
            bus=ACBus.example(),
            fuel=ThermalFuels.NATURAL_GAS,
            active_power=100.0 * ureg.MW,
            ext={"Additional data": "Additional value"},
        )


class ThermalMultiStart(ThermalGen):
    """Class representing a MultiStart thermal generator."""

    # TODO(jwright2): Enhance #146 Update to include more comprehensive treatment of ThermalMultiStart
    # start_time_limits and start_types

    status: bool = True
    ramp_limits: UpDown | None = None
    time_limits: UpDown | None = None
    fuel: ThermalFuels = ThermalFuels.OTHER
    power_trajectory: StartShut | None = None
    start_time_limits: StartTimeLimits | None = None
    start_types: int | None = None

    @classmethod
    def example(cls) -> "ThermalMultiStart":
        return ThermalMultiStart(
            name="ThermalMultiStart",
            bus=ACBus.example(),
            fuel=ThermalFuels.COAL,
            active_power=100.0 * ureg.MW,
            power_trajectory=StartShut(startup=4.0, shutdown=4.0),
            start_time_limits=StartTimeLimits(hot=2.0, warm=6.0, cold=12.0),
            start_types=1,
            ext={"Additional data": "Additional value"},
        )


class Storage(Generator):
    """Default Storage class."""

    storage_duration: (
        Annotated[
            Time,
            Field(description="Storage duration in hours."),
        ]
        | None
    ) = None
    initial_energy: Annotated[Percentage, Field(description="Initial state of charge.")] | None = None
    min_storage_capacity: Annotated[Percentage, Field(description="Minimum state of charge")] = Percentage(
        0, "%"
    )
    max_storage_capacity: Annotated[Percentage, Field(description="Minimum state of charge")] = Percentage(
        100, "%"
    )
    storage_capacity: (
        Annotated[
            Energy,
            Field(description="Total water volume or percentage."),
        ]
        | None
    ) = None


class EnergyReservoirStorage(Storage):
    """Battery energy storage model."""

    storage_technology_type: StorageTechs
    operation_cost: StorageCost | None = None
    charge_efficiency: Annotated[Percentage, Field(ge=0, description="Charge efficiency.")] | None = None
    discharge_efficiency: Annotated[Percentage, Field(ge=0, description="Discharge efficiency.")] | None = (
        None
    )
    storage_level_limits: MinMax = MinMax(min=0, max=1)
    initial_storage_capacity_level: float
    input_active_power_limits: MinMax
    output_active_power_limits: MinMax
    efficiency: InputOutput


class HybridSystem(Device):
    """Representation of hybrid system with renewable generation, load, thermal generation and storage.

    This class is just a link between two components.
    For the implementation see:
    - https://github.com/NREL-Sienna/PowerSystems.jl/blob/main/src/models/HybridSystem.jl
    """

    storage_unit: Storage | None = None
    renewable_unit: RenewableGen | None = None
    thermal_unit: ThermalGen | None = None
    electric_load: PowerLoad | None = None
