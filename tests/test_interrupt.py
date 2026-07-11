"""Tests for interrupt.py — PUSH_CONTEXT, POP_CONTEXT, INTERRUPT_INTO, INTERRUPT_RET."""

from typing import TYPE_CHECKING

import pytest

from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node
from amrita_sense.exceptions import IllegalState, InterruptNotice
from amrita_sense.instructions import GOTO
from amrita_sense.instructions.interrupt import (
    INTERRUPT_INTO,
    INTERRUPT_RET,
    POP_CONTEXT,
    PUSH_CONTEXT,
)
from amrita_sense.node.core import NodeComposeRendered
from amrita_sense.runtime.types import InterpreterContext
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector, Stack


class _FakeGraph:
    def __init__(self, alias_map):
        self.alias2vector_map = alias_map


class _FakeInterpreter:
    def __init__(self, alias_map=None, ptr=None):
        self._graph = _FakeGraph(alias_map or {})
        self._pointer = PointerVector(ptr or [0])
        self.context_stack: Stack[InterpreterContext] = Stack()
        self._ret_addr_stack: Stack[PointerVector] = Stack()
        self._exc_ignored: tuple[type[BaseException], ...] = (InterruptNotice,)
        self.if_flag: bool = False
        self._jump_marked: bool = False
        self._panic_exc: Exception | None = None
        self._ava_args: tuple = ()
        self._ava_kwargs: dict = {}

    def get_graph(self):
        return self._graph

    def find_addr_alias(self, a):
        return self._graph.alias2vector_map[a]

    def jump_to(self, a):
        self._pointer.far_to(a)
        self._jump_marked = True

    def dump_interpreter(self, exclude_deps=True, exclude_stack=True):
        return InterpreterContext(
            ptr=self._pointer.copy(),
            exception_ignored=self._exc_ignored,
            s_args=None if exclude_deps else self._ava_args,
            s_kwargs=None if exclude_deps else self._ava_kwargs,
            extra={},
            stack=None if exclude_stack else self._ret_addr_stack,
            exception=self._panic_exc,
        )

    def rebase_context(self, c):
        self._pointer.far_to(c.ptr.base_addr)
        self._exc_ignored = c.exception_ignored
        if c.s_args is not None and c.s_kwargs is not None:
            self._ava_args, self._ava_kwargs = c.s_args, c.s_kwargs
        self._ret_addr_stack = c.stack or self._ret_addr_stack
        self._panic_exc = c.exception

if not TYPE_CHECKING:

    class _FakeRendered:
        """Minimal NodeComposeRendered-like object that exposes .calc.resolve_alias()."""

        _alias_map: dict = {}  # noqa: RUF012

        def __init__(self, alias_map: dict):
            # Store on the class so the nested calc staticmethod can reach it
            _FakeRendered._alias_map = alias_map

        class calc:
            """Fake AddressCalculator with resolve_alias."""

            @staticmethod
            def resolve_alias(alias: str) -> list[int]:
                return _FakeRendered._alias_map[alias].copy()
else:

    class _FakeRendered(NodeComposeRendered):
        def __init__(*args, **kwargs): ...

# ---- node type ----


def test_push_context_returns_node():
    n = PUSH_CONTEXT("t", exclude_deps=False)
    assert n.tag == "__PUSH_CONTEXT__"
    assert n.wrap_to_async is False


def test_push_context_with_list():
    assert PUSH_CONTEXT([3, 1], exclude_stack=True).tag == "__PUSH_CONTEXT__"


def test_pop_context_returns_node():
    n = POP_CONTEXT()
    assert n.tag == "__POP_CONTEXT__"
    assert n.wrap_to_async is False


def test_interrupt_into_returns_node():
    assert INTERRUPT_INTO("t", "r").tag == "__INTERRUPT_INTO__"


def test_interrupt_into_with_list():
    assert INTERRUPT_INTO([1, 2], [3, 4], if_state=True).tag == "__INTERRUPT_INTO__"


def test_interrupt_ret_returns_node():
    n = INTERRUPT_RET()
    assert n.tag == "__INTERRUPT_RET__"
    assert n.wrap_to_async is False


