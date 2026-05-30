from collections.abc import Callable
from types import FrameType
from typing import Any

from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.node.core import BaseNode
from amrita_sense.runtime.workflow import WorkflowInterpreter


class RetFarNode(BaseNode):
    tag: str
    func: Callable[..., Any]
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

    def __init__(self):
        self._init(self.__call__, "RetFarNode::__call__", False, True)

    def __call__(self, pc: WorkflowInterpreter) -> None:
        ptr = pc._ret_addr_stack.pop()
        pc.jump_far_ptr(ptr.base_addr)


def RET_FAR() -> RetFarNode:
    """Return from the current address.

    This instruction jump out the current bubble. This instruction will use the last jump address in the return address stack, which is usually used for returning from subprograms (always is node compose).

    Returns:
        RetFarNode: A node representing the RET_FAR instruction.
    """
    return RetFarNode()
