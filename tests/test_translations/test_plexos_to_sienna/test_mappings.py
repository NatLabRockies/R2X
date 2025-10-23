"""Tests for PLEXOS to Sienna mappings."""

import pytest
from r2x_sienna.models import ThermalStandard
from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels

from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings
from r2x.translations.plexos_to_sienna.mappings.generator import initialize_generator_mappings
from r2x.translations.plexos_to_sienna.registry import get_registry


@pytest.fixture
def fresh_registry():
    """Create a fresh registry for each test."""
    # Clear the global registry
    registry = get_registry()
    registry._mappings.clear()
    yield registry
    # Clean up after test
    registry._mappings.clear()


def test_initialize_generator_mappings(fresh_registry):
    """Test initializing generator category mappings."""
    initialize_generator_mappings()

    # Verify thermal generators
    assert fresh_registry.get_sienna_type("Coal") == ThermalStandard
    assert fresh_registry.get_prime_mover("Coal") == PrimeMoversType.ST
    assert fresh_registry.get_fuel_type("Coal") == ThermalFuels.COAL

    assert fresh_registry.get_sienna_type("Gas") == ThermalStandard
    assert fresh_registry.get_prime_mover("Gas") == PrimeMoversType.CT
    assert fresh_registry.get_fuel_type("Gas") == ThermalFuels.NATURAL_GAS

    assert fresh_registry.get_sienna_type("Nuclear") == ThermalStandard
    assert fresh_registry.get_prime_mover("Nuclear") == PrimeMoversType.ST
    assert fresh_registry.get_fuel_type("Nuclear") == ThermalFuels.NUCLEAR

    assert fresh_registry.get_sienna_type("Oil") == ThermalStandard
    assert fresh_registry.get_prime_mover("Oil") == PrimeMoversType.CT
    assert fresh_registry.get_fuel_type("Oil") == ThermalFuels.DISTILLATE_FUEL_OIL

    # Renewable and hydro generators currently commented out
    # until r2x-sienna implements them (placeholder classes reject extra fields)
    # assert fresh_registry.get_sienna_type("Wind") == RenewableDispatch
    # assert fresh_registry.get_prime_mover("Wind") == PrimeMoversType.WT
    # assert fresh_registry.get_fuel_type("Wind") is None

    # assert fresh_registry.get_sienna_type("Solar") == RenewableDispatch
    # assert fresh_registry.get_prime_mover("Solar") == PrimeMoversType.PVe
    # assert fresh_registry.get_fuel_type("Solar") is None

    # assert fresh_registry.get_sienna_type("Hydro") == HydroDispatch
    # assert fresh_registry.get_prime_mover("Hydro") == PrimeMoversType.HY
    # assert fresh_registry.get_fuel_type("Hydro") is None


def test_initialize_all_mappings(fresh_registry):
    """Test initializing all mappings."""
    initialize_all_mappings()

    # Should at least have thermal generator mappings
    categories = fresh_registry.list_keys()
    assert "Coal" in categories
    assert "Natural Gas" in categories
    # Wind, Solar, Hydro commented out until r2x-sienna implements them
    assert len(categories) >= 5  # At least the 5 thermal generator types


def test_mapping_count(fresh_registry):
    """Test that all expected categories are registered."""
    initialize_generator_mappings()

    categories = fresh_registry.list_keys()
    # All generator types including thermal, renewable, and hydro
    expected_categories = ["Coal", "Gas", "Natural Gas", "Nuclear", "Oil", "Wind", "Solar", "Hydro"]

    assert len(categories) == len(expected_categories)
    assert set(categories) == set(expected_categories)
