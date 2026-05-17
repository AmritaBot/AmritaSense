from typing import NoReturn

from amrita_sense.exceptions import InterruptNotice
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
def _interrput_operation() -> NoReturn:
    """Interrupt workflow execution node.

    This node immediately terminates workflow execution by raising an
    InterruptNotice exception. It is used to implement external interruption
    mechanisms and cannot be referenced by address since it has address_able=False.

    Raises:
        InterruptNotice: Always raised to terminate workflow execution.
    """
    raise InterruptNotice("Interrupt Node")


NOP: _Node[None] = _no_operation
"""Constant representing a no-operation node instance."""

INTERRUPT: _Node[NoReturn] = _interrput_operation
"""Constant representing an interrupt node instance."""
