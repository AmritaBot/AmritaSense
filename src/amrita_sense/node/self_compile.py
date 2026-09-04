from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from amrita_sense.node.abc_base import AbstractComposeOriginal

if TYPE_CHECKING:
    from amrita_sense.node.core import BaseNode


class SelfCompileInstruction(ABC):
    @abstractmethod
    def extract(self) -> AbstractComposeOriginal: ...
    def __rshift__(
        self,
        other: BaseNode | SelfCompileInstruction | AbstractComposeOriginal,
    ) -> AbstractComposeOriginal:
        """Create a node composition using the right-shift operator.

        This enables the `node1 >> node2` syntax for composing workflows.

        Args:
            other: Another node or composition to append to this node.

        Returns:
            A new composition containing this node and the other element.
        """
        from amrita_sense.instructions.workfl_ctrl import NOP
        from amrita_sense.node.core import NodeCompose

        return NodeCompose(NOP, self, other)
