from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import TYPE_CHECKING

from typing_extensions import Never, Self

from amrita_sense.exceptions import GraphBuildError, NullPointerException
from amrita_sense.node.core import BaseNode, NodeCompose, NodeComposeRendered

from .abc_base import (
    AbstractCompose,
    AbstractComposeOriginal,
)

if TYPE_CHECKING:
    from amrita_sense.node.self_compile import SelfCompileInstruction


class DLLComposeProxy(AbstractCompose[Never]):
    """Placeholder slot for a dynamic-linked source compose.

    A dynamic-linked compose is not compiled into a plain rendered graph.
    Instead the renderer places this proxy at its position in the compiled
    graph and fills it in lazily: the first _build compiles the wrapped
    source compose into an ordinary rendered compose kept in _compose, and
    the read-side dunder methods forward to it. apply() later swaps in a
    new source compose and recompiles it into the same slot, so the graph
    around the proxy never moves — like relinking a shared library at a
    fixed load address.

    The proxy is a linking placeholder, not a full rendered graph: it
    exposes no address calculator (calc always raises), is not directly
    executable on its own, and has no children until built. It implements
    AbstractCompose only so the renderer can treat it as a sub-container
    while compiling. All mutable state is guarded by the _lock attribute so
    that _build/_apply are safe to run concurrently with the dunder
    methods below.

    Attributes:
        _original: The unbuilt source compose to link, or None once built.
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
    _symbols_delta: set[str] | None
    __slots__ = [
        "_compose",
        "_lock",
        "_original",
        "_prefix",
        "_symbols_delta",
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
        self._symbols_delta = None
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
        """Run the full compilation lifecycle of the proxied compose.

        threading.Lock is not reentrant: calling _build again while the lock
        is held would deadlock, so the real logic lives in _build_unlocked,
        which _apply also reuses.

        Args:
            current_path: Address path of this proxy inside the graph.
            top: The top-level rendered compose owning this proxy.

        Raises:
            GraphBuildError: If there is no source compose to compile, or if
                either current_path or top is None.
        """
        with self._lock:
            self._build_unlocked(current_path, top)

    def _build_unlocked(
        self,
        current_path: list[int] | None,
        top: NodeComposeRendered | None,
    ) -> None:
        """Run the full compilation lifecycle; the caller must hold the lock.

        This is the shared entry point for the first render (_build) and for
        later re-renders (_apply), so instead of a bare build it runs the
        whole lifecycle:

        1. Remove the alias symbols registered by the previous build from top.
        2. Compile the wrapped source compose into its rendered form: call
           get_builder() on it to obtain the rendered class, then build that
           rendered compose in place at current_path. The read-side dunders
           of this proxy then forward to it.
        3. Record the alias symbols added by this build as the delta to clean
           up on the next lifecycle.
        4. Run the post-compile hooks collected on top during the build.

        On failure the partial state is rolled back (the rendered compose
        and the symbol delta are cleared). Either way the per-lifecycle
        scratch state is released in the end — the hook collector on top is
        reset and the source compose is dropped, since the proxy may be
        re-applied with a fresh source compose later.

        Args:
            current_path: Address path of this proxy inside the graph.
            top: The top-level rendered compose owning this proxy.

        Raises:
            GraphBuildError: If there is no source compose to compile (the
                proxy was never bound, or was already built and not
                re-applied), or if either current_path or top is None.
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

        if self._symbols_delta is not None:  # Delete the old symbols
            for symbol in self._symbols_delta:
                top.alias2vector_map.pop(symbol, None)

        symbols = set(top.alias2vector_map)
        try:
            top._collected_hooks = []

            origin = self._original
            self._compose = origin.get_builder()(origin)
            self._compose._build(current_path, top)

            self._symbols_delta = (
                top.alias2vector_map.keys() - symbols
            ) or None  # delta of symbols, None if no delta

            for hook in top._collected_hooks:  # Run post-compile hooks
                hook(top)
        except Exception:  # For cleanup
            self._compose = None
            self._symbols_delta = None
            raise
        finally:
            top._collected_hooks = None
            self._original = None

    def _apply(self, comp: NodeCompose):
        """Swap the source compose and rerun the full compilation lifecycle.

        Sets the new source compose, then delegates to _build_unlocked (the
        lock is already held here, so calling it directly avoids a deadlock)
        so the proxy is recompiled in place at its previous path and top.
        After this call the rendered compose reflects the new source at the
        same location.

        Args:
            comp: The new source compose to link.
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
    """Source wrapper that compiles into a DLLComposeProxy.

    Everyday workflows just chain NodeCompose and call render() on it —
    that is the default source container. A dynamic-linked compose is a
    different source container for the special case where the graph at a
    fixed position must be swappable after the first render: it holds the
    NodeCompose to link and declares, via get_builder(), that the renderer
    should build a DLLComposeProxy for it.

    It cannot be rendered standalone — the proxy needs an enclosing
    NodeCompose context to learn its address path and the top-level
    compose. Once built, apply() can swap the wrapped compose and
    recompile it in place, keeping the same location.

    Attributes:
        _compose: The wrapped source compose to link through the proxy.
        _proxy: The proxy bound to this instance, or None if unbound.
    """

    _compose: NodeCompose
    _proxy: DLLComposeProxy | None

    __slots__ = ("_compose", "_proxy")

    def __init__(self, compose: NodeCompose):
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

    def __iter__(
        self,
    ) -> Iterator[BaseNode | AbstractComposeOriginal | SelfCompileInstruction]:
        """Iterate over the wrapped source compose's children.

        Yields:
            Each child node, sub-composition, or self-compile instruction.
        """
        yield from self._compose

    def __rshift__(
        self,
        other: AbstractComposeOriginal | BaseNode | SelfCompileInstruction,
    ) -> Self:
        """Append an element to the wrapped source compose and return self.

        Appending to a DLLCompose mutates the NodeCompose it wraps, so the
        element becomes part of the next apply() payload.

        Args:
            other: Another node, composition, or instruction to append.

        Returns:
            Self reference for method chaining.
        """
        self._compose >>= other
        return self

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
        self._compose = comp
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
