"""Tests for interrupt.py — PUSH_CONTEXT, POP_CONTEXT, INTERRUPT_INTO, INTERRUPT_RET."""

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
from amrita_sense.runtime.types import InterpreterContext
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector, Stack

# Fake interpreter for exercising instruction logic


class _FakeGraph:
    def __init__(self, alias_map: dict[str, list[int]]) -> None:
        self.alias2vector_map = alias_map


class _FakeInterpreter:
    """Minimal fake WorkflowInterpreter surface."""

    def __init__(
        self,
        alias_map: dict[str, list[int]] | None = None,
        ptr: list[int] | None = None,
    ) -> None:
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

    def get_graph(self) -> _FakeGraph:
        return self._graph

    def find_addr_alias(self, alias: str) -> list[int]:
        return self._graph.alias2vector_map[alias]

    def jump_to(self, addr: list[int]) -> None:
        self._pointer.far_to(addr)
        self._jump_marked = True

    def dump_interpreter(
        self, exclude_deps: bool = True, exclude_stack: bool = True
    ) -> InterpreterContext:
        return InterpreterContext(
            ptr=self._pointer.copy(),
            exception_ignored=self._exc_ignored,
            s_args=None if exclude_deps else self._ava_args,
            s_kwargs=None if exclude_deps else self._ava_kwargs,
            extra={},
            stack=None if exclude_stack else self._ret_addr_stack,
            exception=self._panic_exc,
        )

    def rebase_context(self, ctx: InterpreterContext) -> None:
        self._pointer.far_to(ctx.ptr.base_addr)
        self._exc_ignored = ctx.exception_ignored
        if ctx.s_args is not None and ctx.s_kwargs is not None:
            self._ava_args = ctx.s_args
            self._ava_kwargs = ctx.s_kwargs
        self._ret_addr_stack = ctx.stack or self._ret_addr_stack
        self._panic_exc = ctx.exception


# Node type / return value tests


def test_push_context_returns_node():
    node = PUSH_CONTEXT()
    assert node.tag == "__PUSH_CONTEXT__"
    assert node.wrap_to_async is False


def test_push_context_default_params():
    node = PUSH_CONTEXT()
    assert node.tag is not None


def test_push_context_with_options_returns_node():
    node = PUSH_CONTEXT(exclude_deps=False, exclude_stack=False)
    assert node.tag == "__PUSH_CONTEXT__"


def test_pop_context_returns_node():
    node = POP_CONTEXT()
    assert node.tag == "__POP_CONTEXT__"
    assert node.wrap_to_async is False


def test_interrupt_into_returns_node():
    node = INTERRUPT_INTO("target")
    assert node.tag == "__INTERRUPT_INTO__"
    assert node.wrap_to_async is False


def test_interrupt_into_with_list_address_returns_node():
    node = INTERRUPT_INTO([1, 2], if_state=True)
    assert node.tag == "__INTERRUPT_INTO__"


def test_interrupt_ret_returns_node():
    node = INTERRUPT_RET()
    assert node.tag == "__INTERRUPT_RET__"
    assert node.wrap_to_async is False


# PUSH_CONTEXT unit tests


def test_push_context_saves_state():
    pc = _FakeInterpreter(ptr=[3, 5])
    node = PUSH_CONTEXT()
    node(pc)  # type: ignore[arg-type]

    assert len(pc.context_stack) == 1
    ctx = pc.context_stack.stack[0]
    assert ctx.ptr.base_addr == [3, 5]
    assert ctx.exception_ignored == (InterruptNotice,)
    # defaults: exclude_deps=True, exclude_stack=True
    assert ctx.s_args is None
    assert ctx.s_kwargs is None
    assert ctx.stack is None


def test_push_context_exclude_deps_false():
    pc = _FakeInterpreter()
    pc._ava_args = (42,)
    pc._ava_kwargs = {"greeting": "hi"}

    node = PUSH_CONTEXT(exclude_deps=False)
    node(pc)  # type: ignore[arg-type]

    ctx = pc.context_stack.stack[0]
    assert ctx.s_args == (42,)
    assert ctx.s_kwargs == {"greeting": "hi"}


