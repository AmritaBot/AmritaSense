import pytest

from amrita_sense.instructions.jump import GOTO


class _FakeGraph:
    def __init__(self, alias_map):
        self.alias2vector_map = alias_map


class _FakePointer:
    def __init__(self, alias_map=None):
        self._graph = _FakeGraph(alias_map or {})

    def get_graph(self):
        return self._graph

    def find_addr_alias(self, alias):
        return self._graph.alias2vector_map[alias]

    def find_addr(self, idata):
        # no-op for testing
        return idata

    def jump_to(self, addr):
        return addr


def test_goto_with_list_address_sets_node_addr():
    j = GOTO([1, 2, 3])
    ptr = _FakePointer()
    # Pre-check with list should set _node_addr to the list
    j._pre_check(ptr)
    assert j._node_addr == [1, 2, 3]


def test_goto_with_alias_resolves_address():
    alias = "target_alias"
    addr = [5]
    j = GOTO(alias)
    ptr = _FakePointer({alias: addr})
    j._pre_check(ptr)
    assert j._node_addr == addr


def test_goto_with_unknown_alias_raises():
    j = GOTO("nope")
    ptr = _FakePointer({})
    with pytest.raises(RuntimeError):
        j._pre_check(ptr)
