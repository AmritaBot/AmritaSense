from collections.abc import Callable
from types import FrameType
from typing import Any

from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.node.core import BaseNode
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


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


class PushStackNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    alias_or_idata: str | list[int]

    __slots__ = (
        "address_able",
        "alias_or_idata",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, alias_or_idata: str | list[int]):
        self._init(self.__call__, "PushStackNode::__call__", False, True)
        self.alias_or_idata = alias_or_idata

    def __call__(self, pc: WorkflowInterpreter) -> None:
        pc._ret_addr_stack.push(
            PointerVector(pc.find_addr_alias(self.alias_or_idata))
            if isinstance(self.alias_or_idata, str)
            else PointerVector(self.alias_or_idata)
        )


def RET_FAR() -> RetFarNode:
    """Return from the current address.

    This instruction jump out the current bubble. This instruction will use the last jump address in the return address stack, which is usually used for returning from subprograms (always is node compose).

    Returns:
        RetFarNode: A node representing the RET_FAR instruction.
    """
    return RetFarNode()


def PUSH_STACK(alias_or_idata: str | list[int]) -> PushStackNode:
    """Push an address to the return address stack.

    This instruction push an address to the return address stack. The address can be an alias or an idata.

    Args:
        alias_or_idata (str | list[int]): The alias or idata to push.

    Returns:
        PushStackNode: A node representing the PUSH_STACK instruction.
    """
    return PushStackNode(alias_or_idata)