def test_push_context_exclude_stack_false():
    pc = _FakeInterpreter()
    pc._ret_addr_stack.push(PointerVector([9]))

    node = PUSH_CONTEXT(exclude_stack=False)
    node(pc)  # type: ignore[arg-type]

    ctx = pc.context_stack.stack[0]
    assert ctx.stack is not None
    assert ctx.stack.stack[-1].base_addr == [9]


def test_push_context_multiple_pushes():
    pc = _FakeInterpreter(ptr=[0])
    PUSH_CONTEXT()(pc)  # type: ignore[arg-type]
    pc._pointer.far_to([7])
    PUSH_CONTEXT()(pc)  # type: ignore[arg-type]

    assert len(pc.context_stack) == 2
    assert pc.context_stack.stack[0].ptr.base_addr == [0]
    assert pc.context_stack.stack[1].ptr.base_addr == [7]


# POP_CONTEXT unit tests


def test_pop_context_returns_saved_state():
    pc = _FakeInterpreter(ptr=[2, 8])
    PUSH_CONTEXT()(pc)  # type: ignore[arg-type]

    # POP_CONTEXT returns the popped InterpreterContext
    node = POP_CONTEXT()
    result = node(pc)  # type: ignore[arg-type]

    assert isinstance(result, InterpreterContext)
    assert result.ptr.base_addr == [2, 8]
    assert len(pc.context_stack) == 0  # popped


def test_pop_context_stack_order():
    pc = _FakeInterpreter()
    PUSH_CONTEXT()(pc)  # type: ignore[arg-type]  # first push: ptr [0]
    pc._pointer.far_to([10])
    PUSH_CONTEXT()(pc)  # type: ignore[arg-type]  # second push: ptr [10]

    # LIFO — second push is popped first
    ctx2 = POP_CONTEXT()(pc)  # type: ignore[arg-type]
    ctx1 = POP_CONTEXT()(pc)  # type: ignore[arg-type]

    assert ctx2.ptr.base_addr == [10]
    assert ctx1.ptr.base_addr == [0]


# INTERRUPT_INTO unit tests


def test_interrupt_into_saves_context_and_jumps():
    pc = _FakeInterpreter({"handler": [5, 0]}, ptr=[0, 0])
    node = INTERRUPT_INTO("handler")
    node(pc)  # type: ignore[arg-type]

    # context saved
    assert len(pc.context_stack) == 1
    assert pc.context_stack.stack[0].ptr.base_addr == [0, 0]
    # jumped to target
    assert pc._pointer.base_addr == [5, 0]
    assert pc._jump_marked is True


def test_interrupt_into_sets_if_flag():
    pc = _FakeInterpreter({"h": [1]}, ptr=[0])
    node = INTERRUPT_INTO("h", if_state=True)
    node(pc)  # type: ignore[arg-type]

    assert pc.if_flag is True


def test_interrupt_into_default_if_flag():
    pc = _FakeInterpreter({"h": [1]}, ptr=[0])
    node = INTERRUPT_INTO("h")  # if_state defaults to False
    node(pc)  # type: ignore[arg-type]

    assert pc.if_flag is False


def test_interrupt_into_with_list_address():
    pc = _FakeInterpreter(ptr=[0])
    # Use raw address list instead of alias
    node = INTERRUPT_INTO([3, 7], if_state=False)
    node(pc)  # type: ignore[arg-type]

    assert pc._pointer.base_addr == [3, 7]
    assert len(pc.context_stack) == 1


def test_interrupt_into_raises_when_if_flag_is_true():
    pc = _FakeInterpreter({"h": [1]}, ptr=[0])
    pc.if_flag = True

    node = INTERRUPT_INTO("h")
    with pytest.raises(IllegalState, match="Interrupt into is not allowed"):
        node(pc)  # type: ignore[arg-type]


