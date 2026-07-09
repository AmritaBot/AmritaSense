from collections.abc import Callable
from types import FrameType
from typing import Any

from typing_extensions import Self

from amrita_sense._unsafe import __flags__
from amrita_sense.exceptions import BreakLoop
from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.workflow import WorkflowInterpreter


class DONode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _do_offset: int
    _jmp_addr: int
    _break_addr: int

    __slots__ = (
        "_break_addr",
        "_do_offset",
        "_jmp_addr",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, do_offset: int, jmp_addr: int, break_addr: int):
        self._do_offset = do_offset
        self._jmp_addr = jmp_addr
        self._break_addr = break_addr
        self._init(self._do_worker, None, True, False)

    async def _do_worker(self, ptr: WorkflowInterpreter):
        if not __flags__.SQUASHED_LOOP:
            try:
                await ptr.call_offset(self._do_offset)
            except BreakLoop:
                return ptr.jump_near(self._break_addr)
            ptr.jump_near(self._jmp_addr)
        else:
            base = ptr._pointer.copy().offset(self._jmp_addr)
            data = ptr.find_addr(
                base.base_addr,
            )
            assert isinstance(data, DowhileNode)
            condi_addr = base.copy().offset(data._condi_offset)

            try:
                while True:
                    await ptr.call_offset(self._do_offset)
                    if ptr.jump_marked:
                        return
                    if not await ptr.call_sub(condi_addr):
                        return ptr.jump_near(self._break_addr)
            except BreakLoop:
                return ptr.jump_near(self._break_addr)

    def __call__(self, ptr: WorkflowInterpreter):
        return self._do_worker(ptr)


class DowhileNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _back_addr: int
    _condi_offset: int
    _then_addr: int

    def __init__(self, condi_offset: int, then_addr: int, back_addr: int):
        self._condi_offset = condi_offset
        self._then_addr = then_addr
        self._back_addr = back_addr
        self._init(self._do_while_worker, None, False, False)

    async def _do_while_worker(self, ptr: WorkflowInterpreter):
        if await ptr.call_offset(self._condi_offset):
            ptr.jump_near(self._back_addr)
        else:
            ptr.jump_near(self._then_addr)

    def __call__(self, pc: WorkflowInterpreter):
        return self._do_while_worker(pc)


class DoWhileClause(
    SelfCompileInstruction
):  # DO >> do() >> WHILE(jump back to DO or NOP) >> CONDI >> NOP
    condition: Node[bool]
    do: Node

    def __init__(
        self,
        do: Node,
    ):
        self.do = do

    @property
    def WHILE(self) -> Callable[[Node[bool]], Self]:
        return lambda condition: (setattr(self, "condition", condition), self)[1]

    def extract(self) -> NodeCompose:
        return NodeCompose(
            DONode(1, 2, 4), self.do, DowhileNode(1, 4, 0), self.condition, NOP
        )


def DO(do: Node) -> DoWhileClause:
    return DoWhileClause(do)
