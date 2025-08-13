"""Configuration handler.

This script provides the base class to save the metadata for a given ReEDS scenario.
It can either read the information directly or throught a cases file.
"""

from dataclasses import field
from functools import singledispatch
from typing import Any, TypeVar

from pydantic import BaseModel

BaseModelConfigType = TypeVar("BaseModelConfigType", bound=BaseModel)


class BaseModelConfig(BaseModel):
    """Configuration of the Model.

    Attributes
    ----------
    fmap
        Dictionary with file to be parse
    defaults
        Default configuration for the model

    Raises
    ------
    AttributeError
    """

    defaults: dict[str, Any] = field(default_factory=dict)
    fmap: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def get_field_mapping(cls) -> dict[type[BaseModel], dict[str, str]]:
        """Return a dict of {target_class: {target_field: source_field}}."""
        raise NotImplementedError

    def transform_field(self, field_name: str, target_class: type[BaseModel]) -> Any:
        """Define custom field transformations."""
        return getattr(self, field_name)

    def to_class(
        self, target_class: type[BaseModelConfigType], base_instance: BaseModel | None = None
    ) -> BaseModelConfigType:
        """Transform this model instance to another Pydantic model."""
        field_mappings = self.get_field_mapping().get(target_class, {})

        transformed_data = base_instance.model_dump() if base_instance is not None else {}

        for target_field, source_field in field_mappings.items():
            transformed_data[target_field] = self.transform_field(source_field, target_class)

        return target_class(**transformed_data)


class ReEDSConfig(BaseModelConfig):
    """ReEDs specific configuration."""

    solve_year: list[int] | int | None = None
    weather_year: int | None = None

    @classmethod
    def get_field_mapping(cls) -> dict[type[BaseModel], dict[str, str]]:
        """Return a dict of {target_class: {target_field: source_field}}."""
        return {
            PlexosConfig: {
                "model_year": "solve_year",
                "horizon_year": "weather_year",
            },
            SiennaConfig: {"model_year": "solve_year"},
        }


class PlexosConfig(BaseModelConfig):
    """Plexos specific configuration."""
    model_config = {"protected_namespaces": ()}

    master_file: str | None = None
    model_name: str | None = None
    model_year: int | None = None
    horizon_year: int | None = None

    @classmethod
    def get_field_mapping(cls) -> dict[type[BaseModel], dict[str, str]]:
        """Return a dict of {target_class: {target_field: source_field}}."""
        return {
            PlexosConfig: {
                "model_year": "model_year",
                "horizon_year": "horizon_year",
            },
            SiennaConfig: {"model_year": "model_year"},
        }


class SiennaConfig(BaseModelConfig):
    """Sienna specific configuration."""

    model_config = {'protected_namespaces': ()}

    model_year: int | None = None


class InfrasysConfig(BaseModelConfig):
    """Infrasys specific configuration."""

    reference_year: int | None = None

    @classmethod
    def get_field_mapping(cls) -> dict[type[BaseModel], dict[str, str]]:
        """Return a dict of {target_class: {target_field: source_field}}."""
        return {
            PlexosConfig: {
                "horizon_year": "reference_year",
            },
            SiennaConfig: {"model_year": "reference_year"},
        }


@singledispatch
def get_year(model_class: BaseModelConfig) -> int | None:
    """Extract year variable from `BaseModelConfig`."""
    raise NotImplementedError("No get_year implementation for this type")


@get_year.register
def _(model_class: SiennaConfig):
    return model_class.model_year


@get_year.register
def _(model_class: PlexosConfig):
    return model_class.horizon_year
