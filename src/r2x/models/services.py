"""Models related to services."""

from typing import Annotated

from pydantic import Field

from r2x.enums import ReserveDirection
from r2x.models.core import Service
from r2x.models.named_tuples import MinMax


class Reserve(Service):
    """Base class representing a reserve contribution.
    
    This is a base class for reserve products. For specific reserve types,
    use ConstantReserve or VariableReserve classes.
    """

    time_frame: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "Saturation time_frame in minutes to provide reserve contribution, "
                "validation range: (0, nothing)"
            )
        ),
    ] = 0.0
    sustained_time: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "The time in seconds reserve contribution must be sustained at a specified level, "
                "validation range: (0, nothing)"
            )
        ),
    ] = 3600.0
    max_output_fraction: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description=(
                "The maximum fraction of each device's output that can be assigned to the service, "
                "validation range: (0, 1)"
            )
        ),
    ] = 1.0
    max_participation_factor: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description=(
                "The maximum portion [0, 1.0] of the reserve that can be contributed per device, "
                "validation range: (0, 1)"
            )
        ),
    ] = 1.0
    deployed_fraction: Annotated[
        float,
        Field(
            ge=0.0,
            le=1.0,
            description=(
                "Fraction of service procurement that is assumed to be actually deployed. "
                "Most commonly, this is assumed to be either 0.0 or 1.0, validation range: (0, 1)"
            )
        ),
    ] = 0.0
    direction: ReserveDirection

    @classmethod
    def example(cls) -> "Reserve":
        return Reserve(
            name="ExampleReserve",
            direction=ReserveDirection.UP,
        )


class ConstantReserve(Reserve):
    """A reserve product with a constant procurement requirement.

    Such as 3% of the system base power at all times. This reserve product includes online generators that can
    respond right away after an unexpected contingency, such as a transmission line or generator outage. When
    defining the reserve, the ReserveDirection must be specified to define this as a ReserveUp, ReserveDown,
    or ReserveSymmetric.
    """

    requirement: Annotated[
        float,
        Field(
            ge=0.0,
            description=(
                "The value of required reserves in p.u. (SYSTEM_BASE), "
                "validation range: (0, nothing)"
            )
        ),
    ]

    @classmethod
    def example(cls) -> "ConstantReserve":
        return ConstantReserve(
            name="ExampleConstantReserve",
            direction=ReserveDirection.UP,
            requirement=0.03,  # 3% of system base
        )


class VariableReserve(Reserve):
    """A reserve product with a time-varying procurement requirement.

    Such as a higher requirement during hours with an expected high load or high ramp. This reserve product
    includes online generators that can respond right away after an unexpected contingency, such as a
    transmission line or generator outage. When defining the reserve, the ReserveDirection must be specified
    to define this as a ReserveUp, ReserveDown, or ReserveSymmetric. To model the time varying requirement,
    a "requirement" time series should be added to this reserve.
    """

    requirement: Annotated[
        float,
        Field(
            ge=0.0,
            description="The required quantity of the product should be scaled by a TimeSeriesData"
        ),
    ]

    @classmethod
    def example(cls) -> "VariableReserve":
        return VariableReserve(
            name="ExampleVariableReserve",
            direction=ReserveDirection.UP,
            requirement=0.05,  # 5% of system base
        )


class TransmissionInterface(Service):
    """Component representing a collection of branches that make up an interface or corridor.

    It can be specified between different :class:`Area` or :class:`LoadZone`.
    The interface can be used to constrain the power flow across it
    """

    active_power_flow_limits: Annotated[
        MinMax, Field(description="Minimum and maximum active power flow limits on the interface (MW)")
    ]
    direction_mapping: Annotated[
        dict[str, int],
        Field(
            description=(
                "Dictionary of the line names in the interface and their direction of flow (1 or -1) "
                "relative to the flow of the interface"
            )
        ),
    ]

    @classmethod
    def example(cls) -> "TransmissionInterface":
        return TransmissionInterface(
            name="ExampleTransmissionInterface",
            active_power_flow_limits=MinMax(min=-100, max=100),
            direction_mapping={"line-01": 1, "line-02": -2},
        )
