import pytest

from amrita_sense import Node as NodeDecorator
from amrita_sense.exceptions import AliasNotFoundError
from amrita_sense.instructions.alias import AliasNode
from amrita_sense.instructions.jump import GOTO
from amrita_sense.node.core import NodeCompose


def test_goto_with_list_address_sets_node_addr():
    @NodeDecorator()
    def n():
        return "x"

    # Build a graph deep enough so address [1, 2, 3] exists
    workflow = NodeCompose(
        n,
        NodeCompose(n, n, NodeCompose(n, n, n, n)),
    )
    rendered = workflow.render()

    j = GOTO([1, 2, 3])
    j._post_compile(rendered)
    assert j._node_addr == [1, 2, 3]


def test_goto_with_alias_resolves_address():
    @NodeDecorator()
    def target():
        return "target"

    alias_node = AliasNode(target, "target_alias")
    workflow = NodeCompose(alias_node)
    rendered = workflow.render()

    j = GOTO("target_alias")
    j._post_compile(rendered)
    assert j._node_addr == rendered.alias2vector_map["target_alias"]


def test_goto_with_unknown_alias_raises():
    @NodeDecorator()
    def n():
        return "x"

    rendered = NodeCompose(n).render()

    j = GOTO("nope")
    with pytest.raises(AliasNotFoundError):
        j._post_compile(rendered)
