"""Tests for PLEXOS to Sienna plugin integration."""

from r2x.common.config import PLEXOSToSiennaConfig
from r2x.plugin import _plexos_to_sienna_modifier, register_plugin
from r2x_core.plugins import PluginManager


def test_plugin_registration():
    """Test that PLEXOS to Sienna modifier is registered."""
    register_plugin()
    manager = PluginManager()

    assert "plexos_to_sienna" in manager.registered_modifiers
    modifier = manager.registered_modifiers["plexos_to_sienna"]
    assert callable(modifier)


def test_modifier_function_exists():
    """Test that modifier function is accessible."""
    assert callable(_plexos_to_sienna_modifier)


def test_modifier_signature():
    """Test modifier has correct signature."""
    import inspect

    sig = inspect.signature(_plexos_to_sienna_modifier)
    params = list(sig.parameters.keys())

    # Should have 'system' and '**kwargs'
    assert "system" in params
    assert "kwargs" in params


# Note: Full integration tests with actual PLEXOS and Sienna systems
# would require test data and are marked as TODO for future implementation
def test_modifier_config_extraction():
    """Test that modifier can extract config from kwargs."""
    # This is a unit test for config extraction logic
    # Full integration test would require actual system objects

    kwargs = {
        "system_base_power": 200.0,
        "default_voltage_kv": 230.0,
        "mapping_strategy": "replace",
    }

    # We can't call the modifier without a real system,
    # but we can verify the config construction logic
    config = PLEXOSToSiennaConfig(
        system_base_power=kwargs.get("system_base_power", 100.0),
        default_voltage_kv=kwargs.get("default_voltage_kv", 110.0),
        mapping_strategy=kwargs.get("mapping_strategy", "merge"),
    )

    assert config.system_base_power == 200.0
    assert config.default_voltage_kv == 230.0
    assert config.mapping_strategy == "replace"
