from collections.abc import Callable
from types import FrameType
from typing import Any

from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.node.core import BaseNode
from amrita_sense.node.self_compile import SelfCompileInstruction


class AliasNode(BaseNode):
    """Workflow node that provides an alias for another node.

    This class wraps an existing node and assigns it a human-readable alias that
    can be used for addressing and jump operations within the workflow. The alias
    is registered in the workflow's alias map during rendering, allowing other
    nodes to reference this node by name rather than by address.

    Attributes:
        alias: The human-readable alias name for this node.
        node: The underlying node being aliased.
        func: Reference to the underlying node's function for direct execution.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    node: BaseNode
    __slots__ = (
        "address_able",
        "alias",
        "fun_frame",
        "fun_sign",
        "func",
        "node",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, node: BaseNode, alias: str):
        """Initialize an alias node wrapping another node.

        Args:
            node: The node to wrap with an alias. Must not be a SelfCompileInstruction.
            alias: The human-readable alias name to assign to this node.

        Raises:
            ValueError: If the wrapped node is a SelfCompileInstruction.
        """
        if isinstance(node, SelfCompileInstruction):
            raise ValueError("Alias node can't be SelfCompileInstruction")
        self.node = node
        self._init(
            self.node.func,
            tag=f"Alias::{alias}",
            wrap_to_async=node.wrap_to_async,
            address_able=True,
        )
        self.alias = alias

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        """Execute the underlying node with the given arguments.

        Args:
            *args: Positional arguments to pass to the underlying node.
            **kwds: Keyword arguments to pass to the underlying node.

        Returns:
            The result of executing the underlying node.
        """
        return self.node.__call__(*args, **kwds)


def ALIAS(node: BaseNode, alias: str) -> AliasNode:
    """Create an alias node for the specified node.

    This factory function creates an AliasNode that wraps the given node and
    assigns it the specified alias. The alias can then be used for addressing
    and jump operations within the workflow.

    Args:
        node: The node to create an alias for.
        alias: The human-readable alias name to assign.

    Returns:
        An AliasNode instance wrapping the original node with the specified alias.

    Example:
        ```python
        my_node = Node(my_function)
        aliased_node = ALIAS(my_node, "my_special_node")
        ```
    """
    return AliasNode(node, alias)
