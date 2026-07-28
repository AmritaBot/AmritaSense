"""Native IF / ELIF / ELSE — jump+RET_FAR fast-path branching.

Usage::

    NATIVE_IF(cond, body)
    NATIVE_IF(cond, body).ELIF(elif_cond, elif_body)
    NATIVE_IF(cond, body).ELIF(elif_cond, elif_body).ELSE(else_body)

``body`` / ``elif_body`` / ``else_body`` accept:

* ``BaseNode`` — single node, executed via ``call_offset`` (no overhead vs vanilla).
* ``NodeCompose`` | ``SelfCompileInstruction`` — wrapped into a **bubble**
  with automatic ``RET_FAR`` (IF/ELIF) or ``NativeBubbleEnterNode`` (ELSE).
"""

from __future__ import annotations

from typing_extensions import Self, override

from amrita_sense.instructions.native._core import (
    NativeBubbleEnterNode,
    NativeIfJumpNode,
    _classify_body,
)
from amrita_sense.instructions.ret2 import RET_FAR
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction


class _ELIFClause:
    """Internal holder for a single ELIF (condition, body) pair."""

    __slots__ = ("body", "condition")

    def __init__(
        self,
        condition: Node[bool],
        body: BaseNode | NodeCompose | SelfCompileInstruction,
    ) -> None:
        self.condition = condition
        self.body = body


class NativeIfClause(SelfCompileInstruction):
    """Fast-path IF with optional .ELIF / .ELSE chains."""

    _condition: Node[bool]
    _body: BaseNode | NodeCompose | SelfCompileInstruction
    _elifs: list[_ELIFClause]
    _else_body: BaseNode | NodeCompose | SelfCompileInstruction | None

    def __init__(
        self,
        condition: Node[bool],
        body: BaseNode | NodeCompose | SelfCompileInstruction,
    ) -> None:
        self._condition = condition
        self._body = body
        self._elifs = []
        self._else_body = None

    ### Fluent API ###

    def ELIF(
        self,
        condition: Node[bool],
        body: BaseNode | NodeCompose | SelfCompileInstruction,
    ) -> Self:
        """Append an ELIF branch."""
        self._elifs.append(_ELIFClause(condition, body))
        return self

    def ELSE(
        self,
        body: BaseNode | NodeCompose | SelfCompileInstruction,
    ) -> Self:
        """Append an ELSE branch."""
        self._else_body = body
        return self

    ### Compile ###

    @override
    def extract(self) -> NodeCompose:
        """Build the flat native IF layout.

        3 slots per IF/ELIF branch (condi_offset=1, do_offset=2) + optional
        else slot + final NOP merge.  All true branches RET_FAR-jump to the
        merge point; false targets chain to the next ELIF, else, or merge.
        """
        ### helpers ###

        def _wrap_if_body(
            payload: BaseNode | NodeCompose | SelfCompileInstruction,
        ) -> tuple[BaseNode | NodeCompose, bool]:
            """IF/ELIF body: single node OR flat NodeCompose ending with RET_FAR."""
            body, is_single = _classify_body(payload)
            if is_single:
                return body, True
            assert isinstance(body, NodeCompose)
            return NodeCompose(*body._graph, RET_FAR()), False

        def _wrap_else(
            payload: BaseNode | NodeCompose | SelfCompileInstruction,
        ) -> tuple[BaseNode | NodeCompose, bool]:
            """ELSE body: single node OR NodeCompose (no RET_FAR, natural flow)."""
            return _classify_body(payload)

        ### build all pieces ###

        # Main IF
        if_body, if_single = _wrap_if_body(self._body)
        if_cond, _ = _classify_body(self._condition)

        # ELIFs
        elif_specs: list[
            tuple[BaseNode | NodeCompose, BaseNode | NodeCompose, bool]
        ] = []  # (cond, body_slot, is_single)
        for elif_ in self._elifs:
            ec, _ = _classify_body(elif_.condition)
            eb, es = _wrap_if_body(elif_.body)
            elif_specs.append((ec, eb, es))

        # ELSE
        has_else = self._else_body is not None
        if has_else:
            else_body, else_is_single = _wrap_else(self._else_body)  # type: ignore[arg-type]
        else:
            else_body, else_is_single = NOP, True

        n_elif = len(elif_specs)

        # merge position (0-indexed, before building nodes)
        # IF(3) + ELIFs(3*n) + else_slot_width + NOP(1)
        else_slot_width = 1 if else_is_single else 2  # single node or [enter, bubble]
        merge_pos = 3 + 3 * n_elif + else_slot_width

        nodes: list[BaseNode | NodeCompose] = []

        ### Main IF chunk (positions 0-2) ###
        false_next = 3 if (n_elif > 0 or has_else) else merge_pos
        nodes.append(
            NativeIfJumpNode(
                condi_offset=1,
                do_offset=2,
                do_pos=2,
                ret_pos=merge_pos,
                false_pos=false_next,
                is_single=if_single,
            )
        )
        nodes.append(if_cond)
        nodes.append(if_body)

        ### ELIF chunks ###
        for i, (ec, eb, es) in enumerate(elif_specs):
            base = 3 + 3 * i  # chunk start
            # false: next ELIF, else, or merge
            if i + 1 < n_elif or has_else:
                false_next = base + 3
            else:
                false_next = merge_pos
            nodes.append(
                NativeIfJumpNode(
                    condi_offset=1,
                    do_offset=2,
                    do_pos=base + 2,
                    ret_pos=merge_pos,
                    false_pos=false_next,
                    is_single=es,
                )
            )
            nodes.append(ec)
            nodes.append(eb)

        # --- ELSE slot ---
        if has_else and not else_is_single:
            assert isinstance(else_body, NodeCompose)
            else_pos = len(nodes)
            nodes.append(NativeBubbleEnterNode(else_pos + 1))
            nodes.append(NodeCompose(*else_body._graph))
        else:
            nodes.append(else_body)

        ### Merge ###
        nodes.append(NOP)

        return NodeCompose(*nodes)


def NATIVE_IF(
    condition: Node[bool],
    body: BaseNode | NodeCompose | SelfCompileInstruction,
) -> NativeIfClause:
    """Create a native fast-path IF clause.

    Args:
        condition: Boolean condition node (called via ``call_offset``).
        body: Branch body — single ``BaseNode`` or a composition
            (wrapped as a bubble with automatic ``RET_FAR``).

    Returns:
        ``NativeIfClause`` with fluent ``.ELIF`` / ``.ELSE`` chain support.
    """
    return NativeIfClause(condition, body)
