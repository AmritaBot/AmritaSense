from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import field as Field
from types import FrameType
from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from .matcher import DependsFactory, Matcher


class _Empty:
    pass


EMPTY = _Empty()  # Empty marker


class ParamDescriptor(TypedDict):
    type_hint: type | _Empty  # Type hint for the parameter, if available
    kind: Literal["required", "optional", "factory"]  # Parameter status marker
    default: (
        Any | _Empty
    )  # only when kind is "optional", this will have the default value; otherwise, it will be EMPTY


class DependencyMeta(TypedDict):
    params: dict[str, ParamDescriptor]  # arg name -> ParamDescriptor
    factory_map: dict[str, "DependsFactory"]  # Arg name -> DependsFactory


@dataclass
class FunctionData:
    function: Callable[..., Awaitable[Any]] = Field()
    signature: DependencyMeta = Field()
    frame: FrameType = Field()
    priority: int = Field()
    matcher: "Matcher" = Field()


__all__ = ["DependencyMeta", "FunctionData", "ParamDescriptor"]
