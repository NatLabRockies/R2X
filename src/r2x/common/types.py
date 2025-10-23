"""Common type definitions for R2X translations."""

from typing import Any, Protocol, TypeAlias

from r2x_core import System

# Generic system types
SourceSystem: TypeAlias = System
TargetSystem: TypeAlias = System

# Component mapping types
MappingDict: TypeAlias = dict[str, Any]


class ComponentConverter(Protocol):
    """Protocol for component converters."""

    def __call__(
        self,
        component: Any,
        source_system: System,
        target_system: System,
    ) -> Any:
        """Convert a component from source to target format."""
        ...


class TranslationRegistry(Protocol):
    """Protocol for translation registries."""

    def register(self, key: str, value: Any) -> None:
        """Register a mapping."""
        ...

    def get(self, key: str) -> Any:
        """Retrieve a mapping."""
        ...

    def has(self, key: str) -> bool:
        """Check if mapping exists."""
        ...
