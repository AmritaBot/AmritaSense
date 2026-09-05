from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING, Generic, TypeVar

from typing_extensions import Self

from amrita_sense.types import PointerVector

if TYPE_CHECKING:
    from amrita_sense.node.core import BaseNode, NodeComposeRendered
    from amrita_sense.node.self_compile import SelfCompileInstruction


Compose_T = TypeVar("Compose_T", bound="AbstractCompose")
Calc_T = TypeVar("Calc_T", bound="AbstractAddressCalculator")


class AbstractComposeOriginal(ABC, Generic[Compose_T]):
    @abstractmethod
    def __init__(
        self,
        *nodes: AbstractComposeOriginal[Compose_T] | BaseNode | SelfCompileInstruction,
    ):
        """Initialize a node composition with one or more elements.

        Args:
            *nodes: Variable number of nodes, compositions, or self-compile instructions.
        """
        ...

    @abstractmethod
    def __iter__(
        self,
    ) -> Iterator[BaseNode | AbstractComposeOriginal | SelfCompileInstruction]:
        """Iterate over the child elements of this source composition.

        Yields:
            Each child node, sub-composition, or self-compile instruction.
        """
        ...

    @abstractmethod
    def __rshift__(
        self,
        other: AbstractComposeOriginal[Compose_T] | BaseNode | SelfCompileInstruction,
    ) -> Self:
        """Append another element to this composition using the right-shift operator.

        Args:
            other: Another node, composition, or instruction to append.

        Returns:
            Self reference for method chaining.
        """
        ...

    def render(self) -> Compose_T:
        """Compile this composition into an executable workflow graph.

        Concrete source compositions override this to build their rendered
        graph.  The default implementation ``NodeCompose`` returns a
        ``NodeComposeRendered`` via the standard compilation pipeline.

        Returns:
            A ``Compose_T`` instance representing the compiled workflow.
        """
        ...

    @abstractmethod
    @classmethod
    def get_builder(cls) -> type[Compose_T]: ...


class AbstractCompose(ABC, Generic[Calc_T]):
    """Rendered-graph contract consumed by the runtime.

    This is the interface that ``WorkflowInterpreter``, the debugger and node
    ``_post_compile`` hooks rely on when they consume a *rendered* workflow
    graph.  At runtime the graph is treated as read-only, so the contract
    splits into two surfaces: a read side (``calc``, ``__getitem__``,
    ``__iter__``, ``__bool__``, ``__len__``) that the interpreter and hooks
    use, and a build side (``__init__(compose)``, ``_build(...)``) that
    ``render()`` and the renderer use while compiling.  Both build members
    are abstract so that any source composition can be rendered through its
    own ``get_builder()``.  Keeping the contract small makes it cheap to
    implement a fake rendered graph in tests (mock) or to plug in a custom
    rendered-graph implementation.

    The default, fully-featured implementation is ``NodeComposeRendered``
    (see ``amrita_sense.node.core``); anything satisfying this contract can
    be consumed wherever a rendered workflow is expected.
    """

    @abstractmethod
    def __init__(self, compose: "AbstractComposeOriginal"): ...

    @property
    @abstractmethod
    def calc(self) -> Calc_T:
        """Return the address calculator bound to this rendered graph."""
        ...

    @abstractmethod
    def __getitem__(self, key: int) -> BaseNode | AbstractCompose:
        """Access a node in the rendered graph by index.

        Args:
            key: Index of the node to access.

        Returns:
            The node at the specified index.
        """
        ...

    @abstractmethod
    def __iter__(self) -> Iterator[BaseNode | AbstractCompose]:
        """Iterate over all nodes in the rendered graph.

        Yields:
            Each node in the rendered graph sequentially.
        """
        ...

    @abstractmethod
    def __bool__(self) -> bool:
        """Return True if the rendered graph exists and is non-empty.

        Returns:
            Boolean indicating whether the graph has been built and contains nodes.
        """
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Return the number of nodes in the rendered graph.

        Returns:
            Number of nodes in the rendered graph.
        """
        ...

    @abstractmethod
    def _build(
        self,
        current_path: list[int] | None = None,
        top: NodeComposeRendered | None = None,
    ) -> None:
        """Build the compose

        Args:
            current_path (list[int] | None, optional): Current address, when current is the top, this is None.
            top (NodeComposeRendered | None, optional): The top-layer Compose, when current is top, this is Nonw.

        Returns:
            None: Right-In-Place action.
        """
        ...


class AbstractAddressCalculator(ABC, Generic[Compose_T]):
    @abstractmethod
    def __init__(self, graph: Compose_T): ...
    @abstractmethod
    def resolve_alias(self, alias: str) -> list[int]:
        """Look up an alias in the graph's alias map."""
        ...

    @abstractmethod
    def find_addr_safe(self, addr: list[int]) -> BaseNode | Compose_T | None:
        """Find a node at the given address, or None."""
        ...

    @abstractmethod
    def find_addr(self, addr: list[int]) -> BaseNode | Compose_T:
        """Find a node at the given address."""
        ...

    @abstractmethod
    def advance(self, pointer: PointerVector) -> bool:
        """Given a PointerVector, return the next pointer vector, or None if at end."""
        ...
