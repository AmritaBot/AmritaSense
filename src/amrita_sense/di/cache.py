"""Per-scope registry of lifecycle-managed dependencies.

Adapted from NoneBot2's dependency cache in `nonebot/internal/params.py`:

* `CacheState` mirrors its `CacheState` enum.
* `DependencyCache` mirrors its `DependencyCache` — a result holder that is
  registered in the store *before* the value is computed, so a second resolver
  for the same key waits on it instead of running the provider twice.
* `DependencyStore` mirrors the plain `dependency_cache` dict that NoneBot2
  threads through `Dependent.solve`, keyed by the dependency callable.

Two deliberate differences from the upstream implementation:

* The key also carries the args fingerprint and the scope, so a provider whose
  inputs changed — or that is requested under a different lifecycle — does not
  hand back a stale resource.
* On a `BaseException` (e.g. `CancelledError`) the cache is *both* failed and
  dropped, rather than only dropped: a waiter that is still parked on the old
  entry has to be woken up, otherwise it would hang forever.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Hashable
from enum import Enum
from typing import Any, Generic, TypeVar

__all__ = ["CacheState", "DependencyCache", "DependencyStore"]

T = TypeVar("T")


class CacheState(str, Enum):
    """Lifecycle of a single dependency cache entry."""

    PENDING = "PENDING"
    FINISHED = "FINISHED"


class DependencyCache(Generic[T]):
    """Result holder that lets concurrent resolvers await one computation."""

    __slots__ = ("_exception", "_result", "_state", "_waiter")

    def __init__(self) -> None:
        self._state = CacheState.PENDING
        self._result: T | None = None
        self._exception: BaseException | None = None
        self._waiter = asyncio.Event()

    def done(self) -> bool:
        """Whether the value has been produced (or the computation failed)."""
        return self._state is CacheState.FINISHED

    def result(self) -> T:
        """Return the cached value, re-raising the stored exception if any."""
        if self._state is not CacheState.FINISHED:
            raise RuntimeError("Result is not ready")
        if self._exception is not None:
            raise self._exception
        return self._result  # type: ignore[return-value]

    def exception(self) -> BaseException | None:
        """Return the stored exception, if the computation failed."""
        if self._state is not CacheState.FINISHED:
            raise RuntimeError("Result is not ready")
        return self._exception

    def set_result(self, result: T) -> None:
        if self._state is not CacheState.PENDING:
            raise RuntimeError(f"Cache state invalid: {self._state}")
        self._result = result
        self._state = CacheState.FINISHED
        self._waiter.set()

    def set_exception(self, exception: BaseException) -> None:
        if self._state is not CacheState.PENDING:
            raise RuntimeError(f"Cache state invalid: {self._state}")
        self._exception = exception
        self._state = CacheState.FINISHED
        self._waiter.set()

    async def wait(self) -> T:
        """Wait until the value is ready and return it (or raise)."""
        await self._waiter.wait()
        return self.result()


class DependencyStore:
    """Maps a dependency key to its in-flight or finished computation.

    One store backs one resolution tree: a per-call store for `CALL`-scoped
    resources, a per-dispatch store for event hooks, and a per-interpreter
    store for everything longer-lived.
    """

    __slots__ = ("_caches",)

    def __init__(self) -> None:
        self._caches: dict[Hashable, DependencyCache[Any]] = {}

    def get(self, key: Hashable) -> DependencyCache[Any] | None:
        return self._caches.get(key)

    def put(self, key: Hashable, cache: DependencyCache[Any]) -> None:
        self._caches[key] = cache

    def discard(self, key: Hashable) -> None:
        self._caches.pop(key, None)

    def clear(self) -> None:
        self._caches.clear()

    async def resolve(self, key: Hashable, compute: Callable[[], Awaitable[T]], /) -> T:
        """Return the value for `key`, computing it at most once.

        The cache entry is published before `compute()` is awaited, so a
        concurrent resolver for the same key parks on `DependencyCache.wait()`
        rather than starting a second computation.
        """
        cache = self._caches.get(key)
        if cache is not None:
            return await cache.wait()
        cache = DependencyCache[T]()
        self._caches[key] = cache
        try:
            value = await compute()
        except Exception as exc:
            # Ordinary failures are remembered: every waiter should see them.
            cache.set_exception(exc)
            raise
        except BaseException as exc:
            # Cancellation must not leave a parked waiter behind, so fail the
            # entry as well as dropping it.
            cache.set_exception(exc)
            self._caches.pop(key, None)
            raise
        cache.set_result(value)
        return value
