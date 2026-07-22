"""Tests for the AmritaSense debugger module."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.debugger import (
    Breakpoint,
    BreakpointHit,
    backtrace,
    break_at_addr,
    break_at_tag,
    clear_break_addr,
    clear_break_tag,
    cont_async,
    inspect,
    list_breaks,
    list_nodes,
    list_sub_intp,
    step_async,
    step_out_async,
    step_over_async,
    where,
)

if TYPE_CHECKING:
    from amrita_sense.runtime.workflow import WorkflowInterpreter


# Test node definitions


@Node(tag="simple")
def simple_node(pc: WorkflowInterpreter) -> str:
    """A node that just returns a value."""
    return "ok"


@Node(tag="noop")
async def noop_node(pc: WorkflowInterpreter) -> None:
    pass


@Node(tag="caller")
async def caller_node(pc: WorkflowInterpreter) -> str:
    """Call noop_node via call_near, then return."""
    await pc.call_near(1)  # relative addr 1 → noop_node
    return "done"


# Fixtures


@pytest.fixture
def simple_inter() -> WorkflowInterpreter:
    cmp = simple_node.as_compose().render()
    return WorkflowInterpreter(cmp)


@pytest.fixture
def multi_inter() -> WorkflowInterpreter:
    cmp = (simple_node >> noop_node).render()
    return WorkflowInterpreter(cmp)


@pytest.fixture
def call_inter() -> WorkflowInterpreter:
    cmp = (caller_node >> noop_node).render()
    return WorkflowInterpreter(cmp)


@pytest.fixture
def crashing_inter() -> WorkflowInterpreter:
    @Node(tag="always_fail")
    def fail(pc: WorkflowInterpreter) -> None:
        raise RuntimeError("planned crash")

    cmp = fail.as_compose().render()
    return WorkflowInterpreter(cmp)


# inspect tests


class TestInspect:
    def test_where_does_not_crash(self, simple_inter: WorkflowInterpreter) -> None:
        where(simple_inter)

    def test_inspect_does_not_crash(self, simple_inter: WorkflowInterpreter) -> None:
        inspect(simple_inter)

    def test_backtrace_does_not_crash(self, simple_inter: WorkflowInterpreter) -> None:
        backtrace(simple_inter)

    def test_list_nodes_shows_nodes(self, multi_inter: WorkflowInterpreter) -> None:
        list_nodes(multi_inter)

    def test_list_sub_intp_shows_self(self, simple_inter: WorkflowInterpreter) -> None:
        list_sub_intp(simple_inter)

    def test_list_sub_intp_shows_children(self) -> None:
        cmp = simple_node.as_compose().render()
        parent = WorkflowInterpreter(cmp)
        parent.fork_interpreter(cmp)
        list_sub_intp(parent)  # should show child

    def test_inspect_after_crash(self, crashing_inter: WorkflowInterpreter) -> None:
        async def run():
            try:
                await crashing_inter.run()
            except RuntimeError:
                pass

        asyncio.run(run())
        # inspect should show panic state
        exc = crashing_inter.get_exception()
        assert exc is not None, "Panic exception should be preserved"
        inspect(crashing_inter)


# step tests


class TestStep:
    def test_step_executes_one_node(self, simple_inter: WorkflowInterpreter) -> None:
        async def run():
            await step_async(simple_inter)
            # After step on a single-node graph, advance_pointer returns
            # False and the pointer is cleared.
            assert not simple_inter._pointer

        asyncio.run(run())

    def test_step_finishes_workflow(self, simple_inter: WorkflowInterpreter) -> None:
        async def run():
            await step_async(simple_inter)  # execute the only node → pointer cleared
            # Second step should print "(workflow finished)"
            await step_async(simple_inter)

        asyncio.run(run())

    def test_step_over_skips_sub_call(self, call_inter: WorkflowInterpreter) -> None:
        """step_over should execute caller + sub call and stop after."""

        async def run():
            await step_over_async(call_inter)
            ptr = call_inter._pointer.base_addr
            assert ptr == [1], f"Expected [1], got {ptr}"

        asyncio.run(run())

    def test_step_out_exits_frame(self, call_inter: WorkflowInterpreter) -> None:
        """step_out should finish remaining nodes in current frame."""

        async def run():
            await step_async(call_inter)  # execute caller_node → ptr=[1]
            await step_out_async(call_inter)  # finish noop_node → ptr cleared
            assert not call_inter._pointer

        asyncio.run(run())

    def test_keyboard_interrupt_in_cont(
        self,
        multi_inter: WorkflowInterpreter,
    ) -> None:
        """cont() should run to completion for a normal workflow."""

        async def run():
            await cont_async(multi_inter)

        asyncio.run(run())
        assert not multi_inter.is_running


# breakpoint tests


class TestBreakpoint:
    def test_breakpoint_dataclass(self) -> None:
        bp = Breakpoint(target="test", kind="tag")
        assert bp.target == "test"
        assert bp.kind == "tag"
        assert bp.hit_count == 0
        assert bp.enabled is True

    def test_break_at_tag_registers(self, simple_inter: WorkflowInterpreter) -> None:
        bp = break_at_tag(simple_inter, "simple")
        assert bp.kind == "tag"
        list_breaks(simple_inter)

    def test_break_at_tag_hits(self, simple_inter: WorkflowInterpreter) -> None:
        async def run():
            break_at_tag(simple_inter, "simple")
            await cont_async(simple_inter)  # should hit breakpoint before first node

        asyncio.run(run())
        assert simple_inter._pointer.base_addr == [0]

    def test_break_at_addr_hits(self, multi_inter: WorkflowInterpreter) -> None:
        async def run():
            break_at_addr(multi_inter, [0])
            await cont_async(multi_inter)  # hit breakpoint at addr [0]
            assert multi_inter._pointer.base_addr == [0]

        asyncio.run(run())

    def test_condition_breakpoint(
        self,
        multi_inter: WorkflowInterpreter,
    ) -> None:
        """Condition breakpoint: only hits when condition is True."""

        async def run():
            break_at_tag(
                multi_inter,
                "simple",
                condition=lambda pc: len(pc._ret_addr_stack) >= 0,  # always true
            )
            await cont_async(multi_inter)
            assert multi_inter._pointer.base_addr == [0]  # breakpoint hit

        asyncio.run(run())

    def test_clear_break_tag(self, simple_inter: WorkflowInterpreter) -> None:
        break_at_tag(simple_inter, "simple")
        clear_break_tag(simple_inter, "simple")

    def test_clear_break_addr(self, multi_inter: WorkflowInterpreter) -> None:
        break_at_addr(multi_inter, [0])
        clear_break_addr(multi_inter, [0])

    def test_list_breaks_empty(self, simple_inter: WorkflowInterpreter) -> None:
        list_breaks(simple_inter)  # should print "(no breakpoints)"

    def test_recover_from_panic(self, crashing_inter: WorkflowInterpreter) -> None:
        """After a crash, cont should recover from panic and continue."""

        async def run():
            try:
                await crashing_inter.run()
            except RuntimeError:
                pass
            assert crashing_inter.get_exception() is not None
            # cont should recover from panic and try again
            try:
                await cont_async(crashing_inter)
            except RuntimeError:
                pass

        asyncio.run(run())


# BreakpointHit exception tests


class TestBreakpointHit:
    def test_is_base_exception(self) -> None:
        bp = Breakpoint(target="test", kind="tag")
        exc = BreakpointHit(bp)
        assert isinstance(exc, BaseException)
        assert not isinstance(exc, Exception)  # won't trigger panic

    def test_str_representation(self) -> None:
        bp = Breakpoint(target="test", kind="tag", hit_count=3)
        exc = BreakpointHit(bp)
        assert "test" in str(exc)
        assert "3" in str(exc)