def test_interrupt_into_does_not_save_when_raises():
    pc = _FakeInterpreter({"h": [1]}, ptr=[0])
    pc.if_flag = True

    node = INTERRUPT_INTO("h")
    with pytest.raises(IllegalState):
        node(pc)  # type: ignore[arg-type]

    # context stack untouched
    assert len(pc.context_stack) == 0
    # pointer unchanged
    assert pc._pointer.base_addr == [0]


# INTERRUPT_RET unit tests


def test_interrupt_ret_restores_context():
    pc = _FakeInterpreter({"handler": [2, 0]}, ptr=[0, 0])
    # save context and jump via INTERRUPT_INTO
    INTERRUPT_INTO("handler")(pc)  # type: ignore[arg-type]

    # modify state after jump
    pc._pointer.far_to([2, 0])  # simulate executing handler
    pc.if_flag = True

    # INTERRUPT_RET restores pre-interrupt state
    INTERRUPT_RET()(pc)  # type: ignore[arg-type]

    # pre-check pointer stays via jump — _jump_marked set by jp in ret
    assert pc._pointer.base_addr == [0, 0]
    assert pc.if_flag is False
    assert len(pc.context_stack) == 0  # popped


def test_interrupt_ret_restores_if_flag_to_false():
    pc = _FakeInterpreter({"h": [1]}, ptr=[0])
    INTERRUPT_INTO("h", if_state=True)(pc)  # type: ignore[arg-type]
    # simulate: pointer already advanced
    INTERRUPT_RET()(pc)  # type: ignore[arg-type]

    assert pc.if_flag is False


# End-to-end: composition-level (real WorkflowInterpreter)





@pytest.mark.asyncio
async def test_push_pop_context_e2e():
    """End-to-end: PUSH_CONTEXT saves state, node pops and inspects it."""
    steps: list[str] = []

    @Node()
    async def start() -> None:
        steps.append("start")

    @Node()
    async def sub(pc: WorkflowInterpreter) -> None:
        ctx = pc.context_stack.pop()
        steps.append(f"popped_ptr={ctx.ptr.base_addr}")

    @Node()
    async def finish() -> None:
        steps.append("finish")

    comp = start >> PUSH_CONTEXT() >> sub >> finish >> ALIAS(NOP, "done")
    await WorkflowInterpreter(comp.render()).run()

    assert steps == ["start", f"popped_ptr={[1]}", "finish"]


@pytest.mark.asyncio
async def test_interrupt_into_ret_e2e():
    """End-to-end: INTERRUPT_INTO saves context, INTERRUPT_RET restores."""
    from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
    from amrita_sense.instructions import INTERRUPT_INTO, INTERRUPT_RET

    log: list[str] = []

    @Node()
    async def main_start() -> None:
        log.append("main_start")

    @Node()
    async def handler() -> None:
        log.append("handler")

    @Node()
    async def back() -> None:
        log.append("back_to_main")

    handler_block = ARCHIVED_NODES(
        ALIAS(handler, "int_handler"),
        INTERRUPT_RET(),
    )

    comp = (
        main_start
        >> INTERRUPT_INTO("int_handler")
        >> back
        >> GOTO("done")
        >> handler_block
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(comp.render()).run()

    assert log == ["main_start", "handler", "back_to_main"]


@pytest.mark.asyncio
async def test_push_context_preserves_pointer():
    """After PUSH_CONTEXT the pointer is unchanged — execution continues normally."""
    calls: list[str] = []

    @Node()
    async def a() -> None:
        calls.append("a")

    @Node()
    async def b() -> None:
        calls.append("b")

    @Node()
    async def c() -> None:
        calls.append("c")

    comp = a >> PUSH_CONTEXT() >> b >> c >> ALIAS(NOP, "done")
    await WorkflowInterpreter(comp.render()).run()
    assert calls == ["a", "b", "c"]
