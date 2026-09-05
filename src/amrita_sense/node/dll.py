from __future__ import annotations

import threading
from collections.abc import Iterator

from typing_extensions import Never

from amrita_sense.exceptions import GraphBuildError, NullPointerException
from amrita_sense.node.core import BaseNode, NodeCompose, NodeComposeRendered

from .abc_base import (
    AbstractCompose,
    AbstractComposeOriginal,
)


class DLLComposeProxy(AbstractCompose[Never]):
    """Proxy of a dynamic-linked NodeCompose.

    The proxy defers building the underlying compose until the composition
    graph is rendered. All mutable state is guarded by the _lock attribute so
    that _build/_apply are safe to run concurrently with the dunder methods
    below.

    Attributes:
        _original: The unbuilt source compose, or None once built.
        _compose: The rendered compose built from _original, or None before build.
        _prefix: Address path used to rebuild the compose after an apply.
        _top: The top-level rendered compose owning this proxy.
        _lock: Guards all mutable state against concurrent access.
    """

    _original: NodeCompose | None
    _compose: NodeComposeRendered | None
    _prefix: list[int] | None
    _top: NodeComposeRendered | None
    _lock: threading.Lock
    __slots__ = [
        "_compose",
        "_lock",
        "_original",
        "_prefix",
        "_top",
    ]

    def __init__(self, compose: DLLCompose):
        """Create a proxy bound to a single-owner DLLCompose.

        Args:
            compose: The source compose to build and proxy. It must not
                already own a proxy.

        Raises:
            RuntimeError: If compose already owns a proxy.
        """
        if compose._proxy is not None:
            raise RuntimeError("One DLLCompose instance could only be used once")
        self._original = compose._compose
        compose._proxy = self
        self._prefix = None
        self._top = None
        self._compose = None
        self._lock = threading.Lock()

    @property
    def calc(self) -> Never:
        """Raise because a proxy exposes no address calculator.

        Raises:
            AttributeError: Always, since calc is unavailable on a proxy.
        """
        raise AttributeError("DLLComposeProxy does not have a calculator")

    def _build(
        self,
        current_path: list[int] | None = None,
        top: NodeComposeRendered | None = None,
    ) -> None:
        """Build the underlying compose under the proxy lock.

        threading.Lock is not reentrant: calling _build again while the lock
        is held would deadlock, so the real logic lives in _build_unlocked
        which _apply also reuses.

        Args:
            current_path: Address path of this proxy inside the graph.
            top: The top-level rendered compose owning this proxy.

        Raises:
            GraphBuildError: If the proxy is already built, or if either
                current_path or top is None.
        """
        with self._lock:
            self._build_unlocked(current_path, top)

    def _build_unlocked(
        self,
        current_path: list[int] | None,
        top: NodeComposeRendered | None,
    ) -> None:
        """Run the build logic; the caller must already hold the lock.

        Args:
            current_path: Address path of this proxy inside the graph.
            top: The top-level rendered compose owning this proxy.

        Raises:
            GraphBuildError: If the proxy is already built, or if either
                current_path or top is None.
        """
        if self._original is None:
            raise GraphBuildError(
                "DLLComposeProxy: No original compose to build, or this proxy has already been built."
            )
        if current_path is None:
            raise GraphBuildError(
                "DLLComposeProxy: current_path cannot be None, this compose cannot be a root compose"
            )
        if top is None:
            raise GraphBuildError(
                "DLLComposeProxy: I cannot be a top-level compose, top cannot be None"
            )
        if self._top is not None and self._top is not top:
            raise GraphBuildError(
                "DLLComposeProxy: The top-level compose has changed, this proxy cannot be reused in a different context"
            )
        self._top = top
        self._prefix = current_path

        origin = self._original
        self._compose = origin.get_builder()(origin)
        self._compose._build(current_path, top)
        self._original = None

    def _apply(self, comp: NodeCompose):
        """Replace _original and rebuild from the previous path/top.

        Holds the lock to avoid racing with _build or the dunder methods;
        calls _build_unlocked directly to avoid double locking.

        Args:
            comp: The new source compose to build.
        """
        with self._lock:
            self._original = comp
            self._build_unlocked(self._prefix, self._top)

    def __getitem__(self, key: int) -> NodeComposeRendered | BaseNode:
        """Return the child at the given key from the rendered compose.

        Args:
            key: Index of the child to fetch.

        Returns:
            The child node or rendered compose at the key.

        Raises:
            GraphBuildError: If the compose has not been built yet.
        """
        with self._lock:
            if self._compose is None:
                raise GraphBuildError("DLLComposeProxy: Compose has not been built yet")
            return self._compose[key]

    def __iter__(self) -> Iterator[NodeComposeRendered | BaseNode]:
        """Iterate over the children of the rendered compose.

        Yields:
            Each child node or rendered compose in order.

        Raises:
            NullPointerException: If the compose has not been built yet.
        """
        with self._lock:
            if self._compose is None:
                raise NullPointerException(
                    "DLLComposeProxy: Compose has not been built yet"
                )
            return iter(self._compose)

    def __bool__(self) -> bool:
        """Return the truthiness of the rendered compose.

        Returns:
            False if the rendered compose is empty, True otherwise.

        Raises:
            NullPointerException: If the compose has not been built yet.
        """
        with self._lock:
            if self._compose is None:
                raise NullPointerException(
                    "DLLComposeProxy: Compose has not been built yet"
                )
            return bool(self._compose)

    def __len__(self) -> int:
        """Return the number of children in the rendered compose.

        Returns:
            The number of children in the rendered compose.

        Raises:
            NullPointerException: If the compose has not been built yet.
        """
        with self._lock:
            if self._compose is None:
                raise NullPointerException(
                    "DLLComposeProxy: Compose has not been built yet"
                )
            return len(self._compose)


