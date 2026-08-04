"""BREAK_LOOP — jump to the sentinel NOP of the current native loop.

Usage::

    from amrita_sense.instructions.native import BREAK_LOOP

    comp = NATIVE_WHILE(cond).ACTION(NodeCompose(step1, BREAK_LOOP(), step2))
    comp = NATIVE_DO(NodeCompose(step1, BREAK_LOOP(), step2)).WHILE(cond)

``BREAK_LOOP()`` is a factory that returns a node which, at runtime, pops
``_ret_addr_stack`` and ``jump_far_ptr``'s to the sentinel NOP of the
enclosing native loop bubble, cleanly exiting that loop level.

The target is configured at compile-time by the enclosing loop's
``extract()`` via the DFS scanner ``_configure_loop_control_nodes()``.
"""

from __future__ import annotations

import inspect

from amrita_sense.instructions.enum import BuiltinTags
from amrita_sense.instructions.native._core import _LoopControlNode


class _BreakLoopNode(_LoopControlNode):
    """Pop stack and jump to the enclosing bubble's sentinel NOP."""

    __slots__ = ()

    def __init__(self) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        super().__init__()
        self._init(
            self.__call__,
            tag=BuiltinTags.BREAK_LOOP,
            wrap_to_async=False,
            address_able=True,
            frame=frame,
        )


def BREAK_LOOP() -> _BreakLoopNode:
    """Create a BREAK_LOOP node.

    At compile-time, the enclosing loop's ``extract()`` configures the
    target to the bubble's sentinel NOP.  At runtime the node pops
    ``_ret_addr_stack`` and ``jump_far_ptr``'s to exit the loop.
    """
    return _BreakLoopNode()
