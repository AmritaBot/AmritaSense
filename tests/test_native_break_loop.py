"""Tests for BREAK_LOOP in native WHILE/DO bubble bodies."""

import pytest

from amrita_sense import Node, NodeCompose, WorkflowInterpreter
from amrita_sense.instructions.native import BREAK_LOOP, NATIVE_DO, NATIVE_WHILE


class TestWhileBreakLoop:
    @pytest.mark.asyncio
    async def test_while_break_exits_loop(self):
        results = []
        counter = [0]

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return counter[0] < 10

        @Node(wrap_to_async=False)
        def step_a() -> None:
            counter[0] += 1
            results.append(f"a{counter[0]}")

        @Node(wrap_to_async=False)
        def step_b() -> None:
            results.append(f"b{counter[0]}")

        @Node(wrap_to_async=False)
        def after() -> None:
            results.append("after")

        comp = (
            NATIVE_WHILE(cond).ACTION(NodeCompose(step_a, BREAK_LOOP, step_b)) >> after
        ).render()
        await WorkflowInterpreter(comp).run()
        assert results == ["a1", "after"]

    @pytest.mark.asyncio
    async def test_while_single_node_body_no_break_needed(self):
        counter = [0]

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return counter[0] < 3

        @Node(wrap_to_async=False)
        def body() -> None:
            counter[0] += 1

        comp = NATIVE_WHILE(cond).ACTION(body).extract().render()
        await WorkflowInterpreter(comp).run()
        assert counter[0] == 3


class TestDoBreakLoop:
    @pytest.mark.asyncio
    async def test_do_break_exits_loop(self):
        results = []
        counter = [0]

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return True

        @Node(wrap_to_async=False)
        def step_a() -> None:
            counter[0] += 1
            results.append(f"a{counter[0]}")

        @Node(wrap_to_async=False)
        def step_b() -> None:
            results.append(f"b{counter[0]}")

        @Node(wrap_to_async=False)
        def after() -> None:
            results.append("after")

        comp = (
            NATIVE_DO(NodeCompose(step_a, BREAK_LOOP, step_b)).WHILE(cond).extract()
            >> after
        ).render()
        await WorkflowInterpreter(comp).run()
        assert results == ["a1", "after"]

    @pytest.mark.asyncio
    async def test_do_break_then_continues_after(self):
        results = []

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return True

        @Node(wrap_to_async=False)
        def body() -> None:
            results.append("body")

        @Node(wrap_to_async=False)
        def after() -> None:
            results.append("after")

        comp = (
            NATIVE_DO(NodeCompose(body, BREAK_LOOP)).WHILE(cond).extract() >> after
        ).render()
        await WorkflowInterpreter(comp).run()
        assert results == ["body", "after"]

    @pytest.mark.asyncio
    async def test_do_normal_loop_without_break(self):
        counter = [0]

        @Node(wrap_to_async=False)
        def body() -> None:
            counter[0] += 1

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return counter[0] < 3

        comp = NATIVE_DO(body).WHILE(cond).extract().render()
        await WorkflowInterpreter(comp).run()
        assert counter[0] == 3


class TestBreakLoopContinues:
    @pytest.mark.asyncio
    async def test_while_break_many_nodes_after(self):
        results = []
        counter = [0]

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return counter[0] < 10

        @Node(wrap_to_async=False)
        def body() -> None:
            counter[0] += 1
            results.append(f"body{counter[0]}")

        @Node(wrap_to_async=False)
        def n1() -> None:
            results.append("n1")

        @Node(wrap_to_async=False)
        def n2() -> None:
            results.append("n2")

        comp = (
            NATIVE_WHILE(cond).ACTION(NodeCompose(body, BREAK_LOOP)) >> n1 >> n2
        ).render()
        await WorkflowInterpreter(comp).run()
        assert results == ["body1", "n1", "n2"]
