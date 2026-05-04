import inspect
from collections.abc import Callable
from types import FrameType
from typing import Any

from typing_extensions import override

from amrita_sense.node.core import BaseNode, NodeComposeRendered
from amrita_sense.runtime.workflow import WorkflowPC


class JumpNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature
    _node_addr: list[int]
    _alias_or_node: str | BaseNode
    __slots__ = (
        "_alias_or_node",
        "_node_addr",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, aliasOrNode: str | BaseNode):
        self._alias_or_node = aliasOrNode
        super()._init(self.__call__, None, False, True)

    def __call__(self, pc: WorkflowPC):
        pc.jump_to(self._node_addr)

    @override
    def _pre_check(self, pointer: WorkflowPC) -> None:
        if isinstance(self._alias_or_node, str):
            self._node_addr = pointer.find_addr_alias(self._alias_or_node)
        else:
            # Manual depth-first traversal of the graph structure
            visited_nodes = set()
            target_node = self._alias_or_node
            graph = pointer.get_graph()

            def dfs_traverse(
                container: NodeComposeRendered, current_path: list[int]
            ) -> list[int] | None:
                """Manually traverse the graph structure with DFS to find target node and detect duplicates."""
                # Traverse each child in the container
                for idx, child in enumerate(container._graph):
                    new_path = [*current_path, idx]
                    child_id = id(child)

                    # Check for duplicate nodes (only for BaseNode instances)
                    if isinstance(child, BaseNode):
                        if child_id in visited_nodes:
                            raise ValueError(
                                f"Duplicate node detected during traversal: {child}"
                            )
                        visited_nodes.add(child_id)

                        # Check if this is our target
                        if child is target_node:
                            return new_path

                    # Recursively traverse nested NodeComposeRendered
                    if isinstance(child, NodeComposeRendered):
                        result = dfs_traverse(child, new_path)
                        if result is not None:
                            return result

                return None

            # Start DFS from the root graph (which is a NodeComposeRendered)
            result_path = dfs_traverse(graph, [])

            if result_path is None:
                raise ValueError(
                    f"Target node not found in workflow graph: {target_node}"
                )

            self._node_addr = result_path
