"""Tests for translation configuration classes."""

from r2x.common.config import PLEXOSToSiennaConfig, TranslationConfig


def test_translation_config_base():
    """Test base TranslationConfig class."""
    config = TranslationConfig()
    assert config.verbose is False


def test_plexos_to_sienna_config_defaults():
    """Test PLEXOSToSiennaConfig with default values."""
    config = PLEXOSToSiennaConfig()
    assert config.system_base_power == 100.0
    assert config.default_voltage_kv == 110.0
    assert config.category_mappings == {}
    assert config.mappings_file is None
    assert config.mapping_strategy == "merge"


def test_plexos_to_sienna_config_custom():
    """Test PLEXOSToSiennaConfig with custom values."""
    config = PLEXOSToSiennaConfig(
        system_base_power=200.0,
        default_voltage_kv=230.0,
        category_mappings={"Coal": {"sienna_type": "ThermalStandard"}},
        mappings_file="./custom.yaml",
        mapping_strategy="replace",
    )
    assert config.system_base_power == 200.0
    assert config.default_voltage_kv == 230.0
    assert config.category_mappings == {"Coal": {"sienna_type": "ThermalStandard"}}
    assert config.mappings_file == "./custom.yaml"
    assert config.mapping_strategy == "replace"


def test_config_immutability():
    """Test that config fields can be updated if needed."""
    config = PLEXOSToSiennaConfig()
    # Pydantic allows mutation by default
    config.system_base_power = 150.0
    assert config.system_base_power == 150.0
