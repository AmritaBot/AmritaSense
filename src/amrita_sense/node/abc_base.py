from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING, Generic, TypeVar

from typing_extensions import Self

from amrita_sense.types import PointerVector

if TYPE_CHECKING:
    from amrita_sense.node.core import BaseNode
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

        This method processes all nodes in the composition, resolves aliases,
        expands self-compiling instructions, and builds the final execution graph.

        Args:
            cache_size: Maximum size of the cache for resolved nodes. Set to -1 to disable addressing caching.
            pre_cache: Preload addressing cache in compiling.

        Returns:
            A Compose_T instance representing the compiled workflow.
        """
        ...


class AbstractCompose(ABC, Generic[Calc_T]):
    @abstractmethod
    def __init__(self, *nodes: BaseNode | SelfCompileInstruction): ...

    @property
    @abstractmethod
    def calc(self) -> Calc_T: ...
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
        top: AbstractCompose[Calc_T] | None = None,
    ):
        """Build the executable workflow graph from the original composition.

        This internal method recursively processes the original graph, resolving
        aliases, expanding self-compiling instructions, and building the final
        execution structure.

        Args:
            current_path: Current address path during recursive processing.
            top: Reference to the top-level rendered composition for alias registration.
            cache_size: Cache size for address calculation.
            pre_cache: Pre-calculated address cache in %40 of cache_size.

        Raises:
            GraphBuildError: If the composition is already built or has no original graph.
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
