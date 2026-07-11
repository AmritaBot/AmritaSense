from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from cachetools import LRUCache

from amrita_sense._unsafe import __flags__
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
        self._ptr_cache: LRUCache[int, list[int]] | None = (
            LRUCache(maxsize=cache_size) if cache_size != -1 else None
        )

        self._cache_lock: threading.Lock = threading.Lock()

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
        ptr_hash = hash(pointer)
        if not __flags__.NO_ADDRESSING_CACHE:
            with self._cache_lock:
                if (
                    self._ptr_cache is not None
                    and (rst := self._ptr_cache.get(ptr_hash)) is not None
                    and rst != pointer.base_addr
                ):
                    pointer.base_addr = rst.copy()
                    return True

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
            if not __flags__.NO_ADDRESSING_CACHE and self._ptr_cache is not None:
                with self._cache_lock:
                    self._ptr_cache[ptr_hash] = pointer.base_addr.copy()
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
            if not __flags__.NO_ADDRESSING_CACHE and self._ptr_cache is not None:
                with self._cache_lock:
                    self._ptr_cache[ptr_hash] = pointer.base_addr.copy()
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
                    if (
                        not __flags__.NO_ADDRESSING_CACHE
                        and self._ptr_cache is not None
                    ):
                        with self._cache_lock:
                            self._ptr_cache[ptr_hash] = pointer.base_addr.copy()
                    return True

        logger.debug("Failed to advance pointer through any path")
        return False

    def cache_resize(self, size: int) -> None:
        """Resize the LRUCache, make a full copy to new cache.

        Args:
            size (int): Max size of cache, set to -1 to disable cache.

        Raises:
            ValueError: size is a invalid number
        """
        with self._cache_lock:
            if size == -1:
                if self._ptr_cache is not None:
                    self._ptr_cache.clear()
                    self._ptr_cache = None
                return
            if size <= 0:
                raise ValueError("Size cannot lesser than 1")

            cache: None | LRUCache[int, list[int]] = self._ptr_cache
            self._ptr_cache = LRUCache(size)
            if cache is not None:
                for k, v in cache.items():
                    self._ptr_cache[k] = v
                cache.clear()  # To avoid memory leaks.
