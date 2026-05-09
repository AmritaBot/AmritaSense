from amrita_sense.exceptions import InterruptNotice
from amrita_sense.node.core import Node as _Node

from ..node.wrapper import Node as _node_fun


@_node_fun(wrap_to_async=False, address_able=True)
def _no_operation():
    pass


@_node_fun(wrap_to_async=False, address_able=False)
def _interrput_operation():
    raise InterruptNotice("Interrupt Node")


NOP: _Node = _no_operation

INTERRUPT: _Node = _interrput_operation