# ---- PUSH_CONTEXT (push + jump) ----


def test_push_context_jumps():
    pc = _FakeInterpreter({"sub": [5, 0]}, [2, 3])
    n = PUSH_CONTEXT("sub")
    n._post_compile(_FakeRendered({"sub": [5, 0]}))
    n(pc)
    assert len(pc.context_stack) == 1
    assert pc.context_stack.stack[0].ptr.base_addr == [2, 3]
    assert pc._pointer.base_addr == [5, 0]
    assert pc._jump_marked


def test_push_context_list_target():
    pc = _FakeInterpreter(ptr=[0, 0])
    n = PUSH_CONTEXT([7, 2])
    n._post_compile(_FakeRendered({}))
    n(pc)
    assert pc.context_stack.stack[0].ptr.base_addr == [0, 0]
    assert pc._pointer.base_addr == [7, 2]


def test_push_context_exclude_deps():
    pc = _FakeInterpreter({"sub": [1]}, [0])
    pc._ava_args = (42,)
    pc._ava_kwargs = {"g": "hi"}
    n = PUSH_CONTEXT("sub", exclude_deps=False)
    n._post_compile(_FakeRendered({"sub": [1]}))
    n(pc)
    c = pc.context_stack.stack[0]
    assert c.s_args == (42,)
    assert c.s_kwargs == {"g": "hi"}


def test_push_context_exclude_stack():
    pc = _FakeInterpreter({"sub": [1]}, [0])
    pc._ret_addr_stack.push(PointerVector([9]))
    n = PUSH_CONTEXT("sub", exclude_stack=False)
    n._post_compile(_FakeRendered({"sub": [1]}))
    n(pc)
    assert pc.context_stack.stack[0].stack is not None
    assert pc.context_stack.stack[0].stack.stack[-1].base_addr == [9]


def test_push_context_multiple():
    pc = _FakeInterpreter({"s1": [1], "s2": [2]}, [0])
    n1 = PUSH_CONTEXT("s1")
    n1._post_compile(_FakeRendered({"s1": [1]}))
    n1(pc)
    pc._pointer.far_to([1])
    pc._jump_marked = False
    n2 = PUSH_CONTEXT("s2")
    n2._post_compile(_FakeRendered({"s2": [2]}))
    n2(pc)
    assert pc.context_stack.stack[0].ptr.base_addr == [0]
    assert pc.context_stack.stack[1].ptr.base_addr == [1]
    assert pc._pointer.base_addr == [2]


# ---- POP_CONTEXT ----


def test_pop_context_returns():
    pc = _FakeInterpreter({"s": [99]}, [2, 8])
    n = PUSH_CONTEXT("s")
    n._post_compile(_FakeRendered({"s": [99]}))
    n(pc)
    r = POP_CONTEXT()(pc)
    assert isinstance(r, InterpreterContext)
    assert r.ptr.base_addr == [2, 8]
    assert len(pc.context_stack) == 0


def test_pop_context_lifo():
    pc = _FakeInterpreter({"a": [10], "b": [20]}, [0])
    n1 = PUSH_CONTEXT("a")
    n1._post_compile(_FakeRendered({"a": [10]}))
    n1(pc)
    pc._pointer.far_to([10])
    pc._jump_marked = False
    n2 = PUSH_CONTEXT("b")
    n2._post_compile(_FakeRendered({"b": [20]}))
    n2(pc)
    c2 = POP_CONTEXT()(pc)
    c1 = POP_CONTEXT()(pc)
    assert c2.ptr.base_addr == [10]
    assert c1.ptr.base_addr == [0]


# ---- INTERRUPT_INTO (jump_to + ret_to) ----


def test_interrupt_into_saves_and_jumps():
    pc = _FakeInterpreter({"h": [5, 0], "r": [99]}, [0, 0])
    n = INTERRUPT_INTO("h", "r")
    n._post_compile(_FakeRendered({"h": [5, 0], "r": [99]}))
    n(pc)
    assert len(pc.context_stack) == 1
    assert pc.context_stack.stack[0].ptr.base_addr == [99]
    assert pc._pointer.base_addr == [5, 0]


