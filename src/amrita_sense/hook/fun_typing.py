import inspect
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


def sign_func(func: Callable[..., Any]):
    signature = inspect.signature(func)
    params = signature.parameters
    types: dict[str, ParamDescriptor] = {}
    factories: dict[str, DependsFactory] = {}
    kind: Literal["required", "optional", "factory"]
    for name, prm in params.items():
        kind = "required"
        default = prm.default if prm.default != inspect.Parameter.empty else EMPTY
        anno = prm.annotation if prm.annotation != inspect.Parameter.empty else EMPTY
        if default is not EMPTY:
            if isinstance(default, DependsFactory):
                kind = "factory"
                factories[name] = default
                default = None
            else:
                kind = "optional"
        if isinstance(anno, str):
            anno = func.__globals__.get(anno, EMPTY)
            if anno is None:
                raise ValueError(
                    f"Cannot resolve annotation {anno} for parameter {name},"
                    + " please disable `__future__.annotations` and use a normal type hint instead."
                    + "Make sure the import is not only in `TYPE_CHECKING` blocks."
                )

        types[name] = ParamDescriptor(type_hint=anno, kind=kind, default=default)
    return DependencyMeta(params=types, factory_map=factories)


__all__ = ["DependencyMeta", "FunctionData", "ParamDescriptor", "sign_func"]
