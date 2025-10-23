"""Tests for PLEXOS to Sienna mapping loader."""

from r2x_sienna.models import RenewableDispatch, ThermalStandard
from r2x_sienna.models.enums import PrimeMoversType, ThermalFuels

from r2x.translations.plexos_to_sienna.mapping_loader import (
    FUEL_TYPE_MAP,
    PRIME_MOVER_MAP,
    SIENNA_TYPE_MAP,
    load_default_mappings,
    load_mappings_from_file,
    merge_mappings,
    resolve_mapping,
    validate_mapping,
    validate_mappings_file,
)
from r2x.translations.plexos_to_sienna.types import GeneratorCategoryMapping


def test_load_default_mappings():
    """Test loading default mappings from config/defaults.json."""
    defaults = load_default_mappings()

    # Should load successfully
    assert isinstance(defaults, dict)
    assert len(defaults) > 0

    # Check that known categories exist
    assert "Coal" in defaults
    assert "Gas" in defaults
    assert "Nuclear" in defaults

    # Verify structure of a mapping
    coal_mapping = defaults["Coal"]
    assert isinstance(coal_mapping, GeneratorCategoryMapping)
    assert coal_mapping.sienna_type == "ThermalStandard"
    assert coal_mapping.prime_mover == "ST"
    assert coal_mapping.fuel_type == "COAL"


def test_load_mappings_from_file_success(tmp_path):
    """Test loading mappings from a valid YAML file."""
    # Create a test YAML file
    yaml_content = """
defaults: built-in

overrides:
  Coal:
    sienna_type: ThermalStandard
    prime_mover: CC
    fuel_type: COAL

additions:
  CustomGas:
    sienna_type: ThermalStandard
    prime_mover: GT
    fuel_type: NATURAL_GAS
"""
    yaml_file = tmp_path / "test-mappings.yaml"
    yaml_file.write_text(yaml_content)

    # Load the file
    result = load_mappings_from_file(str(yaml_file))

    # Should succeed
    assert result.is_ok()
    config = result.unwrap()

    # Check structure
    assert config.defaults == "built-in"
    assert "Coal" in config.overrides
    assert config.overrides["Coal"].sienna_type == "ThermalStandard"
    assert config.overrides["Coal"].prime_mover == "CC"
    assert "CustomGas" in config.additions
    assert config.additions["CustomGas"].fuel_type == "NATURAL_GAS"


def test_load_mappings_from_file_not_found():
    """Test loading from non-existent file returns error."""
    result = load_mappings_from_file("/nonexistent/path/to/file.yaml")

    assert result.is_err()
    assert "not found" in result.error


def test_load_mappings_from_file_invalid_yaml(tmp_path):
    """Test loading from invalid YAML file returns error."""
    yaml_file = tmp_path / "invalid.yaml"
    yaml_file.write_text("invalid: yaml: content: [")

    result = load_mappings_from_file(str(yaml_file))

    assert result.is_err()
    assert "YAML" in result.error or "Failed" in result.error


def test_merge_strategy_merge():
    """Test merge strategy: defaults + overrides."""
    # Create defaults
    defaults = {
        "Coal": GeneratorCategoryMapping(sienna_type="ThermalStandard", prime_mover="ST", fuel_type="COAL"),
        "Gas": GeneratorCategoryMapping(
            sienna_type="ThermalStandard", prime_mover="CT", fuel_type="NATURAL_GAS"
        ),
    }

    # Create overrides - override Coal, add Wind
    overrides = {
        "Coal": {"sienna_type": "ThermalStandard", "prime_mover": "CC", "fuel_type": "COAL"},
        "Wind": {"sienna_type": "RenewableDispatch", "prime_mover": "WT", "fuel_type": None},
    }

    # Merge with "merge" strategy
    result = merge_mappings(defaults, overrides, "merge")

    # Should have 3 categories: Gas (default), Coal (overridden), Wind (added)
    assert len(result) == 3
    assert "Coal" in result
    assert "Gas" in result
    assert "Wind" in result

    # Coal should be overridden to CC
    assert result["Coal"].prime_mover == "CC"

    # Gas should keep default
    assert result["Gas"].prime_mover == "CT"

    # Wind should be added
    assert result["Wind"].sienna_type == "RenewableDispatch"


def test_merge_strategy_replace():
    """Test replace strategy: ignore defaults, use only overrides."""
    defaults = {
        "Coal": GeneratorCategoryMapping(sienna_type="ThermalStandard", prime_mover="ST", fuel_type="COAL"),
        "Gas": GeneratorCategoryMapping(
            sienna_type="ThermalStandard", prime_mover="CT", fuel_type="NATURAL_GAS"
        ),
    }

    overrides = {
        "Wind": {"sienna_type": "RenewableDispatch", "prime_mover": "WT", "fuel_type": None},
    }

    # Merge with "replace" strategy
    result = merge_mappings(defaults, overrides, "replace")

    # Should only have Wind (defaults ignored)
    assert len(result) == 1
    assert "Wind" in result
    assert "Coal" not in result
    assert "Gas" not in result


def test_merge_strategy_extend():
    """Test extend strategy: keep defaults, only add new categories."""
    defaults = {
        "Coal": GeneratorCategoryMapping(sienna_type="ThermalStandard", prime_mover="ST", fuel_type="COAL"),
        "Gas": GeneratorCategoryMapping(
            sienna_type="ThermalStandard", prime_mover="CT", fuel_type="NATURAL_GAS"
        ),
    }

    # Try to override Coal and add Wind
    overrides = {
        "Coal": {"sienna_type": "ThermalStandard", "prime_mover": "CC", "fuel_type": "COAL"},
        "Wind": {"sienna_type": "RenewableDispatch", "prime_mover": "WT", "fuel_type": None},
    }

    # Merge with "extend" strategy
    result = merge_mappings(defaults, overrides, "extend")

    # Should have 3 categories
    assert len(result) == 3
    assert "Coal" in result
    assert "Gas" in result
    assert "Wind" in result

    # Coal should NOT be overridden (extend mode)
    assert result["Coal"].prime_mover == "ST"

    # Wind should be added
    assert result["Wind"].sienna_type == "RenewableDispatch"


