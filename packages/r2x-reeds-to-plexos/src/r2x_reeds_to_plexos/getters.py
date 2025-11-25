"""Getters for ReEDS to Plexos translation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from r2x_core import Ok, Result
from r2x_core.getters import getter

if TYPE_CHECKING:
    from r2x_reeds.models import ReEDSGenerator, ReEDSReserve, ReEDSTransmissionLine

    from r2x_core.context import TranslationContext


def _float_or_zero(value: Any | None) -> float:
    """Normalize optional numeric values."""
    if value is None:
        return 0.0
    return float(value)


@getter
def forced_outage_rate_percent(_: TranslationContext, component: ReEDSGenerator) -> Result[float, ValueError]:
    """Convert forced outage fraction (0-1) to percent expected by PLEXOS."""
    rate = getattr(component, "forced_outage_rate", None)
    return Ok(_float_or_zero(rate) * 100.0)


@getter
def min_capacity_factor_percent(
    _: TranslationContext, component: ReEDSGenerator
) -> Result[float, ValueError]:
    """Convert minimum capacity factor (0-1) to percent."""
    factor = getattr(component, "min_capacity_factor", None)
    return Ok(_float_or_zero(factor) * 100.0)


def line_max_flow(_: TranslationContext, component: ReEDSTransmissionLine) -> Result[float, ValueError]:
    """Return the larger of the forward/backward flow limits."""
    limits = getattr(component, "max_active_power", None)
    if limits is None:
        return Ok(0.0)
    return Ok(float(max(limits.from_to, limits.to_from)))


@getter
def line_min_flow(_: TranslationContext, component: ReEDSTransmissionLine) -> Result[float, ValueError]:
    """Return the negative of the maximum absolute flow for min_flow."""
    limits = getattr(component, "max_active_power", None)
    if limits is None:
        return Ok(0.0)
    max_abs = max(abs(limits.from_to), abs(limits.to_from))
    return Ok(-float(max_abs))


@getter
def reserve_timeframe(_: TranslationContext, component: ReEDSReserve) -> Result[float, ValueError]:
    """Return the reserve timeframe in seconds."""
    return Ok(_float_or_zero(getattr(component, "time_frame", None)))


@getter
def reserve_duration(_: TranslationContext, component: ReEDSReserve) -> Result[float, ValueError]:
    """Return the reserve duration in seconds."""
    return Ok(_float_or_zero(getattr(component, "duration", None)))


@getter
def reserve_requirement(_: TranslationContext, component: ReEDSReserve) -> Result[float, ValueError]:
    """Return the reserve requirement in MW."""
    return Ok(_float_or_zero(getattr(component, "max_requirement", None)))
