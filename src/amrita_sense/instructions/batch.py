import asyncio
from collections.abc import Awaitable, Callable, Iterable
from types import FrameType
from typing import Any

from exceptiongroup import BaseExceptionGroup

from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.node.core import (
    BaseNode,
    NodeCompose,
    NodeComposeRendered,
)
from amrita_sense.node.core import (
    Node as NodeType,
)
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.workflow import UNSET, WorkflowInterpreter
from amrita_sense.streaming import SuspendObjectStream


def _batch_call(nodes: Iterable[BaseNode], fail_fast: bool = True) -> NodeType[None]:
    @Node("__BATCH_CALLER__")
    async def caller(intp: WorkflowInterpreter):
        callers = [
            intp._call(lambda _, node=node: node, no_cache=True) for node in nodes
        ]
        exc = [
            i
            for i in (await asyncio.gather(*callers, return_exceptions=not fail_fast))
            if isinstance(i, BaseException)
        ]
        if exc:
            raise BaseExceptionGroup("Detected exceptions while batch run nodes.", exc)

    return caller


class BatchRun(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _io: SuspendObjectStream | None
    _mdw: Callable[["WorkflowInterpreter"], Awaitable[Any]] | None | object
    _comp_rendered: NodeComposeRendered
    _fail_fast: bool
    _graphs: list[NodeComposeRendered]
    _origin: tuple[NodeCompose | BaseNode | SelfCompileInstruction, ...]
    _interpreters: list[WorkflowInterpreter]

    __slots__ = (
        "_comp_rendered",
        "_fail_fast",
        "_graphs",
        "_interpreters",
        "_io",
        "_mdw",
        "_origin",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(
        self,
        *payload: BaseNode | NodeCompose | SelfCompileInstruction,
        middleware: Callable[["WorkflowInterpreter"], Awaitable[Any]]
        | None
        | object = UNSET,
        object_io: SuspendObjectStream | None = None,
        fail_fast: bool = False,
    ):
        self._fail_fast = fail_fast
        self._origin = payload
        self._io = object_io
        self._mdw = middleware
        self._init(self.__call__, "__BATCH_RUN__", False, True)
        self._interpreters = []

    def _post_compile(self, compose: NodeComposeRendered) -> None:
        nodes = []
        self._graphs = []
        for pl in self._origin:
            if isinstance(pl, BaseNode):
                nodes.append(pl)
            elif isinstance(pl, SelfCompileInstruction):
                self._graphs.append(pl.extract().render())
            else:
                pl = pl.render()
                self._graphs.append(pl)
        if nodes:
            self._graphs.append(
                NodeCompose(
                    _batch_call(nodes, fail_fast=self._fail_fast),
                ).render()
            )
        del self._origin

    def _pre_check(self, pointer: WorkflowInterpreter[SuspendObjectStream]):
        if self._interpreters:
            return
        for g in self._graphs:
            self._interpreters.append(
                pointer.fork_interpreter(g, self._mdw, self._io or pointer.object_io)
            )

    async def __call__(self, intp: WorkflowInterpreter) -> Any:
        try:
            if exc := [
                i
                for i in (
                    await asyncio.gather(
                        *[i.run() for i in self._interpreters],
                        return_exceptions=not self._fail_fast,
                    )
                )
                if i is not None
            ]:
                raise BaseExceptionGroup(
                    "Some exceptions were detected when running nodes", exc
                )
        finally:
            exc: list[BaseException] = [
                i
                for i in await asyncio.gather(
                    *[i.terminate(True) for i in self._interpreters],
                    return_exceptions=True,
                )
                if i is not None
            ]
            if exc:
                raise BaseExceptionGroup(
                    "Some exceptions were detected when running cleanup tasks", exc
                )


def BATCH_RUN(
    *nodes: BaseNode | NodeCompose | SelfCompileInstruction,
    sos_io: SuspendObjectStream | None = None,
    middleware: Callable[["WorkflowInterpreter"], Awaitable[Any]]
    | None
    | object = UNSET,
    fail_fast: bool = True,
) -> BatchRun:
    """Batch run nodes or NodeCompose.

    Args:
        sos_io (SuspendObjectStream | None, optional): Object stream. Defaults to the runner's default stream.
        middleware (Callable[[&quot;WorkflowInterpreter&quot;], Awaitable[Any]] | None | object, optional): Middleware. Defaults to UNSET to use runner's middleware.
        fail_fast (bool, optional): fail the execution when exceptions raised in runtime. Defaults to True.

    Returns:
        BatchRun: BatchRun node instance
    """
    return BatchRun(
        *nodes, object_io=sos_io, middleware=middleware, fail_fast=fail_fast
    )
