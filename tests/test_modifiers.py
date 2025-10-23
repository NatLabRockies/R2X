"""Tests for system modifier registration and CLI generation."""

import pytest
from r2x_plexos.models import PLEXOSGenerator, PLEXOSNode

from r2x.common.config import PLEXOSToSiennaConfig
from r2x_core import PluginManager, System


def test_plexos_to_sienna_registered_with_config():
    """Test that plexos_to_sienna is registered with config class."""
    pm = PluginManager()

    # Check modifier is registered
    assert "plexos_to_sienna" in pm.registered_modifiers

    # Check config class is stored
    config_class = pm.get_modifier_config("plexos_to_sienna")
    assert config_class is PLEXOSToSiennaConfig


def test_validate_plexos_registered_without_config():
    """Test that validate_plexos is registered without config."""
    pm = PluginManager()

    assert "validate_plexos" in pm.registered_modifiers

    config_class = pm.get_modifier_config("validate_plexos")
    assert config_class is None


def test_modifier_execution_with_config_instance():
    """Test executing modifier with config instance."""
    from plexosdb import CollectionEnum
    from r2x_plexos.models import PLEXOSMembership

    from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings

    initialize_all_mappings()

    plexos_system = System(name="test", auto_add_composed_components=True)
    gen = PLEXOSGenerator(name="Gen1", category="Coal", max_capacity=100.0, units=1)
    node = PLEXOSNode(name="Node1", object_id=1)

    plexos_system.add_component(gen)
    plexos_system.add_component(node)

    membership = PLEXOSMembership(parent_object=gen, child_object=node, collection=CollectionEnum.Nodes)
    plexos_system.add_supplemental_attribute(gen, membership)
    plexos_system.add_supplemental_attribute(node, membership)

    # Execute with config instance
    pm = PluginManager()
    modifier = pm.registered_modifiers["plexos_to_sienna"]

    config = PLEXOSToSiennaConfig(system_base_power=200.0)
    sienna_system = modifier(plexos_system, config=config)

    assert sienna_system.name == "test_sienna"


def test_modifier_execution_with_kwargs():
    """Test executing modifier with kwargs (CLI-style)."""
    from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings

    initialize_all_mappings()

    plexos_system = System(name="test", auto_add_composed_components=True)
    node = PLEXOSNode(name="Node1", object_id=1)
    plexos_system.add_component(node)

    pm = PluginManager()
    modifier = pm.registered_modifiers["plexos_to_sienna"]

    # Pass config fields as kwargs (how CLI will call it)
    sienna_system = modifier(
        plexos_system,
        system_base_power=200.0,
        default_voltage_kv=220.0,
    )

    assert sienna_system is not None
    assert sienna_system.name == "test_sienna"


def test_plexos_to_sienna_modifier_with_warnings():
    """Test modifier succeeds but logs warnings for missing category."""
    from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings

    initialize_all_mappings()

    plexos_system = System(name="test")
    gen = PLEXOSGenerator(name="BadGen", category=None)  # Missing category
    node = PLEXOSNode(name="Node1", object_id=1)
    plexos_system.add_component(gen)
    plexos_system.add_component(node)

    pm = PluginManager()
    modifier = pm.registered_modifiers["plexos_to_sienna"]

    # Should succeed despite warnings
    sienna_system = modifier(plexos_system)
    assert sienna_system is not None
    assert sienna_system.name == "test_sienna"


def test_validate_plexos_modifier_execution():
    """Test executing validate_plexos via PluginManager."""
    from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings

    initialize_all_mappings()

    plexos_system = System(name="test")
    gen = PLEXOSGenerator(name="Gen1", category="Coal", max_capacity=100.0, units=1)
    plexos_system.add_component(gen)

    pm = PluginManager()
    validator_fn = pm.registered_modifiers["validate_plexos"]

    # Should return system unchanged
    result = validator_fn(plexos_system)
    assert result == plexos_system


def test_validate_plexos_modifier_raises_on_validation_errors():
    """Test validator raises RuntimeError when validation has errors."""
    from r2x.translations.plexos_to_sienna.mappings import initialize_all_mappings

    initialize_all_mappings()

    plexos_system = System(name="test")
    gen = PLEXOSGenerator(name="BadGen", category=None)  # Missing category
    plexos_system.add_component(gen)

    pm = PluginManager()
    validator_fn = pm.registered_modifiers["validate_plexos"]

    with pytest.raises(RuntimeError, match="Validation"):
        validator_fn(plexos_system)


def test_config_json_schema_generation():
    """Test that config class generates valid JSON schema."""
    schema = PLEXOSToSiennaConfig.model_json_schema()

    assert "properties" in schema
    assert "system_base_power" in schema["properties"]
    assert "default_voltage_kv" in schema["properties"]
    assert "mapping_strategy" in schema["properties"]

    # Check type mappings
    assert schema["properties"]["system_base_power"]["type"] == "number"
    assert schema["properties"]["mapping_strategy"]["enum"] == ["merge", "replace", "extend"]
