"""Tests for generic registry base class."""

from r2x.common.registry import BaseRegistry


class SimpleRegistry(BaseRegistry[str, dict]):
    """Simple test registry implementation."""

    def register(self, key: str, value: dict, **metadata) -> None:
        """Register a key-value pair with metadata."""
        self._mappings[key] = {**value, **metadata}


def test_registry_initialization():
    """Test registry initialization."""
    registry = SimpleRegistry()
    assert len(registry.list_keys()) == 0


def test_registry_register_and_get():
    """Test registering and retrieving values."""
    registry = SimpleRegistry()
    registry.register("test_key", {"value": 1}, extra="metadata")

    result = registry.get("test_key")
    assert result.is_ok()
    data = result.unwrap()
    assert data["value"] == 1
    assert data["extra"] == "metadata"


def test_registry_get_nonexistent():
    """Test getting non-existent key returns Err."""
    registry = SimpleRegistry()
    result = registry.get("nonexistent")
    assert result.is_err()
    error_msg = result.error
    assert "no mapping found" in error_msg.lower()


def test_registry_has():
    """Test checking key existence."""
    registry = SimpleRegistry()
    registry.register("exists", {"value": 1})

    assert registry.has("exists")
    assert not registry.has("does_not_exist")


def test_registry_list_keys():
    """Test listing all registered keys."""
    registry = SimpleRegistry()
    registry.register("key1", {"value": 1})
    registry.register("key2", {"value": 2})
    registry.register("key3", {"value": 3})

    keys = registry.list_keys()
    assert len(keys) == 3
    assert set(keys) == {"key1", "key2", "key3"}


def test_registry_overwrite():
    """Test overwriting existing key."""
    registry = SimpleRegistry()
    registry.register("key", {"value": 1})
    registry.register("key", {"value": 2})

    result = registry.get("key")
    assert result.is_ok()
    assert result.unwrap()["value"] == 2
