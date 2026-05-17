from typing import cast

import pytest

from amrita_sense.instructions.jump import JumpNode
from amrita_sense.instructions.loop.do_while import DO
from amrita_sense.instructions.loop.while_clause import WHILE
from amrita_sense.node.core import Node as NodeType
from amrita_sense.node.wrapper import Node as NodeDecorator


def _make_node(ret):
    @NodeDecorator()
    def fn():
        return ret

    return fn


def test_do_while_extract_structure():
    action = _make_node("do")
    condi = _make_node(True)

    clause = DO(action).WHILE(condi)
    extracted = clause.extract()

    # DONode, action, DowhileNode, condition, NOP
    assert len(extracted._graph) == 5


def test_while_action_jumpnode_raises():
    cond = _make_node(True)
    w = WHILE(cond)

    # Use a JumpNode as action to trigger RuntimeError during extract()
    action = JumpNode([0])
    w.ACTION(cast(NodeType, action))
    with pytest.raises(RuntimeError):
        w.extract()


def test_while_extract_normal():
    cond = _make_node(False)
    action = _make_node("act")
    w = WHILE(cond).ACTION(action)
    extracted = w.extract()

    # WhileNode, condition, action, CheckUpNode, NOP
    assert len(extracted._graph) == 5