def test_resolve_mapping_valid():
    """Test resolving valid mapping to actual types and enums."""
    mapping = GeneratorCategoryMapping(sienna_type="ThermalStandard", prime_mover="ST", fuel_type="COAL")

    result = resolve_mapping(mapping)

    # Should succeed
    assert result.is_ok()
    sienna_type, prime_mover, fuel_type = result.unwrap()

    # Check resolved values
    assert sienna_type == ThermalStandard
    assert prime_mover == PrimeMoversType.ST
    assert fuel_type == ThermalFuels.COAL


def test_resolve_mapping_renewable_no_fuel():
    """Test resolving renewable mapping without fuel type."""
    mapping = GeneratorCategoryMapping(sienna_type="RenewableDispatch", prime_mover="WT", fuel_type=None)

    result = resolve_mapping(mapping)

    # Should succeed
    assert result.is_ok()
    sienna_type, prime_mover, fuel_type = result.unwrap()

    # Check resolved values
    assert sienna_type == RenewableDispatch
    assert prime_mover == PrimeMoversType.WT
    assert fuel_type is None


def test_resolve_mapping_invalid_sienna_type():
    """Test validating mapping with invalid sienna_type returns error."""
    # Use validate_mapping instead since Pydantic catches this during construction
    mapping_dict = {
        "sienna_type": "InvalidType",
        "prime_mover": "ST",
        "fuel_type": "COAL",
    }

    result = validate_mapping(mapping_dict)

    # Should fail due to Pydantic validation
    assert result.is_err()
    assert "Invalid" in result.error or "literal" in result.error


def test_resolve_mapping_invalid_prime_mover():
    """Test resolving mapping with invalid prime_mover returns error."""
    mapping = GeneratorCategoryMapping(sienna_type="ThermalStandard", prime_mover="INVALID", fuel_type="COAL")

    result = resolve_mapping(mapping)

    # Should fail
    assert result.is_err()
    assert "Unknown prime_mover" in result.error


def test_resolve_mapping_invalid_fuel_type():
    """Test resolving mapping with invalid fuel_type returns error."""
    mapping = GeneratorCategoryMapping(
        sienna_type="ThermalStandard", prime_mover="ST", fuel_type="INVALID_FUEL"
    )

    result = resolve_mapping(mapping)

    # Should fail
    assert result.is_err()
    assert "Unknown fuel_type" in result.error


def test_validate_mapping_valid():
    """Test that valid mapping passes validation."""
    mapping = {
        "sienna_type": "ThermalStandard",
        "prime_mover": "ST",
        "fuel_type": "COAL",
    }

    result = validate_mapping(mapping)

    # Should succeed
    assert result.is_ok()


def test_validate_mapping_invalid_structure():
    """Test that mapping with invalid structure fails validation."""
    mapping = {
        "sienna_type": "ThermalStandard",
        # Missing required fields
    }

    result = validate_mapping(mapping)

    # Should fail
    assert result.is_err()


def test_validate_mappings_file_valid(tmp_path):
    """Test validating a valid mappings file."""
    yaml_content = """
defaults: built-in

overrides:
  Coal:
    sienna_type: ThermalStandard
    prime_mover: ST
    fuel_type: COAL

additions:
  CustomWind:
    sienna_type: RenewableDispatch
    prime_mover: WT
"""
    yaml_file = tmp_path / "valid-mappings.yaml"
    yaml_file.write_text(yaml_content)

    result = validate_mappings_file(str(yaml_file))

    # Should succeed
    assert result.is_ok()


def test_validate_mappings_file_invalid_mapping(tmp_path):
    """Test validating file with invalid mapping fails."""
    yaml_content = """
defaults: built-in

overrides:
  Coal:
    sienna_type: InvalidType
    prime_mover: ST
    fuel_type: COAL
"""
    yaml_file = tmp_path / "invalid-mappings.yaml"
    yaml_file.write_text(yaml_content)

    result = validate_mappings_file(str(yaml_file))

    # Should fail
    assert result.is_err()
    assert "Invalid" in result.error or "Unknown" in result.error


def test_type_maps_completeness():
    """Test that type mapping dictionaries are comprehensive."""
    # Test SIENNA_TYPE_MAP
    assert "ThermalStandard" in SIENNA_TYPE_MAP
    assert "RenewableDispatch" in SIENNA_TYPE_MAP
    assert "HydroDispatch" in SIENNA_TYPE_MAP
    assert SIENNA_TYPE_MAP["ThermalStandard"] == ThermalStandard

    # Test PRIME_MOVER_MAP
    assert "ST" in PRIME_MOVER_MAP
    assert "GT" in PRIME_MOVER_MAP
    assert "CT" in PRIME_MOVER_MAP
    assert "CC" in PRIME_MOVER_MAP
    assert "WT" in PRIME_MOVER_MAP
    assert "PVe" in PRIME_MOVER_MAP
    assert "HY" in PRIME_MOVER_MAP
    assert PRIME_MOVER_MAP["ST"] == PrimeMoversType.ST

    # Test FUEL_TYPE_MAP
    assert "COAL" in FUEL_TYPE_MAP
    assert "NATURAL_GAS" in FUEL_TYPE_MAP
    assert "NUCLEAR" in FUEL_TYPE_MAP
    assert FUEL_TYPE_MAP["COAL"] == ThermalFuels.COAL
