from infrasys.models import InfraSysBaseModel
from pint import Quantity


class GeoLocation(InfraSysBaseModel):
    Latitude: float
    Longitude: float


class MinMax(InfraSysBaseModel):
    min: float | Quantity
    max: float | Quantity


class UpDown(InfraSysBaseModel):
    up: float | Quantity
    down: float | Quantity


class Complex(InfraSysBaseModel):
    real: float
    imag: float


class InputOutput(InfraSysBaseModel):
    input: float
    output: float


class FromTo_ToFrom(InfraSysBaseModel):  # type: ignore  # noqa: N801
    from_to: float | Quantity
    to_from: float | Quantity


class StartShut(InfraSysBaseModel):
    startup: float | Quantity
    shutdown: float | Quantity


class StartTimeLimits(InfraSysBaseModel):
    hot: float | Quantity
    warm: float | Quantity
    cold: float | Quantity


class TurbinePump(InfraSysBaseModel):
    turbine: float | Quantity
    pump: float | Quantity