class DLLCompose(AbstractComposeOriginal[DLLComposeProxy]):
    """Source compose that builds through a DLLComposeProxy.

    Unlike NodeCompose, a dynamic-linked compose cannot be rendered on its
    own; it must be embedded in a NodeCompose context so that the proxy
    receives the address path and top-level compose. The proxy can later be
    re-applied with a new compose while keeping the same location.

    Attributes:
        _compose: The wrapped source compose to build through the proxy.
        _proxy: The proxy bound to this instance, or None if unbound.
    """

    _compose: NodeCompose | None
    _proxy: DLLComposeProxy | None

    __slots__ = ("_compose", "_proxy")

    def __init__(self, compose: NodeCompose | None = None):
        """Initialize the compose wrapper.

        Args:
            compose: The source compose to proxy. Must be a NodeCompose.

        Raises:
            GraphBuildError: If compose is not a NodeCompose.
        """
        if not isinstance(compose, NodeCompose):
            raise GraphBuildError("Only NodeCompose is allowed.")
        self._compose = compose
        self._proxy = None

    def render(self) -> Never:
        """Disallow standalone rendering of a dynamic-linked compose.

        Raises:
            GraphBuildError: Always, since rendering must happen inside a
                NodeCompose context.
        """
        raise GraphBuildError(
            "DLLCompose: render() is not allowed, please use it in a NodeCompose context."
        )

    def apply(self, comp: NodeCompose):
        """Rebuild the proxy with a new source compose.

        Args:
            comp: The new source compose to apply to the bound proxy.

        Raises:
            GraphBuildError: If no proxy is bound, meaning the compose was
                never built.
        """
        if self._proxy is None:
            raise GraphBuildError("DLLCompose: No proxy to apply to")
        self._proxy._apply(comp)

    def get_proxy(self) -> DLLComposeProxy:
        """Return the bound proxy.

        Returns:
            The DLLComposeProxy bound to this instance.

        Raises:
            GraphBuildError: If no proxy is bound, meaning this compose has
                never been built.
        """
        if self._proxy is None:
            raise GraphBuildError(
                "DLLCompose: No proxy available, which means this compose has never been built."
            )
        return self._proxy

    @classmethod
    def get_builder(cls) -> type[DLLComposeProxy]:
        """Return the proxy class used to build this compose.

        Returns:
            The DLLComposeProxy class.
        """
        return DLLComposeProxy
