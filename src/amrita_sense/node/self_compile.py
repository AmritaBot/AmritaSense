from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amrita_sense.node.core import NodeCompose


class SelfCompileInstruction(ABC):
    @abstractmethod
    def extract(self) -> NodeCompose: ...
