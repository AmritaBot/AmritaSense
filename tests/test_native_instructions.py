"""Unit tests for native fast-path control-flow instructions."""

import pytest

from amrita_sense import Node, NodeCompose, WorkflowInterpreter
from amrita_sense.instructions.native import NATIVE_DO, NATIVE_IF, NATIVE_WHILE


@Node(wrap_to_async=False)
def ret_true() -> bool:
    return True


@Node(wrap_to_async=False)
def ret_false() -> bool:
    return False


#  NATIVE_IF


class TestNativeIf:
    @pytest.mark.asyncio
    async def test_if_true_single(self):
        executed = [False]

        @Node(wrap_to_async=False)
        def body():
            executed[0] = True

        comp = NATIVE_IF(ret_true, body).extract().render()
        await WorkflowInterpreter(comp).run()
        assert executed[0] is True

    @pytest.mark.asyncio
    async def test_if_false_single(self):
        executed = [False]

        @Node(wrap_to_async=False)
        def body():
            executed[0] = True

        comp = NATIVE_IF(ret_false, body).extract().render()
        await WorkflowInterpreter(comp).run()
        assert executed[0] is False

    @pytest.mark.asyncio
    async def test_if_else_true(self):
        if_done, else_done = [False], [False]

        @Node(wrap_to_async=False)
        def if_body():
            if_done[0] = True

        @Node(wrap_to_async=False)
        def else_body():
            else_done[0] = True

        comp = NATIVE_IF(ret_true, if_body).ELSE(else_body).extract().render()
        await WorkflowInterpreter(comp).run()
        assert if_done[0] is True
        assert else_done[0] is False

    @pytest.mark.asyncio
    async def test_if_else_false(self):
        if_done, else_done = [False], [False]

        @Node(wrap_to_async=False)
        def if_body():
            if_done[0] = True

        @Node(wrap_to_async=False)
        def else_body():
            else_done[0] = True

        comp = NATIVE_IF(ret_false, if_body).ELSE(else_body).extract().render()
        await WorkflowInterpreter(comp).run()
        assert if_done[0] is False
        assert else_done[0] is True

    @pytest.mark.asyncio
    async def test_if_elif_second_true(self):
        results = []

        @Node(wrap_to_async=False)
        def body1():
            results.append("if")

        @Node(wrap_to_async=False)
        def body2():
            results.append("elif")

        @Node(wrap_to_async=False)
        def body3():
            results.append("else")

        comp = (
            NATIVE_IF(ret_false, body1)
            .ELIF(ret_true, body2)
            .ELSE(body3)
            .extract()
            .render()
        )
        await WorkflowInterpreter(comp).run()
        assert results == ["elif"]

    @pytest.mark.asyncio
    async def test_if_bubble_body(self):
        results = []

        @Node(wrap_to_async=False)
        def step_a():
            results.append("a")

        @Node(wrap_to_async=False)
        def step_b():
            results.append("b")

        comp = NATIVE_IF(ret_true, NodeCompose(step_a, step_b)).extract().render()
        await WorkflowInterpreter(comp).run()
        assert results == ["a", "b"]

    @pytest.mark.asyncio
    async def test_if_bubble_else(self):
        results = []

        @Node(wrap_to_async=False)
        def if_a():
            results.append("if")

        @Node(wrap_to_async=False)
        def else_a():
            results.append("else")

        comp = (
            NATIVE_IF(ret_false, NodeCompose(if_a))
            .ELSE(NodeCompose(else_a))
            .extract()
            .render()
        )
        await WorkflowInterpreter(comp).run()
        assert results == ["else"]

    @pytest.mark.asyncio
    async def test_if_elif_bubble(self):
        results = []

        @Node(wrap_to_async=False)
        def body1():
            results.append("if")

        @Node(wrap_to_async=False)
        def body2():
            results.append("elif")

        comp = (
            NATIVE_IF(ret_false, NodeCompose(body1))
            .ELIF(ret_true, NodeCompose(body2))
            .extract()
            .render()
        )
        await WorkflowInterpreter(comp).run()
        assert results == ["elif"]


