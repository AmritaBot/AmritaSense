import inspect
from collections.abc import Callable
from types import FrameType
from typing import Any

from typing_extensions import override

from amrita_sense.node.core import BaseNode
from amrita_sense.runtime.workflow import WorkflowPC


class JumpNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature
    _node_addr: list[int]
    _alias_or_idata: str | list[int]
    __slots__ = (
        "_alias_or_idata",
        "_node_addr",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, aliasOrIdata: str | list[int]):
        self._alias_or_idata = aliasOrIdata
        self._node_addr = []
        super()._init(self._jump, None, False, True)

    def _jump(self, pc: WorkflowPC):
        return pc.jump_to(self._node_addr)

    def __call__(self, pc: WorkflowPC):
        return self._jump(pc)

    @override
    def _pre_check(self, pointer: WorkflowPC) -> None:
        if self._node_addr:
            return
        if isinstance(self._alias_or_idata, str):
            self._node_addr = pointer.find_addr_alias(self._alias_or_idata)
        else:
            pointer.find_addr(self._alias_or_idata)
            self._node_addr = self._alias_or_idata


def GOTO(aliasOrIdata: str | list[int]) -> JumpNode:
    return JumpNode(aliasOrIdata)