def test_interrupt_into_sets_if_flag():
    pc = _FakeInterpreter({"h": [1], "r": [2]}, [0])
    n = INTERRUPT_INTO("h", "r", if_state=True)
    n._post_compile(_FakeRendered({"h": [1], "r": [2]}))
    n(pc)
    assert pc.if_flag is True


def test_interrupt_into_default_if_flag():
    pc = _FakeInterpreter({"h": [1], "r": [2]}, [0])
    n = INTERRUPT_INTO("h", "r")
    n._post_compile(_FakeRendered({"h": [1], "r": [2]}))
    n(pc)
    assert pc.if_flag is False


def test_interrupt_into_list_addrs():
    pc = _FakeInterpreter(ptr=[0])
    n = INTERRUPT_INTO([3, 7], [9, 2])
    n._post_compile(_FakeRendered({}))
    n(pc)
    assert pc._pointer.base_addr == [3, 7]
    assert pc.context_stack.stack[0].ptr.base_addr == [9, 2]


def test_interrupt_into_raises_when_if_flag_true():
    pc = _FakeInterpreter({"h": [1], "r": [2]}, [0])
    pc.if_flag = True
    with pytest.raises(IllegalState, match="Interrupt into is not allowed"):
        INTERRUPT_INTO("h", "r")(pc)
    assert len(pc.context_stack) == 0


# ---- INTERRUPT_RET ----


def test_interrupt_ret_restores():
    pc = _FakeInterpreter({"h": [2, 0], "r": [99]}, [0, 0])
    n = INTERRUPT_INTO("h", "r")
    n._post_compile(_FakeRendered({"h": [2, 0], "r": [99]}))
    n(pc)
    pc._pointer.far_to([2, 0])
    pc.if_flag = True
    INTERRUPT_RET()(pc)
    assert pc._pointer.base_addr == [99]
    assert pc.if_flag is False
    assert len(pc.context_stack) == 0


def test_interrupt_ret_clears_if_flag():
    pc = _FakeInterpreter({"h": [1], "r": [5]}, [0])
    n = INTERRUPT_INTO("h", "r", if_state=True)
    n._post_compile(_FakeRendered({"h": [1], "r": [5]}))
    n(pc)
    INTERRUPT_RET()(pc)
    assert pc.if_flag is False


# ---- end-to-end ----


@pytest.mark.asyncio
async def test_push_context_e2e():
    log = []

    @Node()
    async def main():
        log.append("main")

    @Node()
    async def sub():
        log.append("sub")

    @Node()
    async def back():
        log.append("back")

    c = (
        main
        >> PUSH_CONTEXT("sub_entry")
        >> back
        >> GOTO("done")
        >> ALIAS(sub, "sub_entry")
        >> INTERRUPT_RET()
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(c.render()).run()
    assert log == ["main", "sub", "back"]


@pytest.mark.asyncio
async def test_interrupt_into_e2e():
    II = INTERRUPT_INTO
    IR = INTERRUPT_RET
    log = []

    @Node()
    async def m():
        log.append("m")

    @Node()
    async def h():
        log.append("h")

    @Node()
    async def b():
        log.append("b")

    blk = ARCHIVED_NODES(ALIAS(h, "ih"), IR())
    c = (
        m
        >> II("ih", "back")  # jump to ih, save ret_to="back"
        >> ALIAS(NOP, "back")  # resumed here (NOP) after INTERRUPT_RET
        >> b  # then b executes
        >> GOTO("done")
        >> blk
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(c.render()).run()
    assert log == ["m", "h", "b"]


@pytest.mark.asyncio
async def test_push_context_skips():
    calls = []

    @Node()
    async def a():
        calls.append("a")

    @Node()
    async def b():
        calls.append("b")

    @Node()
    async def c():
        calls.append("c")

    comp = a >> PUSH_CONTEXT("skip_b") >> b >> ALIAS(c, "skip_b") >> ALIAS(NOP, "done")
    await WorkflowInterpreter(comp.render()).run()
    assert calls == ["a", "c"]
