from __future__ import annotations

import inspect
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from types import FrameType
from typing import TYPE_CHECKING, Any, Generic, TypeVar, overload

from amrita_core import logger
from typing_extensions import Self

from amrita_sense.exceptions import NullPointerException
from amrita_sense.node.self_compile import SelfCompileInstruction

if TYPE_CHECKING:
    from amrita_sense.runtime.workflow import WorkflowPC

NODE_T = TypeVar("NODE_T", bound=Any)


class BaseNode:
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature

    def _init(
        self,
        func: Callable[..., Any],
        tag: str | None,
        wrap_to_async: bool,
        address_able: bool,
        frame: FrameType | None = None,
    ):
        """Coconstructor"""
        frame = frame or inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        fun_sign: inspect.Signature = inspect.signature(func)
        self.fun_sign = fun_sign
        self.fun_frame = frame
        self.func = func
        self.tag = tag or f"NodeSuspend::{func.__name__}"
        self.wrap_to_async = wrap_to_async
        self.address_able = address_able

    def __repr__(self) -> str:
        return f"<Node at {id(self)}:{self.tag}>"

    def __str__(self) -> str:
        return self.tag

    def _pre_check(self, pointer: WorkflowPC) -> None: ...

    @abstractmethod
    def __call__(self, *args: Any, **kwds: Any) -> Any: ...
    def __rshift__(self, other) -> NodeCompose:
        return NodeCompose(self, other)


class Node(BaseNode, Generic[NODE_T]):
    tag: str
    func: Callable[..., Awaitable[NODE_T] | NODE_T]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature
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
        super()._init(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<Node at {id(self)}:{self.tag}>"

    def __str__(self) -> str:
        return self.tag

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.func(*args, **kwds)

    def __rshift__(self, other) -> NodeCompose:
        return NodeCompose(self, other)


class NodeCompose:
    _graph: list[NodeCompose | BaseNode | SelfCompileInstruction]

    def __init__(self, *nodes: NodeCompose | BaseNode | SelfCompileInstruction):
        self._graph = list(nodes)

    def __rshift__(
        self, other: NodeCompose | BaseNode | SelfCompileInstruction
    ) -> Self:
        self._graph.append(other)
        return self

    def render(self) -> NodeComposeRendered:
        logger.info("rendering node compose")
        r = NodeComposeRendered(self)
        r._build()
        return r


class NodeComposeRendered:
    _graph: list[BaseNode | NodeComposeRendered]
    __original_tmp: (
        NodeCompose | list[BaseNode | NodeCompose | SelfCompileInstruction] | None
    ) = None
    alias2vector_map: dict[str, list[int]]

    def __init__(
        self,
        original_graph: NodeCompose
        | list[BaseNode | NodeCompose | SelfCompileInstruction],
    ):
        self.__original_tmp = original_graph
        self.alias2vector_map = {}

    def __bool__(self) -> bool:
        return bool(self._graph if hasattr(self, "_graph") else False)

    def _build(
        self,
        current_path: list[int] | None = None,
        top: NodeComposeRendered | None = None,
    ):

        if current_path is None:
            current_path = []
        if top is None:
            top = self

        if hasattr(self, "_graph"):
            raise RuntimeError("NodeComposeRendered is already built")
        if not self.__original_tmp:
            raise RuntimeError("No original graph to build")

        self._graph = []

        if isinstance(self.__original_tmp, NodeCompose):
            self._process_nodes(self.__original_tmp._graph, current_path, top)
        else:
            self._process_nodes(self.__original_tmp, current_path, top)
        del self.__original_tmp

    def _process_nodes(
        self,
        nodes: list[BaseNode | NodeCompose | SelfCompileInstruction],
        current_path: list[int],
        top: NodeComposeRendered,
    ):
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
                rendered_compose = (
                    self._render_compose(extracted_compose, node_path, top)
                    if isinstance(extracted_compose, NodeCompose)
                    else extracted_compose
                )
                self._graph.append(rendered_compose)

            elif isinstance(node, AliasNode):
                if not node.address_able:
                    raise ValueError(
                        f"Alias node `{node.alias}` cannot be used in an addressable node."
                    )
                if node.alias in top.alias2vector_map:
                    raise RuntimeError(f"Alias {node.alias} already exists")
                top.alias2vector_map[node.alias] = node_path
                self._graph.append(node)

            else:
                self._graph.append(node)

    def _render_compose(
        self,
        node_compose: NodeCompose,
        compose_path: list[int],
        top: NodeComposeRendered,
    ) -> NodeComposeRendered:

        rendered = NodeComposeRendered(node_compose._graph)

        rendered._build(compose_path, top)
        return rendered

    def __getitem__(self, key: int):
        if key >= len(self._graph):
            raise NullPointerException(f"NodeComposeRendered index out of range: {key}")
        return self._graph[key]

    def __iter__(self):
        yield from self._graph
