from amrita_sense.instructions.if_clause import IF
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.wrapper import Node as NodeDecorator


def _make_node(ret):
    @NodeDecorator()
    def fn():
        return ret

    return fn


def test_if_simple_extract():
    """Simple IF clause should render a 3-chunk plus NOP composition."""
    cond = _make_node(True)
    action = _make_node("ok")

    if_clause = IF(cond, action)
    extracted = if_clause.extract()

    # Base IF chunk: ConditionJumpNode, condition, do, then NOP
    assert len(extracted._graph) == 4
    assert extracted._graph[-1] is NOP


def test_if_with_elif_else_extract():
    """IF with ELIF chains and ELSE should produce expanded chunks and final NOP."""
    cond1 = _make_node(False)
    do1 = _make_node(1)
    cond2 = _make_node(False)
    do2 = _make_node(2)
    else_do = _make_node(3)

    composed = IF(cond1, do1).ELIF(cond2, do2).ELSE(else_do)
    extracted = composed.extract()

    # There should be more than the base 4 elements and end with NOP
    assert len(extracted._graph) >= 7
    assert extracted._graph[-1] is NOP
