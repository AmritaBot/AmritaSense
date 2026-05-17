import pytest

from amrita_sense.instructions.try_catch import Try, TryNode
from amrita_sense.node.wrapper import Node as NodeDecorator


def _make_node(ret):
    @NodeDecorator()
    def fn():
        return ret

    return fn


def test_try_requires_catch_or_finally():
    """TryClause without catch or finally should raise on extract."""
    node = _make_node(1)
    tc = Try(node)
    with pytest.raises(TypeError):
        tc.extract()


def test_try_full_chain_extract():
    """Try with catch/then/finally should produce a NodeCompose with TryNode."""
    do_node = _make_node("do")
    catch_node = _make_node("catch")
    then_node = _make_node("then")
    fin_node = _make_node("fin")

    tc = Try(do_node).CATCH(Exception, catch_node).THEN(then_node).FINALLY(fin_node)
    extracted = tc.extract()

    # First element should be a TryNode instance
    assert isinstance(extracted._graph[0], TryNode)
    # Ensure the composed graph contains the provided nodes
    assert any(n is catch_node for n in extracted._graph)
    assert any(n is then_node for n in extracted._graph)
    assert any(n is fin_node for n in extracted._graph)
