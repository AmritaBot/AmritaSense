import contextlib
from collections.abc import Awaitable, Callable
from types import FrameType
from typing import Any

from typing_extensions import override

from amrita_sense.exceptions import IllegalState
from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.node.core import BaseNode, NodeCompose, NodeComposeRendered
from amrita_sense.node.self_compile import SelfCompileInstruction
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
                compose=self._comp_rendered,
                middleware=self._mdw,
                object_io=self._io,
            )

    async def __call__(self):
        assert self._interpreter
        try:
            await self._interpreter.run()
        finally:
            with contextlib.suppress(IllegalState):
                await self._interpreter.terminate_all_forks(eol=self._onetime)
            if self._onetime:
                self._interpreter = None
            else:
                self._interpreter.reset()


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


def INTER_FN(block: NodeCompose | SelfCompileInstruction) -> NodeCompose:
    """Define an **interrupt service routine** (Sense interrupt handler).

    Appends :func:`~amrita_sense.instructions.interrupt.INTERRUPT_RET` to
    ``block`` so the routine auto-restores the interpreter context when it
    finishes.  Use this together with
    :func:`~amrita_sense.instructions.interrupt.INTERRUPT_INTO` (the
    interrupt dispatcher) and :func:`ARCHIVED_SEGMENT` (to hide the routine
    from normal execution flow).

    Args:
        block: The body of the interrupt routine (nodes or self-compiling
            instruction).

    Returns:
        A :class:`NodeCompose` representing the complete interrupt routine
        (body + :func:`INTERRUPT_RET`).
    """
    from amrita_sense.instructions.interrupt import INTERRUPT_RET

    if isinstance(block, SelfCompileInstruction):
        block = block.extract()
    return block >> INTERRUPT_RET()


def FN(block: NodeCompose | SelfCompileInstruction) -> NodeCompose:
    """Define a **regular function block** (Sense subroutine).

    Appends :func:`~amrita_sense.instructions.ret2.RET_FAR` to ``block`` so
    the function returns via the return-address stack when it finishes.  Use
    this together with
    :func:`~amrita_sense.instructions.ret2.PUSH_AND_GOTO` (the caller) and
    :func:`ARCHIVED_SEGMENT` (to hide the function body from normal
    execution flow).

    Args:
        block: The body of the function (nodes or self-compiling
            instruction).

    Returns:
        A :class:`NodeCompose` representing the complete function (body +
        :func:`RET_FAR`).
    """
    from amrita_sense.instructions.ret2 import RET_FAR

    if isinstance(block, SelfCompileInstruction):
        block = block.extract()
    return block >> RET_FAR()
