import difflib
import inspect
from collections.abc import Callable
from types import FrameType
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.workflow import WorkflowInterpreter

if TYPE_CHECKING:
    from amrita_sense.instructions.alias import AliasNode


class SubprogramJumpNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature
    _target_near: int
    __slots__ = (
        "_target_near",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, target_near: int):
        self._target_near = target_near
        self._init(
            func=self.__call__,
            tag=None,
            wrap_to_async=False,
            address_able=True,
        )

    def __call__(self, pc: WorkflowInterpreter):
        pc.jump_near(self._target_near)


class SubprogramStorage(SelfCompileInstruction):
    _nodes: tuple["AliasNode", ...]
    __slots__ = ("_nodes",)

    def __init__(self, *nodes: "AliasNode"):
        self._nodes = nodes

    def extract(self) -> NodeCompose:
        node_compose = [NOP, *self._nodes, NOP]
        addr: int = len(node_compose) - 1
        node_compose[0] = SubprogramJumpNode(addr)
        return NodeCompose(*node_compose)


class CallNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature
    _alias: str
    _addr: list[int]

    __slots__ = (
        "_addr",
        "_alias",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, alias: str, tag: str | None = None):
        self._alias = alias
        super()._init(self.__call__, tag, False, True)

    @override
    def _pre_check(self, pointer: WorkflowInterpreter) -> None:
        if (addr := pointer.get_graph().alias2vector_map.get(self._alias)) is None:
            str_keys = list(pointer.get_graph().alias2vector_map.keys())
            matches = difflib.get_close_matches(self._alias, str_keys, n=1, cutoff=0.6)
            if matches:
                suggestion = matches[0]
                hint = (
                    f"{self._alias} not found in namespace, did you mean {suggestion}"
                )
            else:
                hint = f"{self._alias} not found in namespace, please check your alias!"
            raise ValueError(hint)
        self._addr = addr

    async def __call__(self, pc: WorkflowInterpreter) -> Any:
        return await pc.call_sub(self._addr)


def CALL(alias: str) -> CallNode:
    return CallNode(alias)


def ARCHIVED_NODES(*nodes: "AliasNode") -> SubprogramStorage:
    return SubprogramStorage(*nodes)