#  NATIVE_WHILE


class TestNativeWhile:
    @pytest.mark.asyncio
    async def test_while_false_skips(self):
        executed = [False]

        @Node(wrap_to_async=False)
        def body():
            executed[0] = True

        comp = NATIVE_WHILE(ret_false).ACTION(body).extract().render()
        await WorkflowInterpreter(comp).run()
        assert executed[0] is False

    @pytest.mark.asyncio
    async def test_while_three_iterations(self):
        counter = [0]

        @Node(wrap_to_async=False)
        def cond():
            return counter[0] < 3

        @Node(wrap_to_async=False)
        def body():
            counter[0] += 1

        comp = NATIVE_WHILE(cond).ACTION(body).extract().render()
        await WorkflowInterpreter(comp).run()
        assert counter[0] == 3

    @pytest.mark.asyncio
    async def test_while_bubble_body(self):
        counter = [0]

        @Node(wrap_to_async=False)
        def cond():
            return counter[0] < 2

        @Node(wrap_to_async=False)
        def step_a():
            counter[0] += 1

        @Node(wrap_to_async=False)
        def step_b():
            pass

        comp = NATIVE_WHILE(cond).ACTION(NodeCompose(step_a, step_b)).extract().render()
        await WorkflowInterpreter(comp).run()
        assert counter[0] == 2

    @pytest.mark.asyncio
    async def test_while_continues_after(self):
        results = []
        counter = [0]

        @Node(wrap_to_async=False)
        def cond():
            return counter[0] < 1

        @Node(wrap_to_async=False)
        def body():
            counter[0] += 1
            results.append("body")

        @Node(wrap_to_async=False)
        def after():
            results.append("after")

        comp = (NATIVE_WHILE(cond).ACTION(body) >> after).render()
        await WorkflowInterpreter(comp).run()
        assert results == ["body", "after"]


#  NATIVE_DO


class TestNativeDo:
    @pytest.mark.asyncio
    async def test_do_at_least_once(self):
        results = []

        @Node(wrap_to_async=False)
        def body():
            results.append("body")

        comp = NATIVE_DO(body).WHILE(ret_false).extract().render()
        await WorkflowInterpreter(comp).run()
        assert results == ["body"]

    @pytest.mark.asyncio
    async def test_do_three_iterations(self):
        counter = [0]

        @Node(wrap_to_async=False)
        def body():
            counter[0] += 1

        @Node(wrap_to_async=False)
        def cond():
            return counter[0] < 3

        comp = NATIVE_DO(body).WHILE(cond).extract().render()
        await WorkflowInterpreter(comp).run()
        assert counter[0] == 3

    @pytest.mark.asyncio
    async def test_do_bubble_body(self):
        counter = [0]

        @Node(wrap_to_async=False)
        def step_a():
            counter[0] += 1

        @Node(wrap_to_async=False)
        def step_b():
            pass

        @Node(wrap_to_async=False)
        def cond():
            return counter[0] < 2

        comp = NATIVE_DO(NodeCompose(step_a, step_b)).WHILE(cond).extract().render()
        await WorkflowInterpreter(comp).run()
        assert counter[0] == 2

    @pytest.mark.asyncio
    async def test_do_continues_after(self):
        results = []
        counter = [0]

        @Node(wrap_to_async=False)
        def body():
            counter[0] += 1
            results.append("body")

        @Node(wrap_to_async=False)
        def cond():
            return counter[0] < 2

        @Node(wrap_to_async=False)
        def after():
            results.append("after")

        comp = (NATIVE_DO(body).WHILE(cond) >> after).render()
        await WorkflowInterpreter(comp).run()
        assert results == ["body", "body", "after"]
