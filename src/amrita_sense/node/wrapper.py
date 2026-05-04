import inspect
from collections.abc import Awaitable, Callable
from types import FrameType
from typing import TypeVar

from .core import Node as _Node

T = TypeVar("T")


def Node(
    tag: str | None = None,
    wrap_to_async: bool = True,
    address_able: bool = True,
):
    def wrapper(func: Callable[..., T | Awaitable[T]]) -> _Node[T]:
        frame: FrameType | None = inspect.currentframe()
        if not frame:
            raise RuntimeError("Can't get current frame")
        return _Node(func, tag, wrap_to_async, address_able, frame)

    return wrapper


__all__ = [
    "Node",
]
