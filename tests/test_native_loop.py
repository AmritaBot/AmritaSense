"""Tests for BREAK_LOOP / CONTINUE in native WHILE/DO loops."""

import pytest

from amrita_sense import Node, NodeCompose, WorkflowInterpreter
from amrita_sense.instructions.native import (
    BREAK_LOOP,
    CONTINUE,
    NATIVE_DO,
    NATIVE_WHILE,
)

#  WHILE + BREAK_LOOP


class TestWhileBreak:
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
            NATIVE_WHILE(cond).ACTION(NodeCompose(step_a, BREAK_LOOP(), step_b))
            >> after
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
            NATIVE_WHILE(cond).ACTION(NodeCompose(body, BREAK_LOOP())) >> n1 >> n2
        ).render()
        await WorkflowInterpreter(comp).run()
        assert results == ["body1", "n1", "n2"]


#  DO + BREAK_LOOP


class TestDoBreak:
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
            NATIVE_DO(NodeCompose(step_a, BREAK_LOOP(), step_b)).WHILE(cond).extract()
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
            NATIVE_DO(NodeCompose(body, BREAK_LOOP())).WHILE(cond).extract() >> after
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


#  WHILE + CONTINUE


class TestWhileContinue:
    @pytest.mark.asyncio
    async def test_while_continue_skips_rest_of_body(self):
        results = []
        counter = [0]

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return counter[0] < 5

        @Node(wrap_to_async=False)
        def step_a() -> None:
            counter[0] += 1

        @Node(wrap_to_async=False)
        def step_b() -> None:
            results.append(f"b{counter[0]}")

        @Node(wrap_to_async=False)
        def step_c() -> None:
            results.append(f"c{counter[0]}")

        comp = (
            NATIVE_WHILE(cond)
            .ACTION(NodeCompose(step_a, CONTINUE(), step_b, step_c))
            .extract()
            .render()
        )
        await WorkflowInterpreter(comp).run()
        # step_b, step_c should never execute; CONTINUE jumps to next iteration
        assert results == []
        assert counter[0] == 5

    @pytest.mark.asyncio
    async def test_while_continue_then_finishes_normally(self):
        results = []
        counter = [0]

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return counter[0] < 3

        @Node(wrap_to_async=False)
        def body() -> None:
            counter[0] += 1
            if counter[0] == 2:
                results.append("skip")

        comp = NATIVE_WHILE(cond).ACTION(body).extract().render()
        await WorkflowInterpreter(comp).run()
        assert counter[0] == 3
        assert results == ["skip"]


#  DO + CONTINUE


class TestDoContinue:
    @pytest.mark.asyncio
    async def test_do_continue_skips_rest_of_body(self):
        results = []
        counter = [0]

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return counter[0] < 5

        @Node(wrap_to_async=False)
        def step_a() -> None:
            counter[0] += 1

        @Node(wrap_to_async=False)
        def step_b() -> None:
            results.append(f"b{counter[0]}")

        comp = (
            NATIVE_DO(NodeCompose(step_a, CONTINUE(), step_b)).WHILE(cond).extract()
        ).render()
        await WorkflowInterpreter(comp).run()
        assert results == []
        assert counter[0] == 5

    @pytest.mark.asyncio
    async def test_do_continue_at_least_one_exec(self):
        results = []

        @Node(wrap_to_async=False)
        def cond() -> bool:
            return False

        @Node(wrap_to_async=False)
        def pre() -> None:
            results.append("pre")

        @Node(wrap_to_async=False)
        def post() -> None:
            results.append("post")

        comp = (
            NATIVE_DO(NodeCompose(pre, CONTINUE(), post)).WHILE(cond).extract()
        ).render()
        await WorkflowInterpreter(comp).run()
        assert results == ["pre"]


# ── Nesting ───────────────────────────────────────────────────────────


class TestNestedLoops:
    @pytest.mark.asyncio
    async def test_nested_while_break_inner_only(self):
        results = []
        outer_count = [0]
        inner_count = [0]

        @Node(wrap_to_async=False)
        def outer_cond() -> bool:
            return outer_count[0] < 3

        @Node(wrap_to_async=False)
        def inner_cond() -> bool:
            return inner_count[0] < 10

        @Node(wrap_to_async=False)
        def inner_step() -> None:
            inner_count[0] += 1
            results.append(f"i{inner_count[0]}")

        # Inner loop: body step + BREAK → runs once then breaks
        inner_body = NodeCompose(inner_step, BREAK_LOOP())
        inner_loop = NATIVE_WHILE(inner_cond).ACTION(inner_body).extract()

        @Node(wrap_to_async=False)
        def outer_body() -> None:
            outer_count[0] += 1
            results.append(f"o{outer_count[0]}")

        outer_body_comp = NodeCompose(inner_loop, outer_body)
        comp = NATIVE_WHILE(outer_cond).ACTION(outer_body_comp).extract().render()
        await WorkflowInterpreter(comp).run()
        # inner BREAK_LOOP each time, outer runs 3 times
        assert results == ["i1", "o1", "i2", "o2", "i3", "o3"]

    @pytest.mark.asyncio
    async def test_nested_while_continue_inner_only(self):
        results = []
        outer_count = [0]
        inner_count = [0]

        @Node(wrap_to_async=False)
        def outer_cond() -> bool:
            return outer_count[0] < 2

        @Node(wrap_to_async=False)
        def inner_cond() -> bool:
            return inner_count[0] < 3

        @Node(wrap_to_async=False)
        def inner_pre() -> None:
            inner_count[0] += 1

        @Node(wrap_to_async=False)
        def inner_post() -> None:
            results.append(f"post{inner_count[0]}")

        # Inner loop: CONTINUE skips inner_post each iteration
        inner_body = NodeCompose(inner_pre, CONTINUE(), inner_post)
        inner_loop = NATIVE_WHILE(inner_cond).ACTION(inner_body).extract()

        @Node(wrap_to_async=False)
        def outer_body() -> None:
            outer_count[0] += 1
            results.append(f"o{outer_count[0]}")

        outer_body_comp = NodeCompose(inner_loop, outer_body)
        comp = NATIVE_WHILE(outer_cond).ACTION(outer_body_comp).extract().render()
        await WorkflowInterpreter(comp).run()
        # inner CONTINUE skips inner_post; inner runs 3 times in first outer
        # iteration then inner_count=3 so second outer iteration inner is skipped
        assert results == ["o1", "o2"]
        assert inner_count[0] == 3
