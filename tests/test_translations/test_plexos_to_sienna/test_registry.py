"""Tests for PLEXOS to Sienna registry."""

from r2x_sienna.models import HydroDispatch, RenewableDispatch, ThermalStandard
from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels

from r2x.translations.plexos_to_sienna.registry import PLEXOSToSiennaRegistry, get_registry


def test_registry_initialization():
    """Test registry initialization."""
    registry = PLEXOSToSiennaRegistry()
    assert len(registry.list_keys()) == 0


def test_registry_register_thermal():
    """Test registering thermal generator mapping."""
    registry = PLEXOSToSiennaRegistry()
    registry.register(
        plexos_category="Coal",
        sienna_type=ThermalStandard,
        prime_mover=PrimeMoversType.ST,
        fuel_type=ThermalFuels.COAL,
    )

    assert registry.has("Coal")
    assert registry.get_sienna_type("Coal") == ThermalStandard
    assert registry.get_prime_mover("Coal") == PrimeMoversType.ST
    assert registry.get_fuel_type("Coal") == ThermalFuels.COAL


def test_registry_register_renewable():
    """Test registering renewable generator mapping."""
    registry = PLEXOSToSiennaRegistry()
    registry.register(plexos_category="Wind", sienna_type=RenewableDispatch, prime_mover=PrimeMoversType.WT)

    assert registry.has("Wind")
    assert registry.get_sienna_type("Wind") == RenewableDispatch
    assert registry.get_prime_mover("Wind") == PrimeMoversType.WT
    assert registry.get_fuel_type("Wind") is None  # Renewables don't have fuel


def test_registry_register_hydro():
    """Test registering hydro generator mapping."""
    registry = PLEXOSToSiennaRegistry()
    registry.register(plexos_category="Hydro", sienna_type=HydroDispatch, prime_mover=PrimeMoversType.HY)

    assert registry.has("Hydro")
    assert registry.get_sienna_type("Hydro") == HydroDispatch
    assert registry.get_prime_mover("Hydro") == PrimeMoversType.HY


def test_registry_get_nonexistent():
    """Test getting non-existent category returns None."""
    registry = PLEXOSToSiennaRegistry()
    assert registry.get_sienna_type("NonExistent") is None
    assert registry.get_prime_mover("NonExistent") is None
    assert registry.get_fuel_type("NonExistent") is None


def test_global_registry_singleton():
    """Test that get_registry returns the same instance."""
    registry1 = get_registry()
    registry2 = get_registry()
    assert registry1 is registry2
