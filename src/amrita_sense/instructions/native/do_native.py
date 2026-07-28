"""Native DO-WHILE — natural-flow fast-path loop.

Usage::

    NATIVE_DO(body).WHILE(condition)

``body`` accepts:

* ``BaseNode`` — single node, reached naturally (no extra hop).
* ``NodeCompose`` | ``SelfCompileInstruction`` — wrapped with a
  ``NativeBubbleEnterNode`` so the engine enters the bubble, then
  exits via the normal ``advance_pointer`` mechanism (no ``RET_FAR``).
"""

from __future__ import annotations

from typing_extensions import Self, override

from amrita_sense.instructions.native._core import (
    NativeBubbleEnterNode,
    NativeDoWhileNode,
    _classify_body,
)
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction


class NativeDoClause(SelfCompileInstruction):
    """Fast-path DO-WHILE loop.

    **Single-node layout:** ``[0]`` body, ``[1]`` NativeDoWhileNode, ``[2]`` cond, ``[3]`` NOP exit.

    **Bubble layout:** ``[0]`` NativeBubbleEnterNode, ``[1]`` body bubble, ``[2]`` NativeDoWhileNode, ``[3]`` cond, ``[4]`` NOP exit.
    """

    _body: BaseNode | NodeCompose | SelfCompileInstruction
    _condition: Node[bool] | None

    __slots__ = ("_body", "_condition")

    def __init__(self, body: BaseNode | NodeCompose | SelfCompileInstruction) -> None:
        self._body = body
        self._condition = None

    ### Fluent API ###

    def WHILE(self, condition: Node[bool]) -> Self:
        """Set the loop condition."""
        if self._condition is not None:
            raise TypeError("NATIVE_DO can only have a single .WHILE(condition)")
        self._condition = condition
        return self

    ### Compile ###

    @override
    def extract(self) -> NodeCompose:
        if self._condition is None:
            raise RuntimeError("NATIVE_DO requires .WHILE(condition) before use")

        flat_cond, _ = _classify_body(self._condition)
        body, is_single = _classify_body(self._body)

        if is_single:
            return NodeCompose(
                body,
                NativeDoWhileNode(
                    condi_offset=1,
                    loop_pos=0,
                    exit_pos=3,
                ),
                flat_cond,
                NOP,
            )

        # Bubble body: [0]=enter, [1]=flat_bubble, [2]=do_while, [3]=cond, [4]=NOP
        assert isinstance(body, NodeCompose)
        return NodeCompose(
            NativeBubbleEnterNode(body_pos=1),
            NodeCompose(*body._graph),
            NativeDoWhileNode(
                condi_offset=1,
                loop_pos=0,
                exit_pos=4,
            ),
            flat_cond,
            NOP,
        )


def NATIVE_DO(body: BaseNode | NodeCompose | SelfCompileInstruction) -> NativeDoClause:
    """Create a native fast-path DO-WHILE loop.

    Args:
        body: Loop body — single ``BaseNode`` or a composition.

    Returns:
        ``NativeDoClause`` — call ``.WHILE(condition)`` to set the condition.
    """
    return NativeDoClause(body)
