from collections.abc import Callable
from types import FrameType
from typing import Any

from typing_extensions import Self

from amrita_sense._unsafe import __flags__
from amrita_sense.exceptions import BreakLoop
from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.instructions.jump import JumpNode
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.workflow import WorkflowInterpreter


class WhileNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _condi_offset: int
    _do_offset: int
    _checkup_addr: int
    _else_addr: int

    __slots__ = (
        "_condi_offset",
        "_do_offset",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(
        self,
        condi_offset: int,
        do_offset: int,
        checkup_addr: int,
        else_addr: int,
    ):
        self._condi_offset = condi_offset
        self._do_offset = do_offset
        self._checkup_addr = checkup_addr
        self._else_addr = else_addr
        self._init(self._while_worker, None, False, True)

    async def _while_worker(self, pc: WorkflowInterpreter):
        if not __flags__.SQUASHED_LOOP:
            if await pc.call_offset(self._condi_offset):
                try:
                    await pc.call_offset(self._do_offset)
                except BreakLoop:
                    return pc.jump_near(self._else_addr)
                pc.jump_near(self._checkup_addr)
            else:
                pc.jump_near(self._else_addr)
        else:
            try:
                while await pc.call_offset(self._condi_offset):
                    await pc.call_offset(self._do_offset)
                    if pc._jump_marked:
                        break
                pc.jump_near(self._else_addr)
            except BreakLoop:
                return pc.jump_near(self._else_addr)

    def __call__(self, pc: WorkflowInterpreter):
        return self._while_worker(pc)


class CheckUpNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _jump_addr: int

    __slots__ = (
        "_checkup_addr",
        "_condi_offset",
        "_do_offset",
        "_else_addr",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, jump_near: int):
        self._jump_addr = jump_near
        self._init(self._while_checkup, None, False, False)

    def _while_checkup(self, pc: WorkflowInterpreter):
        pc.jump_near(self._jump_addr)

    def __call__(self, pc: WorkflowInterpreter) -> Any:
        return self._while_checkup(pc)


class WhileClause(SelfCompileInstruction):  # WHILE >> CONDI >> DO >> CHECKUP >> NOP
    condition: Node[bool]
    _action: BaseNode

    def __init__(self, condition: Node[bool]) -> None:
        self.condition = condition

    def _action_set(self, action: BaseNode):
        self._action = action

    @property
    def ACTION(self) -> Callable[[BaseNode], Self]:
        if hasattr(self, "_action"):
            raise RuntimeError("Please DO NOT follow a ACTION after a ACTION")
        return lambda node: (self, self._action_set(node))[0]

    def extract(self) -> NodeCompose:
        if isinstance(self._action, JumpNode):
            raise RuntimeError(
                "Please DO NOT use a GOTO node in a WHILE clause. Which will cause probably problems."
            )
        return NodeCompose(
            WhileNode(condi_offset=1, do_offset=2, checkup_addr=3, else_addr=4),
            self.condition,
            self._action,
            CheckUpNode(0),
            NOP,
        )


def WHILE(condition: Node[bool]) -> WhileClause:
    return WhileClause(condition)
