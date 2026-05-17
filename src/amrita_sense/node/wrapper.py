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
    """Decorator factory for creating workflow nodes from regular functions.

    This decorator converts a regular Python function into a workflow node that
    can be used in AmritaSense workflows. It automatically captures the function's
    context and wraps it with the necessary metadata for workflow execution.

    Args:
        tag: Optional human-readable identifier for the node. If not provided,
            the function name will be used.
        wrap_to_async: Whether to automatically wrap synchronous functions for
            async execution. Defaults to True.
        address_able: Whether this node can be referenced by address in the
            workflow graph. Defaults to True.

    Returns:
        A decorator function that wraps the target function as a workflow node.

    Example:
        ```python
        @Node(tag="my_custom_node", wrap_to_async=True)
        def my_function(x: int, y: str) -> str:
            return f"{x}: {y}"
        ```
    """

    def wrapper(func: Callable[..., T | Awaitable[T]]) -> _Node[T]:
        """Wrap a function as a workflow node.

        Args:
            func: The function to convert into a workflow node.

        Returns:
            A Node instance wrapping the original function.

        Raises:
            RuntimeError: If the current frame cannot be obtained for context capture.
        """
        frame: FrameType | None = inspect.currentframe()
        if not frame:
            raise RuntimeError("Can't get current frame")
        return _Node(func, tag, wrap_to_async, address_able, frame)

    return wrapper


__all__ = [
    "Node",
]
