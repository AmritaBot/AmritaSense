"""Enumeration of all built-in instruction tags.

Each member corresponds to the runtime `tag` attribute of a built-in
AmritaSense instruction node.  Tags fall into two categories:

**Explicit tags**
    Set directly via `@Node("...")` or `_init(..., tag="...")`.
    These are the stable, human-readable identifiers.

**Auto-generated tags** (:attr:`AUTO_PREFIX`)
    Produced by the `BaseNode._init` fallback `f"NodeSuspend::{func.__name__}"`
    when no explicit tag is supplied.  Multiple node types may share the same
    auto-generated tag (e.g. `NodeSuspend::__call__`), so these are primarily
    useful for debugging rather than unique identification.
"""

from enum import Enum

from typing_extensions import LiteralString


class BuiltinTags(str, Enum):
    """String-mixin enumeration of all built-in instruction tags."""

    #  Context stack / Interrupts
    PUSH_CONTEXT = "__PUSH_CONTEXT__"
    """Tag for :func:`~amrita_sense.instructions.interrupt.PUSH_CONTEXT`."""

    POP_CONTEXT = "__POP_CONTEXT__"
    """Tag for :func:`~amrita_sense.instructions.interrupt.POP_CONTEXT`."""

    INTERRUPT_INTO = "__INTERRUPT_INTO__"
    """Tag for :func:`~amrita_sense.instructions.interrupt.INTERRUPT_INTO`."""

    INTERRUPT_RET = "__INTERRUPT_RET__"
    """Tag for :func:`~amrita_sense.instructions.interrupt.INTERRUPT_RET`."""

    #  Return-address stack
    RET_FAR = "__RET_FAR__"
    """Tag for :func:`~amrita_sense.instructions.ret2.RET_FAR`."""

    PUSH_STACK = "__PUSH_STACK__"
    """Tag for :func:`~amrita_sense.instructions.ret2.PUSH_STACK`."""

    PUSH_AND_GOTO = "__PUSH_AND_GOTO__"
    """Tag for :func:`~amrita_sense.instructions.ret2.PUSH_AND_GOTO`."""

    #  Subprogram
    ARCHIVED_SEGMENT = "__ARCHIVED_SEGMENT__"
    """Tag for the internal jump node in :func:`~amrita_sense.instructions.subprogram.ARCHIVED_SEGMENT`."""

    #  Batch execution
    BATCH_CALLER = "__BATCH_CALLER__"
    """Tag for :func:`~amrita_sense.instructions.batch.BATCH_RUN`'s internal batch caller."""

    BATCH_RUN = "__BATCH_RUN__"
    """Tag for :func:`~amrita_sense.instructions.batch.BATCH_RUN` itself."""

    #  Native loop control
    BREAK_LOOP = "__BREAK_LOOP__"
    """Tag for :func:`~amrita_sense.instructions.native.break_loop.BREAK_LOOP`."""

    CONTINUE = "__CONTINUE__"
    """Tag for :func:`~amrita_sense.instructions.native.continue_loop.CONTINUE`."""

    #  Event system
    EVENT_TRIGGER_CALL = "EventTrigger::__call__"
    """Tag for the internal `EventTrigger` node in :func:`~amrita_sense.instructions.trigger_event.TRIGGER_EVENT`."""

    TRIGGER_CONSTRUCTOR = "TriggerInstruction::constructor"
    """Tag for the event-constructor node in :func:`~amrita_sense.instructions.trigger_event.TRIGGER_EVENT`."""

    #  Exception handling
    TRY_WORKER = "TryNode::worker"
    """Tag for the internal worker node in :class:`~amrita_sense.instructions.try_catch.Try`."""


AUTO_PREFIX: LiteralString = "NodeSuspend::"
"""Prefix for auto-generated tags."""

AUTO_TAGS: dict[LiteralString, str] = {
    "NOP": f"{AUTO_PREFIX}_no_operation",
    "INTERRUPT": f"{AUTO_PREFIX}_interrput_operation",
    "INTERRUPT_KEEP_CTX": f"{AUTO_PREFIX}_interrupt_keep_ctx",
    "GOTO": f"{AUTO_PREFIX}_jump",
    "IF_CONDJUMP": f"{AUTO_PREFIX}_do",
    "ELSE_WORKER": f"{AUTO_PREFIX}_else_worker",
    "DO_NODE": f"{AUTO_PREFIX}_do_worker",
    "DO_WHILE": f"{AUTO_PREFIX}_do_while_worker",
    "WHILE_NODE": f"{AUTO_PREFIX}_while_worker",
    "WHILE_CHECKUP": f"{AUTO_PREFIX}_while_checkup",
}

"""
Auto-generated tags for built-in instructions whose nodes pass `tag=None`.

These are produced by the `BaseNode._init` fallback and are shared
across many node types — they are **not** unique identifiers.

=============================== ============================================
Tag                             Instruction(s)
=============================== ============================================
`NodeSuspend::_no_operation`  :data:`~amrita_sense.instructions.workfl_ctrl.NOP`
`NodeSuspend::_interrput_operation` :data:`~amrita_sense.instructions.workfl_ctrl.INTERRUPT`
`NodeSuspend::_interrupt_keep_ctx`  :data:`~amrita_sense.instructions.workfl_ctrl.INTERRUPT_KEEP_CTX`
`NodeSuspend::_jump`          :func:`~amrita_sense.instructions.jump.GOTO` (JumpNode)
`NodeSuspend::__call__`       SubprogramJumpNode, CallNode, NativeIfJumpNode,
                                NativeWhileNode, NativeDoWhileNode,
                                NativeBubbleEnterNode, FuncBlock
`NodeSuspend::_do`            ConditionJumpNode (IF chain)
`NodeSuspend::_else_worker`   ELSE clause worker node
`NodeSuspend::_do_worker`     DONode
`NodeSuspend::_do_while_worker` DowhileNode
`NodeSuspend::_while_worker`  WhileNode
`NodeSuspend::_while_checkup` CheckUpNode
=============================== ============================================
"""

__all__ = [
    "AUTO_PREFIX",
    "AUTO_TAGS",
    "BuiltinTags",
]
