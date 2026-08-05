"""Native WHILE — jump+CONTINUE fast-path loop.

Usage::

    NATIVE_WHILE(condition).ACTION(body)

``body`` is always wrapped as ``NodeCompose(body, CONTINUE())`` so that
the loop can iterate.  Single-node bodies are auto‑wrapped.
"""

from __future__ import annotations

from typing import cast

from typing_extensions import Self, override

from amrita_sense.instructions.native._core import (
    NativeWhileNode,
    _classify_body,
    _configure_loop_control_nodes,
)
from amrita_sense.instructions.native.continue_loop import CONTINUE
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction


class NativeWhileClause(SelfCompileInstruction):
    """Fast-path WHILE loop.

    Layout: ``[0]`` while_node, ``[1]`` cond, ``[2]`` body (+CONTINUE),
    ``[3]`` NOP exit.

    While-node pushes ``[0]``, ``jump_far_ptr`` into body.  The body's
    ``CONTINUE()`` pops and ``jump_far_ptr``'s back to ``[0]``.
    ``BREAK_LOOP()`` pops and jumps to ``[3]``.
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

        # All bodies end with CONTINUE — single nodes are auto‑wrapped.
        body_slot: NodeCompose = (
            NodeCompose(body, CONTINUE())
            if is_single
            else NodeCompose(*cast(NodeCompose, body)._graph, CONTINUE())
        )

        # DFS configure CONTINUE/BREAK_LOOP inside body_slot.
        _configure_loop_control_nodes(body_slot, continue_pos=0, break_pos=3)

        # Layout: [0]=while_node, [1]=cond, [2]=body_slot, [3]=NOP exit
        return NodeCompose(
            NativeWhileNode(
                condi_offset=1,
                body_pos=2,
                self_pos=0,
                exit_pos=3,
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
