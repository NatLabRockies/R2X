"""Core models for R2X."""

from collections import defaultdict, namedtuple

from infrasys.component import Component
from typing import Annotated
from pydantic import Field, computed_field, field_serializer
from r2x.units import ureg


class BaseComponent(Component):
    """Infrasys base component with additional fields for R2X."""

    available: Annotated[bool, Field(description="If the component is available.")] | int = True
    category: Annotated[str, Field(description="Category that this component belongs to.")] | None = None
    ext: dict = Field(default_factory=dict, description="Additional information of the component.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def class_type(self) -> str:
        """Create attribute that holds the class name."""
        return type(self).__name__

    @field_serializer("ext", when_used="json")
    def serialize_ext(ext: dict):  # type:ignore  # noqa: N805
        for key, value in ext.items():
            if isinstance(value, ureg.Quantity):
                ext[key] = value.magnitude
        return ext


MinMax = namedtuple("MinMax", ["min", "max"])
Complex = namedtuple("Complex", ["real", "imag"])
FromTo_ToFrom = namedtuple("FromTo_ToFrom", ["from_to", "to_from"])
UpDown = namedtuple("UpDown", ["up", "down"])
InputOutput = namedtuple("InputOutput", ["input", "output"])


class Service(BaseComponent):
    """Abstract class for services attached to components."""


class Device(BaseComponent):
    """Abstract class for devices."""

    services: (
        Annotated[
            list[Service],
            Field(description="Services that this component contributes to.", default_factory=list),
        ]
        | None
    ) = None


class StaticInjection(Device):
    """Supertype for all static injection devices."""


class TransmissionInterfaceMap(BaseComponent):
    mapping: defaultdict[str, list] = defaultdict(list)  # noqa: RUF012


class ReserveMap(BaseComponent):
    mapping: defaultdict[str, list] = defaultdict(list)  # noqa: RUF012
