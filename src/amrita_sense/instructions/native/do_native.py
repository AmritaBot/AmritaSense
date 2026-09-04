"""Native DO-WHILE — jump+CONTINUE fast-path loop.

Usage::

    NATIVE_DO(body).WHILE(condition)

``body`` is always wrapped as ``NodeCompose(body, CONTINUE())`` so that
the loop can iterate.  Single-node bodies are auto‑wrapped.
"""

from __future__ import annotations

from typing import cast

from typing_extensions import Self, override

from amrita_sense.instructions.native._core import (
    NativeBubbleEnterNode,
    NativeDoWhileNode,
    _classify_body,
    _configure_loop_control_nodes,
)
from amrita_sense.instructions.native.continue_loop import CONTINUE
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.abc_base import AbstractComposeOriginal
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction


class NativeDoClause(SelfCompileInstruction):
    """Fast-path DO-WHILE loop.

    Layout: ``[0]`` enter, ``[1]`` body (+CONTINUE), ``[2]`` do_while,
    ``[3]`` cond, ``[4]`` NOP exit.

    Enter pushes and ``jump_far_ptr``'s into body every iteration.
    ``CONTINUE()`` pops and jumps to ``[2]`` do_while to re‑check.
    ``BREAK_LOOP()`` pops and jumps to ``[4]`` NOP exit.
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
    def extract(self) -> AbstractComposeOriginal:
        if self._condition is None:
            raise RuntimeError("NATIVE_DO requires .WHILE(condition) before use")

        flat_cond, _ = _classify_body(self._condition)
        body, is_single = _classify_body(self._body)

        # All bodies end with CONTINUE — single nodes are auto‑wrapped.
        body_slot: NodeCompose = (
            NodeCompose(body, CONTINUE())
            if is_single
            else NodeCompose(*cast(NodeCompose, body)._graph, CONTINUE())
        )

        # DFS configure CONTINUE/BREAK_LOOP inside body_slot.
        _configure_loop_control_nodes(body_slot, continue_pos=2, break_pos=4)

        # Layout: [0]=enter, [1]=body_slot, [2]=do_while, [3]=cond, [4]=NOP
        return NodeCompose(
            NativeBubbleEnterNode(body_pos=1),
            body_slot,
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
