"""Tests for ret2.py — PUSH_RET, RET, CALL instructions."""

from typing import TYPE_CHECKING

import pytest

from amrita_sense.instructions.ret2 import CALL, PUSH_RET, RET
from amrita_sense.node.core import NodeComposeRendered
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector, Stack

# Fake rendered object for post_compile hooks (mirrors interrupt test pattern)


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


# Fake interpreter (minimal — no alias resolution needed at runtime)


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

    def rebase_ptr(self, ptr: list[int] | PointerVector) -> None:
        self._pointer.base_addr = (
            list(ptr) if isinstance(ptr, list) else ptr.base_addr.copy()
        )


# Unit tests — return values and types


def test_ret_returns_node():
    node = RET()
    assert node.tag == "__RET__"
    assert node.wrap_to_async is False


def test_push_ret_returns_node():
    node = PUSH_RET("foo")
    assert node.tag == "__PUSH_RET__"
    assert node.wrap_to_async is False


def test_call_returns_node():
    node = CALL("to", from_adr="from")
    assert node.tag == "__CALL__"
    assert node.wrap_to_async is False


# Unit tests — PUSH_RET logic


def test_push_ret_with_alias_pushes_resolved_address():
    pc = _FakeInterpreter()
    node = PUSH_RET("after")
    node._post_compile(_FakeRendered({"after": [3, 1]}))
    node(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 1
    assert pc._ret_addr_stack.stack[-1].base_addr == [3, 1]


def test_push_ret_with_list_pushes_raw_address():
    pc = _FakeInterpreter()
    node = PUSH_RET([7, 2])
    node._post_compile(_FakeRendered({}))
    node(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 1
    assert pc._ret_addr_stack.stack[-1].base_addr == [7, 2]


def test_push_ret_multiple():
    pc = _FakeInterpreter()
    n1 = PUSH_RET("s1")
    n1._post_compile(_FakeRendered({"s1": [1]}))
    n1(pc)  # type: ignore[arg-type]
    n2 = PUSH_RET("s2")
    n2._post_compile(_FakeRendered({"s2": [2]}))
    n2(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 2
    assert pc._ret_addr_stack.stack[0].base_addr == [1]
    assert pc._ret_addr_stack.stack[1].base_addr == [2]


# Unit tests — RET logic


def test_ret_pops_and_jumps():
    pc = _FakeInterpreter()
    pc._ret_addr_stack.push(PointerVector([5, 0]))
    node = RET()
    node(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 0
    assert pc._pointer.base_addr == [5, 0]


def test_ret_lifo_order():
    pc = _FakeInterpreter()
    pc._ret_addr_stack.push(PointerVector([1]))
    pc._ret_addr_stack.push(PointerVector([2]))
    RET()(pc)  # type: ignore[arg-type]
    assert pc._pointer.base_addr == [2]
    RET()(pc)  # type: ignore[arg-type]
    assert pc._pointer.base_addr == [1]
    assert len(pc._ret_addr_stack) == 0


# Unit tests — CALL logic


def test_call_alias_alias():
    pc = _FakeInterpreter()
    node = CALL("to_addr", from_adr="from_addr")
    node._post_compile(_FakeRendered({"from_addr": [1], "to_addr": [2]}))
    node(pc)  # type: ignore[arg-type]
    assert len(pc._ret_addr_stack) == 1
    assert pc._ret_addr_stack.stack[-1].base_addr == [1]
    assert pc._pointer.base_addr == [2]


def test_call_list_alias():
    pc = _FakeInterpreter()
    node = CALL("to_addr", from_adr=[1, 0])
    node._post_compile(_FakeRendered({"to_addr": [2]}))
    node(pc)  # type: ignore[arg-type]
    assert pc._ret_addr_stack.stack[-1].base_addr == [1, 0]
    assert pc._pointer.base_addr == [2]


def test_call_alias_list():
    pc = _FakeInterpreter()
    node = CALL([2, 0], from_adr="from_addr")
    node._post_compile(_FakeRendered({"from_addr": [1]}))
    node(pc)  # type: ignore[arg-type]
    assert pc._ret_addr_stack.stack[-1].base_addr == [1]
    assert pc._pointer.base_addr == [2, 0]


def test_call_list_list():
    pc = _FakeInterpreter()
    node = CALL([4], from_adr=[3])
    node._post_compile(_FakeRendered({}))
    node(pc)  # type: ignore[arg-type]
    assert pc._ret_addr_stack.stack[-1].base_addr == [3]
    assert pc._pointer.base_addr == [4]


# Integration tests — real WorkflowInterpreter


from amrita_sense import ALIAS, NOP  # noqa: E402


@pytest.mark.asyncio
async def test_push_ret_jmp_ret_roundtrip():
    """PUSH_RET + JMP + RET pattern with real interpreter.

    Since v0.6.0, RET uses rebase_ptr (no jump flag) and the interpreter
    advances onto the node AFTER the saved address — so the caller must push
    the predecessor of the real resume point (the "resume" NOP).
    """
    from amrita_sense.instructions.jump import JMP

    executed: list[str] = []

    @Node()
    async def start() -> None:
        executed.append("start")

    @Node()
    async def work() -> None:
        executed.append("work")

    @Node()
    async def returned() -> None:
        executed.append("returned")

    comp = (
        start
        >> PUSH_RET("resume")  # push the NOP right before `returned`
        >> JMP("work")
        >> ALIAS(NOP, "resume")  # RET rebases here -> advance lands on returned
        >> ALIAS(returned, "after")
        >> JMP("end")
        >> ALIAS(work, "work")
        >> RET()
        >> ALIAS(NOP, "end")
    )
    interpreter = WorkflowInterpreter(comp.render())
    await interpreter.run()
    assert executed == ["start", "work", "returned"]


@pytest.mark.asyncio
async def test_call_equivalent_to_push_ret_plus_jmp():
    """CALL(target) should behave identically to PUSH_RET + JMP."""
    from amrita_sense.instructions.jump import JMP

    executed: list[str] = []

    @Node()
    async def start() -> None:
        executed.append("start")

    @Node()
    async def work() -> None:
        executed.append("work")

    @Node()
    async def returned() -> None:
        executed.append("returned")

    comp = (
        start
        >> CALL("work")  # from_adr=None in main flow = current pointer
        >> ALIAS(returned, "after")  # RET rebases to CALL -> advance lands here
        >> JMP("end")
        >> ALIAS(work, "work")
        >> RET()
        >> ALIAS(NOP, "end")
    )
    interpreter = WorkflowInterpreter(comp.render())
    await interpreter.run()
    assert executed == ["start", "work", "returned"]
