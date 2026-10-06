"""`NodeComposeRendered` sequence protocol: `__len__`, `__bool__`, `__getitem__`."""

import pytest

from amrita_sense.exceptions import NullPointerException
from amrita_sense.node.core import NodeCompose, NodeComposeRendered
from amrita_sense.node.wrapper import Node as NodeDecorator


class TestRenderedIndexing:
    """The rendered graph is addressed by `__getitem__`, never iterated."""

    @staticmethod
    def _rendered():
        @NodeDecorator()
        def simple_node():
            return "hello"

        return NodeCompose(simple_node).render()

    def test_in_range_index_returns_the_node(self):
        rendered = self._rendered()
        assert len(rendered) == 1
        assert rendered[0] is not None

    def test_past_the_end_raises_null_pointer(self):
        with pytest.raises(NullPointerException):
            self._rendered()[1]

    def test_before_the_start_raises_null_pointer(self):
        """Out of range is out of range, in either direction.

        The bounds check used to be `key >= len(self._graph)`, so a negative
        index fell through to the raw list lookup and surfaced as `IndexError`.
        The contract promises `NullPointerException` for out-of-range indexing,
        and the debugger's disassembler relies on that being uniform.
        """
        with pytest.raises(NullPointerException):
            self._rendered()[-2]

    def test_unbuilt_graph_is_falsy(self):
        rendered = NodeComposeRendered(NodeCompose())
        assert not rendered
        # `__len__` returns -1 as a "not built" sentinel, which the `len()`
        # builtin rejects (`ValueError: __len__() should return >= 0`); the
        # sentinel is only observable through a direct call.
        assert rendered.__len__() == -1
