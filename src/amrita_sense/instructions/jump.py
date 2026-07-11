import difflib
from collections.abc import Callable
from types import FrameType
from typing import Any

from typing_extensions import override

from amrita_sense.exceptions import AliasNotFoundError
from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.node.core import BaseNode, NodeComposeRendered
from amrita_sense.runtime.workflow import WorkflowInterpreter


class JumpNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
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
        self._init(self._jump, None, False, True)

    def _jump(self, pc: WorkflowInterpreter):
        return pc.jump_to(self._node_addr)

    def __call__(self, pc: WorkflowInterpreter):
        return self._jump(pc)

    @override
    def _post_compile(self, compose: NodeComposeRendered) -> None:
        if self._node_addr:
            return
        if isinstance(self._alias_or_idata, str):
            if self._alias_or_idata not in compose.alias2vector_map:
                str_keys = list(compose.alias2vector_map.keys())
                matches = difflib.get_close_matches(
                    self._alias_or_idata, str_keys, n=1, cutoff=0.6
                )
                if matches:
                    suggestion = matches[0]
                    hint = f"{self._alias_or_idata} not found in namespace, did you mean {suggestion}"
                else:
                    hint = f"{self._alias_or_idata} not found in namespace, please check your alias!"
                raise AliasNotFoundError(hint)
            self._node_addr = compose.alias2vector_map[self._alias_or_idata]
        else:
            compose.calc.find_addr(
                self._alias_or_idata
            )  # Make sure the address exists, fail in compile time
            self._node_addr = self._alias_or_idata


def GOTO(aliasOrIdata: str | list[int]) -> JumpNode:
    return JumpNode(aliasOrIdata)
