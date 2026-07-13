"""Tests for ret2.py — PUSH_STACK, RET_FAR, PUSH_AND_GOTO instructions."""

from typing import TYPE_CHECKING

import pytest

from amrita_sense.instructions.ret2 import PUSH_AND_GOTO, PUSH_STACK, RET_FAR
from amrita_sense.node.core import NodeComposeRendered
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector, Stack

# ---------------------------------------------------------------------------
# Fake rendered object for post_compile hooks (mirrors interrupt test pattern)
# ---------------------------------------------------------------------------

if not TYPE_CHECKING:

    class _FakeRendered:
        """Minimal NodeComposeRendered-like object that exposes .calc.resolve_alias()."""

        _alias_map: dict = {}  # noqa: RUF012

        def __init__(self, alias_map: dict):
            _FakeRendered._alias_map = alias_map

        class calc:
            """Fake AddressCalculator with resolve_alias."""

            @staticmethod
            def resolve_alias(alias: str) -> list[int]:
                return _FakeRendered._alias_map[alias].copy()
else:

    class _FakeRendered(NodeComposeRendered):
        def __init__(*args, **kwargs): ...


# ---------------------------------------------------------------------------
# Fake interpreter (minimal — no alias resolution needed at runtime)
# ---------------------------------------------------------------------------


class _FakeInterpreter:
    """Minimal fake to exercise ret2 instruction internals.

    Alias resolution is done at compile time via _post_compile, so the
    interpreter does NOT need find_addr_alias / get_graph."""

    def __init__(self) -> None:
        self._ret_addr_stack: Stack[PointerVector] = Stack()
        self._pointer = PointerVector()

    def jump_to(self, addr: list[int]) -> None:
        self._pointer.far_to(addr)

    def jump_far_ptr(self, addr: list[int]) -> None:
        self._pointer.far_to(addr)


# ---------------------------------------------------------------------------
# Unit tests — return values and types
# ---------------------------------------------------------------------------


def test_ret_far_returns_node():
    node = RET_FAR()
    assert node.tag == "__RET_FAR__"
    assert node.wrap_to_async is False


def test_push_stack_returns_node():
    node = PUSH_STACK("foo")
    assert node.tag == "__PUSH_STACK__"
    assert node.wrap_to_async is False


def test_push_and_goto_returns_node():
    node = PUSH_AND_GOTO("from", "to")
    assert node.tag == "__PUSH_AND_GOTO__"
    assert node.wrap_to_async is False


# ---------------------------------------------------------------------------
# Unit tests — PUSH_STACK logic
# ---------------------------------------------------------------------------


