from __future__ import annotations

import inspect
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from types import FrameType
from typing import TYPE_CHECKING, Any, Generic, TypeVar, overload

from typing_extensions import Self

from amrita_sense.exceptions import GraphBuildError, NullPointerException
from amrita_sense.hook.fun_typing import DependencyMeta, sign_func
from amrita_sense.logging import debug_log, logger
from amrita_sense.node import addressing
from amrita_sense.node.addressing import AddressCalculator
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.types import PointerVector
from amrita_sense.utils import TimeInsighter, isabstractmethod

from . import self_compile

if TYPE_CHECKING:
    from amrita_sense.runtime.workflow import WorkflowInterpreter

NODE_T = TypeVar("NODE_T", bound=Any, covariant=True)


class BaseNode:
    """Abstract base class for all workflow nodes.

    This class defines the common interface and attributes for all node types
    in the workflow engine. It provides metadata storage, function wrapping,
    and basic operations like string representation and composition.

    Attributes:
        tag: Human-readable identifier for the node.
        func: The underlying callable function or method.
        wrap_to_async: Flag indicating if synchronous functions should be wrapped for async execution.
        address_able: Flag indicating if this node can be referenced by address.
        fun_frame: Frame object capturing the creation context of the node.
        fun_sign: Signature object describing the function's parameters.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    def _init(
        self,
        func: Callable[..., Any],
        tag: str | None,
        wrap_to_async: bool,
        address_able: bool,
        frame: FrameType | None = None,
    ):
        """Initialize the base node with function and metadata.

        This is a co-constructor that sets up the node's core attributes.

        Args:
            func: The underlying callable to wrap.
            tag: Optional human-readable identifier. If None, auto-generated from function name.
            wrap_to_async: Whether to wrap synchronous functions for async execution.
            address_able: Whether this node can be referenced by address.
            frame: Optional frame object for context capture. If None, uses current frame.

        Raises:
            RuntimeError: If no valid frame can be obtained.
        """
        frame = frame or inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        fun_sign = sign_func(func)
        self.fun_sign = fun_sign
        self.fun_frame = frame
        self.func = func
        self.tag = tag or f"NodeSuspend::{func.__name__}"
        self.wrap_to_async = wrap_to_async
        self.address_able = address_able

    def __repr__(self) -> str:
        """Return a detailed string representation of the node.

        Returns:
            String representation including memory address and tag.
        """
        return f"<Node at {id(self)}:{self.tag}>"

    def __str__(self) -> str:
        """Return the node's tag as its string representation.

        Returns:
            The human-readable tag of the node.
        """
        return self.tag

    @abstractmethod
    def _pre_check(self, pointer: WorkflowInterpreter) -> None:
        """Perform pre-execution checks on the node.

        This method is called before node execution and can be overridden by
        subclasses to perform validation or setup tasks.

        Args:
            pointer: The current workflow interpreter instance.
        """
        ...

    @abstractmethod
    def _post_compile(self, compose: NodeComposeRendered) -> None:
        """Perform post-compile checks on the node.

        This method is called after compose construction and can be overridden by
        subclasses to perform validation or setup tasks.

        Args:
            compose: The compiled node-compose
        """
        ...

    @abstractmethod
    def __call__(self, *args: Any, **kwds: Any) -> Any:
        """Execute the node with given arguments.

        This abstract method must be implemented by concrete node classes.

        Args:
            *args: Positional arguments to pass to the underlying function.
            **kwds: Keyword arguments to pass to the underlying function.

        Returns:
            The result of executing the node's function.
        """
        ...

    def __rshift__(
        self, other: BaseNode | SelfCompileInstruction | NodeCompose
    ) -> NodeCompose:
        """Create a node composition using the right-shift operator.

        This enables the `node1 >> node2` syntax for composing workflows.

        Args:
            other: Another node or composition to append to this node.

        Returns:
            A new NodeCompose containing this node and the other element.
        """
        return NodeCompose(self, other)

    def as_compose(self) -> NodeCompose:
        return NodeCompose(self)


class Node(BaseNode, Generic[NODE_T]):
    """Generic workflow node that wraps a callable function.

    This class represents a concrete workflow node that wraps an arbitrary
    callable function. It supports both synchronous and asynchronous functions
    and provides type safety through generic typing.

    Attributes:
        tag: Human-readable identifier for the node.
        func: The underlying callable function or method.
        wrap_to_async: Flag indicating if synchronous functions should be wrapped for async execution.
        address_able: Flag indicating if this node can be referenced by address.
        fun_frame: Frame object capturing the creation context of the node.
        fun_sign: Signature object describing the function's parameters.
    """

    tag: str
    func: Callable[..., Awaitable[NODE_T] | NODE_T]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    __slots__ = (
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    @overload
    def __init__(
        self,
        func: Callable[..., Awaitable[NODE_T] | NODE_T],
        tag: str | None,
        wrap_to_async: bool,
        address_able: bool,
    ): ...
    @overload
    def __init__(
        self,
        func: Callable[..., Awaitable[NODE_T] | NODE_T],
        tag: str | None,
        wrap_to_async: bool,
        address_able: bool,
        frame: FrameType | None = None,
    ): ...

    def __init__(self, *args, **kwargs):
        """Initialize a generic node with function and metadata.

        Args:
            func: The underlying callable to wrap.
            tag: Optional human-readable identifier.
            wrap_to_async: Whether to wrap synchronous functions for async execution.
            address_able: Whether this node can be referenced by address.
            frame: Optional frame object for context capture.
        """
        self._init(*args, **kwargs)

    def __repr__(self) -> str:
        """Return a detailed string representation of the node.

        Returns:
            String representation including memory address and tag.
        """
        return f"<Node at {id(self)}:{self.tag}>"

    def __str__(self) -> str:
        """Return the node's tag as its string representation.

        Returns:
            The human-readable tag of the node.
        """
        return self.tag

    if TYPE_CHECKING:

        def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
    else:

        @property
        def __call__(self):
            """Return the underlying function for direct execution.

            Returns:
                The wrapped function that can be called directly.
            """
            return self.func

    def __rshift__(
        self, other: BaseNode | SelfCompileInstruction | NodeCompose
    ) -> NodeCompose:
        """Create a node composition using the right-shift operator.

        Args:
            other: Another node or composition to append to this node.

        Returns:
            A new NodeCompose containing this node and the other element.
        """
        return NodeCompose(self, other)


class NodeCompose:
    """Container for composing multiple nodes into a workflow sequence.

    This class represents a linear composition of nodes that will be executed
    sequentially. It supports the `>>` operator for chaining nodes together
    and provides a render() method to compile the composition into an
    executable workflow graph.

    Attributes:
        _graph: List of nodes and sub-compositions in this composition.
    """

    _graph: list[NodeCompose | BaseNode | SelfCompileInstruction]

    def __init__(self, *nodes: NodeCompose | BaseNode | SelfCompileInstruction):
        """Initialize a node composition with one or more elements.

        Args:
            *nodes: Variable number of nodes, compositions, or self-compile instructions.
        """
        if any(isinstance(i, NodeComposeRendered) for i in nodes):
            raise TypeError("NodeComposeRendered cannot be used in NodeCompose")
        self._graph = list(nodes)

    def __rshift__(
        self, other: NodeCompose | BaseNode | SelfCompileInstruction
    ) -> Self:
        """Append another element to this composition using the right-shift operator.

        Args:
            other: Another node, composition, or instruction to append.

        Returns:
            Self reference for method chaining.
        """
        self._graph.append(other)
        return self

    def render(
        self, cache_size: int = 1024, pre_cache: bool = True
    ) -> NodeComposeRendered:
        """Compile this composition into an executable workflow graph.

        This method processes all nodes in the composition, resolves aliases,
        expands self-compiling instructions, and builds the final execution graph.

        Args:
            cache_size: Maximum size of the cache for resolved nodes. Set to -1 to disable addressing caching.
            pre_cache: Preload addressing cache in compiling.

        Returns:
            A NodeComposeRendered instance representing the compiled workflow.
        """
        debug_log(f"Size of the main graph is : {len(self._graph)}")
        with TimeInsighter() as tm:
            r = NodeComposeRendered(self)
            r._build(cache_size=cache_size, pre_cache=pre_cache)
        time_end = tm.t_diff
        logger.info(f"node compose rendered, cost: {(time_end.total_seconds())}s")
        return r


class NodeComposeRendered:
    """Compiled and executable workflow graph.

    This class represents a fully processed workflow graph that is ready for
    execution. It contains the resolved node structure, alias mappings, and
    provides methods for accessing nodes by address.

    Attributes:
        _graph: List of resolved base nodes and rendered compositions.
        alias2vector_map: Mapping from alias names to their address vectors.
    """

    _graph: list[BaseNode | NodeComposeRendered]
    __original_tmp: (
        NodeCompose | list[BaseNode | NodeCompose | SelfCompileInstruction] | None
    )
    alias2vector_map: dict[str, list[int]]
    """Mark for AliasNodes"""
    _collected_hooks: list[Callable[[NodeComposeRendered], Any]] | None
    _calc: AddressCalculator
    """Address calculator, only be set when compiled, in the top level of the workflow"""

    __slots__ = [
        "__original_tmp",
        "_calc",
        "_collected_hooks",
        "_graph",
        "alias2vector_map",
    ]

    @property
    def calc(self) -> AddressCalculator:
        """Get the address calculator for this rendered composition.

        Returns:
            The address calculator instance.

        Raises:
            AttributeError: If the address calculator is not set or this NodeComposeRendered instance is not the top level of the workflow.
        """
        return self._calc

    def __init__(
        self,
        original_graph: NodeCompose
        | list[BaseNode | NodeCompose | SelfCompileInstruction],
    ):
        """Initialize a rendered composition with the original graph.

        Args:
            original_graph: The original node composition or list of nodes to render.
        """
        self.__original_tmp = original_graph
        self.alias2vector_map = {}
        self._collected_hooks = None

    def __bool__(self) -> bool:
        """Return True if the rendered graph exists and is non-empty.

        Returns:
            Boolean indicating whether the graph has been built and contains nodes.
        """
        return bool(self._graph if hasattr(self, "_graph") else False)

    def __len__(self) -> int:
        """Return the number of nodes in the rendered graph.

        Returns:
            Number of nodes in the rendered graph.
        """
        return len(self._graph) if hasattr(self, "_graph") else -1

    def _build(
        self,
        current_path: list[int] | None = None,
        top: NodeComposeRendered | None = None,
        cache_size: int = 1024,
        pre_cache: bool = True,
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

        if current_path is None:
            current_path = []
        im_top: bool = False
        if top is None:
            top = self
            im_top = True

        if hasattr(self, "_graph"):
            raise GraphBuildError("NodeComposeRendered is already built")
        if not self.__original_tmp:
            raise GraphBuildError("No original graph to build")

        self._graph = []

        if im_top:
            top._collected_hooks = []

        if isinstance(self.__original_tmp, NodeCompose):
            self._process_nodes(self.__original_tmp._graph, current_path, top)
        else:
            self._process_nodes(self.__original_tmp, current_path, top)
        if im_top:
            self._calc = AddressCalculator(self, cache_size)
            if pre_cache:
                ptr = PointerVector()
                for _ in range(int(cache_size * 0.6)):
                    if not self._calc.advance(ptr):
                        break
            if self._collected_hooks:
                logger.debug("Running post-compile hooks...")
                for fn in self._collected_hooks:
                    fn(self)

        self.__original_tmp = None

    def _process_nodes(
        self,
        nodes: list[BaseNode | NodeCompose | SelfCompileInstruction],
        current_path: list[int],
        top: NodeComposeRendered,
    ):
        """Process a list of nodes during graph building.

        This internal method handles different node types during the rendering process.

        Args:
            nodes: List of nodes to process.
            current_path: Current address path in the graph.
            top: Top-level rendered composition for alias registration.
        """
        from amrita_sense.instructions.alias import AliasNode

        for idx, node in enumerate(nodes):
            node_path = [*current_path, idx]

            if isinstance(node, NodeCompose):
                rendered_compose: NodeComposeRendered | BaseNode = self._render_compose(
                    node, node_path, top
                )
                self._graph.append(rendered_compose)

            elif isinstance(node, SelfCompileInstruction):
                extracted_compose = node.extract()
                rendered_compose = self._render_compose(
                    extracted_compose, node_path, top
                )
                self._graph.append(rendered_compose)

            elif isinstance(node, AliasNode):
                if not node.address_able:
                    raise ValueError(
                        f"Alias node `{node.alias}` cannot be used in an addressable node."
                    )
                if node.alias in top.alias2vector_map:
                    raise GraphBuildError(
                        f"Alias {node.alias} already exists in address `{top.alias2vector_map[node.alias]}`"
                    )
                top.alias2vector_map[node.alias] = node_path
                self._graph.append(node)

            else:
                if not isabstractmethod(node._post_compile):
                    if top._collected_hooks is None:
                        raise GraphBuildError(
                            "Top level compose's hooks collection is None!"
                        )
                    top._collected_hooks.append(node._post_compile)
                self._graph.append(node)

    def _render_compose(
        self,
        node_compose: NodeCompose,
        compose_path: list[int],
        top: NodeComposeRendered,
    ) -> NodeComposeRendered:
        """Recursively render a nested node composition.

        Args:
            node_compose: The node composition to render.
            compose_path: Address path for this composition.
            top: Top-level rendered composition for alias registration.

        Returns:
            A rendered composition representing the nested structure.
        """

        rendered = NodeComposeRendered(node_compose._graph)

        rendered._build(compose_path, top)
        return rendered

    def __getitem__(self, key: int):
        """Access a node in the rendered graph by index.

        Args:
            key: Index of the node to access.

        Returns:
            The node at the specified index.

        Raises:
            NullPointerException: If the index is out of range.
        """
        if key >= len(self._graph):
            raise NullPointerException(f"NodeComposeRendered index out of range: {key}")
        return self._graph[key]

    def __iter__(self):
        """Iterate over all nodes in the rendered graph.

        Yields:
            Each node in the rendered graph sequentially.
        """
        yield from self._graph


self_compile.NodeCompose = NodeCompose  # For import.
addressing.NodeComposeRendered = NodeComposeRendered
