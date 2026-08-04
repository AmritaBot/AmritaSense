"""Native DO-WHILE — fast-path loop.

Usage::

    NATIVE_DO(body).WHILE(condition)

``body`` accepts:

* ``BaseNode`` — single node, ``call_offset`` + ``jump_near`` loop.
* ``NodeCompose`` | ``SelfCompileInstruction`` — body compose finishes
  naturally; ``advance_pointer`` steps to ``NativeDoWhileNode`` which
  ``jump_near``'s back to re-enter the body bubble.
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

    **Single-node layout:** ``[0]`` body, ``[1]`` NativeDoWhileNode, ``[2]`` cond,
    ``[3]`` NOP exit.

    **Bubble layout:** ``[0]`` enter, ``[1]`` body, ``[2]`` NOP landing,
    ``[3]`` NativeDoWhileNode, ``[4]`` cond, ``[5]`` NOP exit.

    Body finishes naturally -> advance to ``[2]`` NOP -> ``[3]`` do-while
    re-checks the condition.  Enter pushes ``[2]`` (= do-while - 1) so a
    user-placed ``RET_FAR`` (CONTINUE) inside the body rebases to ``[2]``
    and advances to ``[3]``, re-evaluating the condition.
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

        # Bubble: [0]=enter(PUSH→[2] for BREAK_LOOP/RET_FAR), [1]=body,
        # [2]=NOP landing, [3]=do_while, [4]=cond, [5]=NOP exit.
        assert isinstance(body, NodeCompose)
        return NodeCompose(
            NativeBubbleEnterNode(body_pos=1, ret_pos=2),
            body,
            NOP,
            NativeDoWhileNode(
                condi_offset=1,
                loop_pos=0,
                exit_pos=5,
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
