from collections.abc import Callable
from typing import Any

from amrita_sense.node.core import BaseNode, Node
from amrita_sense.node.self_compile import SelfCompileInstruction


class AliasNode(BaseNode):
    """A node in workflow just mark node a alias."""

    __slots__ = ("alias", "node")
    func: Callable[..., Any]

    def __init__(self, node: Node, alias: str):
        if isinstance(node, SelfCompileInstruction):
            raise ValueError("Alias node can't be SelfCompileInstruction")
        self.node = node
        super()._init(
            self.node.func,
            tag=f"Alias::{alias}",
            wrap_to_async=node.wrap_to_async,
            address_able=True,
        )
        self.alias = alias

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.node.__call__(*args, **kwds)


def ALIAS(node: Node, alias: str) -> AliasNode:
    """A node in workflow just mark node a alias."""
    return AliasNode(node, alias)
