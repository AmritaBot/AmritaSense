from typing import NoReturn

from amrita_sense.exceptions import InterruptKeepContext, InterruptNotice
from amrita_sense.node.core import Node as _Node

from ..node.wrapper import Node as _node_fun


@_node_fun(wrap_to_async=False, address_able=True)
def _no_operation() -> None:
    """No-operation workflow node.

    This node performs no action when executed and simply continues to the next
    node in the workflow. It is commonly used as a placeholder or target for
    jump operations in control flow constructs like IF-ELSE statements.
    """
    pass


@_node_fun(wrap_to_async=False, address_able=False)
def _reset_operation() -> NoReturn:
    """Reset workflow execution node.

    This node immediately terminates workflow execution by raising an
    InterruptNotice exception.  The interpreter catches it and calls
    `WorkflowInterpreter.reset()`, discarding the pointer, return-address stack,
    context stack, if-flag and panic state.  It cannot be referenced by address
    since it has address_able=False.

    Raises:
        InterruptNotice: Always raised to terminate workflow execution.
    """
    raise InterruptNotice("Reset Node")


@_node_fun(wrap_to_async=False, address_able=True)
def _suspend_operation() -> NoReturn:
    """Suspend workflow execution node while keeping context.

    This node immediately terminates workflow execution by raising
    InterruptKeepContext, a subclass of InterruptNotice that the interpreter
    deliberately does **not** reset on — so the interpreter state survives and
    the workflow can be resumed later.  Being address_able, it can also be
    reached by a jump.

    Raises:
        InterruptKeepContext: Always raised to terminate workflow execution.
    """
    raise InterruptKeepContext("Suspend Node with context retention")


NOP: _Node[None] = _no_operation
"""Constant representing a no-operation node instance. Usually used as a sentinel in control flow constructs."""
#  Module-level singletons: annotated on the instance, since all three share one class
NOP.__sdb_dis__ = "NOP"
NOP.__sdb_cmt__ = "no operation"

RESET: _Node[NoReturn] = _reset_operation
"""Constant representing a node that terminates the workflow and discards interpreter state."""
RESET.__sdb_dis__ = "RESET"
RESET.__sdb_cmt__ = "reset interpreter state"

SUSPEND: _Node[NoReturn] = _suspend_operation
"""Constant representing a node that terminates the workflow but keeps interpreter state, so it can be resumed."""
SUSPEND.__sdb_dis__ = "SUSPEND"
SUSPEND.__sdb_cmt__ = "suspend, keep context"

#  Deprecated aliases (renamed in 1.0.0); silent, since PEP 702 has no marker for variables.
INTERRUPT: _Node[NoReturn] = RESET
INTERRUPT_KEEP_CTX: _Node[NoReturn] = SUSPEND
