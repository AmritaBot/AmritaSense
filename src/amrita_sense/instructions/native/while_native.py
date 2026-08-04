"""Native WHILE — jump+RET_FAR fast-path loop.

Usage::

    NATIVE_WHILE(condition).ACTION(body)

``body`` accepts:

* ``BaseNode`` — single node, ``call_offset`` + ``jump_near`` loop.
* ``NodeCompose`` | ``SelfCompileInstruction`` — wrapped into a **bubble**
  with automatic ``RET_FAR`` that jumps back to re‑evaluate the condition.
"""

from __future__ import annotations

from typing_extensions import Self, override

from amrita_sense.instructions.native._core import (
    NativeWhileNode,
    _classify_body,
)
from amrita_sense.instructions.ret2 import RET_FAR
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction


class NativeWhileClause(SelfCompileInstruction):
    """Fast-path WHILE loop.

    Bubble layout: ``[0]`` NOP landing, ``[1]`` self, ``[2]`` cond,
    ``[3]`` body slot (+RET_FAR), ``[4]`` NOP exit.

    ``RET_FAR`` (CONTINUE) pops ``[0]`` (= self - 1) and rebases to it;
    ``advance_pointer`` then naturally steps to ``[1]`` self which
    re-evaluates the condition.
    """

    _condition: Node[bool]
    _body: BaseNode | NodeCompose | SelfCompileInstruction | None

    __slots__ = ("_body", "_condition")

    def __init__(self, condition: Node[bool]) -> None:
        self._condition = condition
        self._body = None

    ### Fluent API ###

    def ACTION(self, body: BaseNode | NodeCompose | SelfCompileInstruction) -> Self:
        """Set the loop body."""
        if self._body is not None:
            raise TypeError("ACTION already set on NativeWhileClause")
        self._body = body
        return self

    ### Compile ###

    @override
    def extract(self) -> NodeCompose:
        if self._body is None:
            raise RuntimeError("NATIVE_WHILE requires .ACTION(body) before use")

        flat_cond, _ = _classify_body(self._condition)
        body, is_single = _classify_body(self._body)

        if is_single:
            body_slot: BaseNode | NodeCompose = body
        else:
            assert isinstance(body, NodeCompose)
            body_slot = NodeCompose(*body._graph, RET_FAR())

        # Layout: [0]=NOP landing, [1]=while_node, [2]=cond, [3]=body, [4]=NOP exit
        return NodeCompose(
            NOP,
            NativeWhileNode(
                condi_offset=1,
                body_offset=2,
                body_pos=3,
                self_pos=1,
                exit_pos=4,
                is_single=is_single,
            ),
            flat_cond,
            body_slot,
            NOP,
        )


def NATIVE_WHILE(condition: Node[bool]) -> NativeWhileClause:
    """Create a native fast-path WHILE loop.

    Args:
        condition: Boolean condition node.

    Returns:
        ``NativeWhileClause`` — call ``.ACTION(body)`` to set the loop body.
    """
    return NativeWhileClause(condition)
