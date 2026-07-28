"""BREAK_LOOP — pop stack and jump to the sentinel NOP of the current bubble.

Usage::

    from amrita_sense.instructions.native import BREAK_LOOP

    comp = NATIVE_WHILE(cond).ACTION(NodeCompose(step1, BREAK_LOOP, step2))
    comp = NATIVE_DO(NodeCompose(step1, BREAK_LOOP, step2)).WHILE(cond)

``BREAK_LOOP`` only makes sense inside a native loop **bubble** body.
It pops the return address that was pushed by the loop's enter node and
jumps to the last sentinel (NOP) of the parent bubble, cleanly exiting
the loop.
"""

from __future__ import annotations

import inspect

from amrita_sense.node.core import BaseNode, NodeComposeRendered
from amrita_sense.runtime.workflow import WorkflowInterpreter


class _BreakLoopNode(BaseNode):
    """Pop stack and jump to parent bubble's sentinel NOP."""

    __slots__ = ()

    def __init__(self) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        self._init(
            self.__call__,
            tag="__BREAK_LOOP__",
            wrap_to_async=False,
            address_able=True,
            frame=frame,
        )

    def __call__(self, pc: WorkflowInterpreter) -> None:
        addr: list[int] = list(pc._pointer.base_addr)
        if len(addr) < 2:
            raise RuntimeError(
                "BREAK_LOOP must be used inside a native loop bubble body, "
                f"got address {addr} (too shallow)"
            )

        # addr[:-2] is the coordinate of the *parent* bubble (the one
        # containing the loop structure).  We jump to its last sentinel
        # (NOP) to cleanly exit the loop.
        parent_addr: list[int] = addr[:-2]
        parent_bubble = pc.get_graph().calc.find_addr(parent_addr)
        if not isinstance(parent_bubble, NodeComposeRendered):
            raise RuntimeError(
                f"BREAK_LOOP: expected NodeComposeRendered at {parent_addr}, "
                f"got {type(parent_bubble).__name__}"
            )

        target: int = len(parent_bubble) - 1
        pc._ret_addr_stack.pop()
        pc.jump_far_ptr([*parent_addr, target])


BREAK_LOOP: _BreakLoopNode = _BreakLoopNode()
"""Break out of a native WHILE/DO bubble body.

Pops the return address pushed by the loop's enter node and jumps to the
last sentinel (NOP) of the parent bubble.
"""
