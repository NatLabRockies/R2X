from functools import singledispatch
from typing import Any

from pint import Quantity

from r2x.models import Generator
from r2x.models.named_tuples import MinMax, UpDown
from r2x.units import get_magnitude


# TODO@pesap: This should read from the system base units.
# https://github.com/NREL/R2X/issues/159
def _get_multiplier(component):
    return get_magnitude(getattr(component, "base_power", None)) or 1.0


@singledispatch
def get_value(value, component) -> Any:
    msg = f"`get_value` not implemented for {type(component)} and {type(value)}"
    raise NotImplementedError(msg)


@get_value.register
def _(value: MinMax, component) -> MinMax:
    m = _get_multiplier(component)
    return MinMax(min=value.min * m, max=value.max * m)


@get_value.register
def _(value: float, component) -> float:
    return _get_multiplier(component) * value


@get_value.register
def _(value: Quantity, component) -> float:
    return _get_multiplier(component) * value.magnitude


@singledispatch
def get_max_active_power(component) -> float:
    msg = f"`get_max_active_power` not implemented for {type(component)}"
    raise TypeError(msg)


@get_max_active_power.register
def _(component: Generator) -> float:
    return get_value(component.active_power_limits, component).max


@singledispatch
def get_ramp_limits(component) -> UpDown:
    msg = f"`get_ramp_limits` not implemented for {type(component)}"
    raise TypeError(msg)


@get_ramp_limits.register
def _(component: Generator) -> UpDown:
    m = _get_multiplier(component)
    ramp = component.ramp_limits
    if not ramp:
        msg = f"Ramp not defined for {component.name=}"
        raise KeyError(msg)
    up = get_magnitude(ramp.up) * m
    down = get_magnitude(ramp.down) * m
    return UpDown(up=up, down=down)
