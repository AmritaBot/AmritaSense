"""Tests for the interpreter's status register (`Flags`).

Covers the three bits (`IF`, `HLT`, `JMP`), their round-trip through
`InterpreterContext`, and the resume semantics of a halted interpreter.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from amrita_sense import ALIAS, JMP, Node, NodeCompose, WorkflowInterpreter
from amrita_sense.debugger import step_async
from amrita_sense.exceptions import InterruptKeepContext
from amrita_sense.instructions.interrupt import INT, IRET
from amrita_sense.instructions.workfl_ctrl import RESET, SUSPEND
from amrita_sense.node.core import NodeComposeRendered
from amrita_sense.runtime.types import Flags

LOG: list[str] = []


@Node()
def first() -> None:
    LOG.append("first")


@Node()
def second() -> None:
    LOG.append("second")


@Node()
def third() -> None:
    LOG.append("third")


@Node()
def halting() -> None:
    LOG.append("halting")
    raise InterruptKeepContext("test halt")


@pytest.fixture(autouse=True)
def _clear_log() -> Any:
    LOG.clear()
    yield
    LOG.clear()


class TestFlagsRegister:
    def test_initial_state_is_clear(self):
        pc = WorkflowInterpreter(NodeCompose(first).render())
        assert pc.flags == Flags.NONE
        assert pc.if_flag is False
        assert pc.jump_marked is False

    def test_if_flag_round_trips(self):
        pc = WorkflowInterpreter(NodeCompose(first).render())
        pc.if_flag = True
        assert pc.flags == Flags.IF
        assert pc.if_flag is True
        pc.if_flag = False
        assert pc.flags == Flags.NONE

    def test_if_flag_rejects_non_boolean(self):
        pc = WorkflowInterpreter(NodeCompose(first).render())
        bad: Any = 1
        with pytest.raises(TypeError):
            pc.if_flag = bad

    def test_bits_are_independent(self):
        pc = WorkflowInterpreter(NodeCompose(first).render())
        pc.if_flag = True
        pc._flags |= Flags.JMP
        assert pc.if_flag is True
        assert pc.jump_marked is True
        pc.unmarkup()
        assert pc.if_flag is True
        assert pc.jump_marked is False


class TestSnapshotRoundTrip:
    def test_context_carries_the_register(self):
        pc = WorkflowInterpreter(NodeCompose(first).render())
        pc.if_flag = True
        pc._flags |= Flags.JMP
        ctx = pc.dump_interpreter()
        assert ctx.flags & Flags.IF
        assert ctx.flags & Flags.JMP

    def test_rebase_restores_the_register(self):
        pc = WorkflowInterpreter(NodeCompose(first).render())
        ctx = pc.dump_interpreter()
        pc.if_flag = True
        pc._flags |= Flags.JMP
        pc.rebase_context(ctx)
        assert pc.flags == Flags.NONE

    @pytest.mark.asyncio
    async def test_dump_strips_hlt(self):
        """A snapshot taken while halted must not carry the halt bit."""
        pc = WorkflowInterpreter(NodeCompose(first, SUSPEND, second).render())
        await pc.run()
        assert pc.flags & Flags.HLT
        ctx = pc.dump_interpreter()
        assert not ctx.flags & Flags.HLT
        # The live register keeps it: only the snapshot is stripped.
        assert pc.flags & Flags.HLT

    def test_rebase_restores_every_captured_bit(self):
        pc = WorkflowInterpreter(NodeCompose(first).render())
        pc.if_flag = True
        pc._flags |= Flags.JMP
        ctx = pc.dump_interpreter()
        pc.if_flag = False
        pc.unmarkup()
        pc.rebase_context(ctx)
        assert pc.if_flag is True
        assert pc.jump_marked is True

    def test_int_snapshot_excludes_the_handler_if_bit(self):
        """`INT(..., if_state=True)` snapshots the state to return to."""
        pc = WorkflowInterpreter(NodeCompose(first, second).render())
        node = INT([0], [1], if_state=True)
        node._post_compile(cast(NodeComposeRendered, pc.get_graph()))
        node(pc)
        # The live register carries the handler's bit; the snapshot does not.
        assert pc.if_flag is True
        assert pc.context_stack.stack[-1].flags & Flags.IF == Flags.NONE

    def test_iret_restores_the_register(self):
        pc = WorkflowInterpreter(NodeCompose(first, second).render())
        node = INT([0], [1], if_state=True)
        node._post_compile(cast(NodeComposeRendered, pc.get_graph()))
        node(pc)
        IRET()(pc)
        assert pc.if_flag is False


class TestResumeFromHalt:
    @pytest.mark.asyncio
    async def test_run_again_advances_past_the_suspend_node(self):
        pc = WorkflowInterpreter(NodeCompose(first, SUSPEND, second, third).render())
        await pc.run()
        assert LOG == ["first"]
        assert pc.flags & Flags.HLT

        await pc.run()
        assert LOG == ["first", "second", "third"]
        assert not pc.flags & Flags.HLT

    @pytest.mark.asyncio
    async def test_resume_does_not_reexecute_the_halting_node(self):
        pc = WorkflowInterpreter(NodeCompose(first, halting, second).render())
        await pc.run()
        assert LOG == ["first", "halting"]

        await pc.run()
        assert LOG == ["first", "halting", "second"]

    @pytest.mark.asyncio
    async def test_hlt_is_cleared_by_an_explicit_jump(self):
        pc = WorkflowInterpreter(NodeCompose(first, SUSPEND, second).render())
        await pc.run()
        assert pc.flags & Flags.HLT
        pc.jump_to([0])
        assert not pc.flags & Flags.HLT
        assert pc.jump_marked

    @pytest.mark.asyncio
    async def test_hlt_is_cleared_by_rebase_ptr(self):
        pc = WorkflowInterpreter(NodeCompose(first, SUSPEND, second).render())
        await pc.run()
        assert pc.flags & Flags.HLT
        pc.rebase_ptr([0])
        assert not pc.flags & Flags.HLT

    @pytest.mark.asyncio
    async def test_run_step_by_also_resumes(self):
        pc = WorkflowInterpreter(NodeCompose(first, SUSPEND, second).render())
        async for _ in pc.run_step_by():
            pass
        assert LOG == ["first"]

        async for _ in pc.run_step_by():
            pass
        assert LOG == ["first", "second"]

    @pytest.mark.asyncio
    async def test_reset_does_not_leave_a_halt_bit(self):
        pc = WorkflowInterpreter(NodeCompose(first, RESET, second).render())
        await pc.run()
        assert pc.flags == Flags.NONE

    @pytest.mark.asyncio
    async def test_stepping_resumes_past_the_suspend_node(self):
        pc = WorkflowInterpreter(NodeCompose(first, SUSPEND, second).render())
        await pc.run()
        assert LOG == ["first"]
        assert pc.flags & Flags.HLT

        await step_async(pc, show=False)
        assert LOG == ["first", "second"]
        assert not pc.flags & Flags.HLT


class TestJumpBit:
    @pytest.mark.asyncio
    async def test_jump_node_consumes_the_bit(self):
        comp = NodeCompose(first, JMP("target"), second, ALIAS(third, "target"))
        pc = WorkflowInterpreter(comp.render())
        await pc.run()
        assert LOG == ["first", "third"]
        assert not pc.jump_marked

    def test_markup_sets_the_bit_once(self):
        pc = WorkflowInterpreter(NodeCompose(first).render())
        pc.jump_to([0])
        pc.jump_to([0])
        assert pc.jump_marked
        pc.unmarkup()
        assert not pc.jump_marked