def test_push_stack_with_alias_pushes_resolved_address():
    pc = _FakeInterpreter()
    node = PUSH_STACK("after")
    node._post_compile(_FakeRendered({"after": [3, 1]}))
    node(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 1
    assert pc._ret_addr_stack.stack[-1].base_addr == [3, 1]


def test_push_stack_with_list_pushes_raw_address():
    pc = _FakeInterpreter()
    node = PUSH_STACK([7, 2])
    node._post_compile(_FakeRendered({}))
    node(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 1
    assert pc._ret_addr_stack.stack[-1].base_addr == [7, 2]


def test_push_stack_multiple():
    pc = _FakeInterpreter()
    n1 = PUSH_STACK("s1")
    n1._post_compile(_FakeRendered({"s1": [1]}))
    n1(pc)  # type: ignore[arg-type]
    n2 = PUSH_STACK("s2")
    n2._post_compile(_FakeRendered({"s2": [2]}))
    n2(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 2
    assert pc._ret_addr_stack.stack[0].base_addr == [1]
    assert pc._ret_addr_stack.stack[1].base_addr == [2]


# ---------------------------------------------------------------------------
# Unit tests — RET_FAR logic
# ---------------------------------------------------------------------------


def test_ret_far_pops_and_jumps():
    pc = _FakeInterpreter()
    pc._ret_addr_stack.push(PointerVector([5, 0]))
    node = RET_FAR()
    node(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 0
    assert pc._pointer.base_addr == [5, 0]


def test_ret_far_lifo_order():
    pc = _FakeInterpreter()
    pc._ret_addr_stack.push(PointerVector([1]))
    pc._ret_addr_stack.push(PointerVector([2]))
    RET_FAR()(pc)  # type: ignore[arg-type]
    assert pc._pointer.base_addr == [2]
    RET_FAR()(pc)  # type: ignore[arg-type]
    assert pc._pointer.base_addr == [1]
    assert len(pc._ret_addr_stack) == 0


# ---------------------------------------------------------------------------
# Unit tests — PUSH_AND_GOTO logic
# ---------------------------------------------------------------------------


def test_push_and_goto_alias_alias():
    pc = _FakeInterpreter()
    node = PUSH_AND_GOTO("from_addr", "to_addr")
    node._post_compile(_FakeRendered({"from_addr": [1], "to_addr": [2]}))
    node(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 1
    assert pc._ret_addr_stack.stack[-1].base_addr == [1]
    assert pc._pointer.base_addr == [2]


def test_push_and_goto_list_alias():
    pc = _FakeInterpreter()
    node = PUSH_AND_GOTO([1, 0], "to_addr")
    node._post_compile(_FakeRendered({"to_addr": [2]}))
    node(pc)  # type: ignore[arg-type]
    assert pc._ret_addr_stack.stack[-1].base_addr == [1, 0]
    assert pc._pointer.base_addr == [2]


def test_push_and_goto_alias_list():
    pc = _FakeInterpreter()
    node = PUSH_AND_GOTO("from_addr", [2, 0])
    node._post_compile(_FakeRendered({"from_addr": [1]}))
    node(pc)  # type: ignore[arg-type]
    assert pc._ret_addr_stack.stack[-1].base_addr == [1]
    assert pc._pointer.base_addr == [2, 0]


def test_push_and_goto_list_list():
    pc = _FakeInterpreter()
    node = PUSH_AND_GOTO([3], [4])
    node._post_compile(_FakeRendered({}))
    node(pc)  # type: ignore[arg-type]
    assert pc._ret_addr_stack.stack[-1].base_addr == [3]
    assert pc._pointer.base_addr == [4]


# ---------------------------------------------------------------------------
# Integration tests — real WorkflowInterpreter
# ---------------------------------------------------------------------------

from amrita_sense import ALIAS, NOP  # noqa: E402


@pytest.mark.asyncio
async def test_push_stack_goto_ret_far_roundtrip():
    """PUSH_STACK + GOTO + RET_FAR pattern with real interpreter."""
    from amrita_sense.instructions.jump import GOTO

    @Node()
    async def start() -> None:
        pass

    @Node()
    async def work() -> None:
        pass

    @Node()
    async def returned() -> None:
        pass

    comp = (
        start
        >> PUSH_STACK("after")
        >> GOTO("work")
        >> ALIAS(returned, "after")
        >> GOTO("end")
        >> ALIAS(work, "work")
        >> RET_FAR()
        >> ALIAS(NOP, "end")
    )
    interpreter = WorkflowInterpreter(comp.render())
    await interpreter.run()
    # If we reach here without error, the roundtrip succeeded


@pytest.mark.asyncio
async def test_push_and_goto_equivalent_to_push_stack_plus_goto():
    """PUSH_AND_GOTO should behave identically to PUSH_STACK + GOTO."""
    from amrita_sense.instructions.jump import GOTO

    @Node()
    async def start() -> None:
        pass

    @Node()
    async def work() -> None:
        pass

    @Node()
    async def returned() -> None:
        pass

    comp = (
        start
        >> PUSH_AND_GOTO("after", "work")
        >> ALIAS(returned, "after")
        >> GOTO("end")
        >> ALIAS(work, "work")
        >> RET_FAR()
        >> ALIAS(NOP, "end")
    )
    interpreter = WorkflowInterpreter(comp.render())
    await interpreter.run()
