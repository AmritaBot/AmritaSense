import contextlib
from collections.abc import Awaitable, Callable
from types import FrameType
from typing import Any

from typing_extensions import override

from amrita_sense.exceptions import IllegalState
from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.logging import logger
from amrita_sense.node.core import BaseNode, NodeComposeRendered
from amrita_sense.runtime.workflow import UNSET, WorkflowInterpreter
from amrita_sense.streaming import SuspendObjectStream


class FuncBlock(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    _comp_rendered: NodeComposeRendered
    _mdw: Callable[["WorkflowInterpreter"], Awaitable[Any]] | None | object
    _io: SuspendObjectStream[Any] | None
    _interpreter: WorkflowInterpreter | None
    _onetime: bool
    __slots__ = (
        "_comp_rendered",
        "_io",
        "_mdw",
        "_onetime",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(
        self,
        sub_comp: NodeComposeRendered,
        middleware: Callable[["WorkflowInterpreter"], Awaitable[Any]] | None | object,
        object_io: SuspendObjectStream | None,
        one_time_interp: bool,
    ):
        self._comp_rendered = sub_comp
        self._mdw = middleware
        self._io = object_io
        self._interpreter = None
        self._init(self.__call__, None, False, True)
        self._onetime = one_time_interp

    @override
    def _pre_check(self, pointer: WorkflowInterpreter) -> None:
        if not self._interpreter:
            self._interpreter = pointer.fork_interpreter(
                self._comp_rendered,
                middleware=self._mdw,
                object_io=self._io,
            )

    async def __call__(self):
        assert self._interpreter
        logger.debug("Calling sub-workflow...")
        try:
            await self._interpreter.run()
        finally:
            with contextlib.suppress(IllegalState):
                await self._interpreter.terminate_all_forks(eol=self._onetime)
            if self._onetime:
                self._interpreter = None
            else:
                self._interpreter._ret_addr_stack.clear()
                self._interpreter._jump_marked = False
                self._interpreter._pointer.far_to([0])
                self._interpreter._pending_stop = False


def FUN_BLOCK(
    sub_comp: NodeComposeRendered,
    middleware: Callable[["WorkflowInterpreter"], Awaitable[Any]]
    | None
    | object = UNSET,
    object_io: SuspendObjectStream | None = None,
    one_time_interp: bool = False,
) -> FuncBlock:
    """Create a sub workflow call.

    Args:
        sub_comp (NodeComposeRendered): Sub compose to call.
        middleware (Callable[[&quot;WorkflowInterpreter&quot;], Awaitable[Any]] | None | object, optional): middleware to be used in sub interpreter. Defaults to UNSET.
        object_io (SuspendObjectStream | None, optional): (Please make sure it's thread safe, not shared between interpreters.). Defaults to None.
        one_time_interp (bool, optional): Whether to create a new interpreter for each call. Defaults to False.

    Returns:
        FuncBlock: Node.
    """
    return FuncBlock(
        sub_comp,
        middleware=middleware,
        object_io=object_io,
        one_time_interp=one_time_interp,
    )
