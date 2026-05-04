from amrita_sense.node.core import BaseNode, Node

from .alias import AliasNode
from .if_clause import IFClause
from .jump import GOTO
from .loop.do_while import DO
from .loop.while_clause import WHILE
from .workfl_ctrl import INTERRUPT, NOP


def IF(condition: Node[bool], do: BaseNode) -> IFClause:
    """If condition

    Args:
        condition (Node): Condition node
        do (Node): Payload

    Returns:
        IFClause: If Clause (Must follow with ELSE)

    Examples:
        ```python
        IF(CONDITION,PAYLOAD).ELSE(ELSE_PAYLOAD)
        IF(CONDITION,PAYLOAD).ELIF(ELIF_CONDITION,ELIF_PAYLOAD).ELSE(ELSE_PAYLOAD)
        ```
    """
    return IFClause(condition, do)


__all__ = (
    "DO",
    "GOTO",
    "IF",
    "INTERRUPT",
    "NOP",
    "WHILE",
    "AliasNode",
)
