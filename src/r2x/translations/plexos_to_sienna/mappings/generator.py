"""Generator category mappings."""

from r2x_sienna.models import HydroDispatch, RenewableDispatch, ThermalStandard
from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels

from r2x.translations.plexos_to_sienna.registry import get_registry


def initialize_generator_mappings() -> None:
    """Initialize PLEXOS generator category to Sienna type mappings."""
    registry = get_registry()

    # Thermal generators
    registry.register(
        plexos_category="Coal",
        sienna_type=ThermalStandard,
        prime_mover=PrimeMoversType.ST,
        fuel_type=ThermalFuels.COAL,
    )

    registry.register(
        plexos_category="Gas",
        sienna_type=ThermalStandard,
        prime_mover=PrimeMoversType.CT,
        fuel_type=ThermalFuels.NATURAL_GAS,
    )

    registry.register(
        plexos_category="Natural Gas",
        sienna_type=ThermalStandard,
        prime_mover=PrimeMoversType.CT,
        fuel_type=ThermalFuels.NATURAL_GAS,
    )

    registry.register(
        plexos_category="Nuclear",
        sienna_type=ThermalStandard,
        prime_mover=PrimeMoversType.ST,
        fuel_type=ThermalFuels.NUCLEAR,
    )

    registry.register(
        plexos_category="Oil",
        sienna_type=ThermalStandard,
        prime_mover=PrimeMoversType.CT,
        fuel_type=ThermalFuels.DISTILLATE_FUEL_OIL,
    )

    registry.register(
        plexos_category="Wind",
        sienna_type=RenewableDispatch,
        prime_mover=PrimeMoversType.WT,
    )

    registry.register(
        plexos_category="Solar",
        sienna_type=RenewableDispatch,
        prime_mover=PrimeMoversType.PVe,
    )

    registry.register(
        plexos_category="Hydro",
        sienna_type=HydroDispatch,
        prime_mover=PrimeMoversType.HY,
    )
