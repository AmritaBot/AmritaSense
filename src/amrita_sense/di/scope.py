"""Execution scopes for generator-based dependency lifecycle management.

The design is adapted from two upstream projects:

* **FastAPI** — `fastapi/routing.py` creates a *pair* of `AsyncExitStack`s per
  request (an inner one closed before the response is sent and an outer one
  closed after), `fastapi/dependencies/utils.py` selects between them per
  dependency, `_get_computed_scope` in `fastapi/dependencies/models.py`
  derives the default scope, and `DependencyScopeError` rejects a wider-scoped
  dependency that depends on a narrower-scoped one.
* **NoneBot2** — `nonebot/message.py` opens one `AsyncExitStack` per event and
  threads it through every dependency, and `nonebot/internal/params.py`
  registers generator dependencies on that stack via `contextmanager` /
  `asynccontextmanager`.

AmritaSense keeps the same shape with the scopes renamed for a workflow
engine: `CALL` replaces FastAPI's `function`, `WORKFLOW` replaces its
`request`, and `DISPATCH` is the event-hook analogue of NoneBot2's per-event
stack.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Hashable
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    AsyncExitStack,
    asynccontextmanager,
)
from enum import Enum
from typing import Any

from typing_extensions import Self

__all__ = ["LifecycleScope", "Scope", "lift_sync_context"]


class Scope(str, Enum):
    """How long a generator dependency's resource stays alive.

    The scopes are nested — a `CALL` scope is closed while the enclosing
    `DISPATCH` scope is still open, which in turn is closed while the
    `WORKFLOW` scope is still open.
    """

    CALL = "call"
    """Closed as soon as the node call that requested the dependency returns."""

    DISPATCH = "dispatch"
    """Closed once every handler of the current event dispatch has run."""

    WORKFLOW = "workflow"
    """Closed when the interpreter stops executing."""


@asynccontextmanager
async def lift_sync_context(
    cm: AbstractContextManager[Any],
) -> AsyncGenerator[Any, None]:
    """Present a synchronous context manager as an asynchronous one.

    Lets every dependency be entered through `AsyncExitStack.enter_async_context`
    so a single stack keeps one deterministic LIFO teardown order across both
    kinds.  FastAPI vendors the same idea as `_AsyncLiftContextManager` in
    `fastapi/routing.py`.
    """
    with cm as value:
        yield value


class LifecycleScope:
    """An `AsyncExitStack` plus the resources it has produced.

    A scope owns at most one instance of a given dependency: `acquire` returns
    the already-created value when the key is present, otherwise it enters the
    context manager and remembers both.  Closing the scope runs every teardown
    in reverse order and is idempotent, so both the normal exit path and the
    interpreter's `terminate()` can call it safely.
    """

    __slots__ = ("_closed", "_stack", "_values", "scope")

    def __init__(self, scope: Scope) -> None:
        self.scope = scope
        self._stack: AsyncExitStack | None = AsyncExitStack()
        self._values: dict[Hashable, Any] = {}
        self._closed = False

    @property
    def closed(self) -> bool:
        """Whether the scope has already been closed."""
        return self._closed

    @property
    def active(self) -> bool:
        """Whether the scope can still accept new resources."""
        return not self._closed and self._stack is not None

    async def acquire(
        self,
        key: Hashable,
        cm_factory: Callable[[], AbstractAsyncContextManager[Any]],
        /,
    ) -> Any:
        """Return the resource for `key`, creating it on first use.

        `cm_factory` is called with no arguments and must return an async
        context manager; its `__aenter__` result is the injected value.
        """
        if key in self._values:
            return self._values[key]
        stack = self._stack
        if self._closed or stack is None:
            raise RuntimeError(
                f"Cannot acquire a resource from an inactive {self.scope.value!r} scope"
            )
        value = await stack.enter_async_context(cm_factory())
        self._values[key] = value
        return value

    async def aclose(self) -> None:
        """Close every resource in reverse order.  Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        stack, self._stack = self._stack, None
        self._values.clear()
        if stack is not None:
            await stack.aclose()

    async def __aenter__(self) -> Self:
        if self._closed or self._stack is None:
            raise RuntimeError(f"{self.scope.value!r} scope has already been closed")
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
