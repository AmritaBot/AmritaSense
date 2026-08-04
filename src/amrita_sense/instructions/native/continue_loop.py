"""CONTINUE — jump to loop head for next iteration.

Usage::

    from amrita_sense.instructions.native import CONTINUE

    comp = NATIVE_WHILE(cond).ACTION(NodeCompose(
        step1,
        CONTINUE(),    # skip step2, go to next iteration
        step2,
    ))

``CONTINUE()`` is a factory that returns a node which, at runtime, pops
the ``_ret_addr_stack`` and ``jump_far_ptr``'s to the loop head.  The
target position is configured at compile-time by the enclosing native
loop's ``extract()`` via ``_configure_loop_control_nodes()``.

Unlike ``RET_FAR`` (which uses ``rebase_ptr`` and relies on
``advance_pointer``), ``CONTINUE`` uses ``jump_far_ptr`` — a direct
jump that sets ``_jump_marked`` so the main loop executes the target
immediately without an intervening advance step.
"""

from __future__ import annotations

import inspect

from amrita_sense.instructions.enum import BuiltinTags
from amrita_sense.instructions.native._core import _LoopControlNode


class _ContinueNode(_LoopControlNode):
    """Pop stack and jump to the loop head (next iteration)."""

    __slots__ = ()

    def __init__(self) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        super().__init__()
        self._init(
            self.__call__,
            tag=BuiltinTags.CONTINUE,
            wrap_to_async=False,
            address_able=True,
            frame=frame,
        )


def CONTINUE() -> _ContinueNode:
    """Create a CONTINUE node.

    At compile-time, the enclosing loop's ``extract()`` configures the
    target position so that ``CONTINUE`` jumps back to the loop head.
    """
    return _ContinueNode()
