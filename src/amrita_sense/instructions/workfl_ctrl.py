from typing import NoReturn

from amrita_sense.exceptions import InterruptNotice
from amrita_sense.node.core import Node as _Node

from ..node.wrapper import Node as _node_fun


@_node_fun(wrap_to_async=False, address_able=True)
def _no_operation() -> None:
    pass


@_node_fun(wrap_to_async=False, address_able=False)
def _interrput_operation() -> NoReturn:
    raise InterruptNotice("Interrupt Node")


NOP: _Node[None] = _no_operation

INTERRUPT: _Node[NoReturn] = _interrput_operation
