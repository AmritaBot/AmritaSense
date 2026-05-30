from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amrita_sense.node.core import BaseNode, NodeCompose
else:
    NodeCompose = None


class SelfCompileInstruction(ABC):
    @abstractmethod
    def extract(self) -> NodeCompose: ...
    def __rshift__(
        self, other: BaseNode | SelfCompileInstruction | NodeCompose
    ) -> NodeCompose:
        """Create a node composition using the right-shift operator.

        This enables the `node1 >> node2` syntax for composing workflows.

        Args:
            other: Another node or composition to append to this node.

        Returns:
            A new NodeCompose containing this node and the other element.
        """
        from amrita_sense.instructions.workfl_ctrl import NOP

        return NodeCompose(NOP, self, other)
