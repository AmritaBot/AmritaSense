from __future__ import annotations

from typing import TYPE_CHECKING

from amrita_sense.exceptions import NullPointerException
from amrita_sense.logging import logger

if TYPE_CHECKING:
    from amrita_sense.node.core import BaseNode, NodeComposeRendered
    from amrita_sense.types import PointerVector
else:
    NodeComposeRendered = None


class AddressCalculator:
    """A stateless (but cached) address computation utility."""

    def __init__(self, graph: NodeComposeRendered, cache_size: int = 1024):
        """Constructor

        Args:
            graph (NodeComposeRendered): Rendered workflow.
            cache_size (int, optional): Cache size. Defaults to 1024, set to -1 to disable cache.
        """
        self._graph: NodeComposeRendered = graph

    def resolve_alias(self, alias: str) -> list[int]:
        """Look up an alias in the graph's alias map."""
        if (ptr := self._graph.alias2vector_map.get(alias)) is None:
            raise NullPointerException(f"alias '{alias}' not found")
        return ptr.copy()

    def find_addr_safe(self, addr: list[int]) -> BaseNode | NodeComposeRendered | None:
        """Find a node at the given address, or None."""
        current: BaseNode | NodeComposeRendered = self._graph
        for idx in addr:
            if not isinstance(current, NodeComposeRendered):
                return None
            if idx >= len(current):
                return None
            current = current[idx]
        return current

    def find_addr(self, addr: list[int]) -> BaseNode | NodeComposeRendered:
        """Find a node at the given address."""
        if pl := self.find_addr_safe(addr):
            return pl
        raise NullPointerException(f"address {addr} not found")

    def advance(self, pointer: PointerVector) -> bool:
        """Given a PointerVector, return the next pointer vector, or None if at end.

        This uses LRU caching to avoid re‑traversing the graph for the same ptr.
        """
        if not pointer:
            return False
        graph: NodeComposeRendered = self._graph
        current_container: BaseNode | NodeComposeRendered = graph
        for idx in pointer.base_addr[:-1]:
            if isinstance(current_container, NodeComposeRendered):
                current_container = current_container[idx]
            else:
                return False

        end_idx = pointer[-1]
        if not isinstance(current_container, NodeComposeRendered):
            return False

        current_node: BaseNode | NodeComposeRendered = current_container[end_idx]
        if isinstance(current_node, NodeComposeRendered) and current_node:
            pointer.append(0)
            return True

        next_idx = end_idx + 1
        if next_idx < len(current_container):
            # Check if the next node is a NodeComposeRendered that should be entered immediately
            next_node: BaseNode | NodeComposeRendered = current_container[next_idx]
            if isinstance(next_node, NodeComposeRendered) and next_node:
                pointer[-1] = next_idx
                pointer.append(0)
            else:
                pointer[-1] = next_idx
            return True

        while pointer:
            pointer.pop()
            if not pointer:
                logger.debug("Reached end of workflow, no more nodes to process")
                return False

            parent_path: list[int] = pointer.base_addr[:-1]
            parent_container: BaseNode | NodeComposeRendered = graph
            for idx in parent_path:
                if isinstance(parent_container, NodeComposeRendered):
                    parent_container = parent_container[idx]
                else:
                    return False

            if isinstance(parent_container, NodeComposeRendered):
                current_parent_idx = pointer[-1]
                if current_parent_idx + 1 < len(parent_container):
                    next_parent_node: BaseNode | NodeComposeRendered = parent_container[
                        current_parent_idx + 1
                    ]
                    if (
                        isinstance(next_parent_node, NodeComposeRendered)
                        and next_parent_node
                    ):
                        pointer[-1] = current_parent_idx + 1
                        pointer.append(0)
                    else:
                        pointer[-1] = current_parent_idx + 1
                    return True

        logger.debug("Failed to advance pointer through any path")
        return False
