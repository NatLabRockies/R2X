"""Generic mapping registry base classes."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from loguru import logger

from r2x_core import Err, Ok, Result

K = TypeVar("K")  # Key type
V = TypeVar("V")  # Value type


class BaseRegistry(ABC, Generic[K, V]):
    """Abstract base class for mapping registries.

    This provides a common interface that can be specialized for
    different translation pairs.
    """

    def __init__(self) -> None:
        self._mappings: dict[K, V] = {}

    @abstractmethod
    def register(self, key: K, value: V, **metadata: Any) -> None:
        """Register a mapping.

        Parameters
        ----------
        key : K
            Mapping key (e.g., source category/type)
        value : V
            Mapping value (e.g., target type)
        **metadata : Any
            Additional metadata for this mapping
        """
        raise NotImplementedError

    def get(self, key: K) -> Result[V, str]:
        """Get mapping for key.

        Parameters
        ----------
        key : K
            Mapping key

        Returns
        -------
        Result[V, str]
            Ok with value or Err with error message
        """
        if key not in self._mappings:
            return Err(f"No mapping found for: {key}")
        return Ok(self._mappings[key])

    def has(self, key: K) -> bool:
        """Check if mapping exists.

        Parameters
        ----------
        key : K
            Mapping key

        Returns
        -------
        bool
            True if mapping exists
        """
        return key in self._mappings

    def list_keys(self) -> list[K]:
        """List all registered keys.

        Returns
        -------
        list[K]
            All registered keys
        """
        return list(self._mappings.keys())

    def clear(self) -> None:
        """Clear all mappings."""
        self._mappings.clear()
        logger.debug("Cleared all mappings from {}", self.__class__.__name__)
