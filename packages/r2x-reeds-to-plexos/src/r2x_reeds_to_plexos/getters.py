"""Getter helpers for ReEDS → PLEXOS translation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from r2x_core import Ok, Result
from r2x_core.getters import getter

if TYPE_CHECKING:
    from r2x_reeds.models.components import ReEDSGenerator

    from r2x_core.translation_rules import TranslationContext

MMBTU_TO_GJ = 1.055056  # Unit conversion factor


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


@getter
def heat_rate_to_gj_per_mwh(_: TranslationContext, component: ReEDSGenerator) -> Result[float, ValueError]:
    """Convert heat rate from MMBtu/MWh to GJ/MWh."""
    heat_rate = getattr(component, "heat_rate", None)
    return Ok(_float_or_zero(heat_rate) * MMBTU_TO_GJ)


@getter
def fuel_price_per_gj(_: TranslationContext, component: ReEDSGenerator) -> Result[float, ValueError]:
    """Convert fuel price from $/MMBtu to $/GJ."""
    fuel_price = getattr(component, "fuel_price", None)
    if fuel_price is None:
        return Ok(0.0)
    return Ok(float(fuel_price) / MMBTU_TO_GJ)
