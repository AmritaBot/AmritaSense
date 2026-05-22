from typing import Any

import pytest

from amrita_sense.exceptions import (
    DependsInjectFailed,
    DependsResolveFailed,
    InterruptNotice,
    NullPointerException,
)
from amrita_sense.hook.matcher import DependsFactory, FailedEnum, MatcherFactory
from amrita_sense.node.core import NodeCompose
from amrita_sense.node.wrapper import Node as NodeDecorator
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


class TestWorkflowInterpreter:
    """Test cases for the WorkflowInterpreter class."""

    @pytest.mark.asyncio
    async def test_interpreter_basic_execution(self):
        """Test basic workflow execution."""

        @NodeDecorator()
        def simple_node():
            return "hello"

        workflow = NodeCompose(simple_node)
        rendered = workflow.render()
        interpreter = WorkflowInterpreter(rendered)

        await interpreter.run()

    @pytest.mark.asyncio
    async def test_interpreter_sequential_execution(self):
        """Test sequential execution of multiple nodes."""
        results = []

        @NodeDecorator()
        def node1():
            results.append("first")
            return 1

        @NodeDecorator()
        def node2():
            results.append("second")
            return 2

        @NodeDecorator()
        def node3():
            results.append("third")
            return 3

        workflow = NodeCompose(node1, node2, node3)
        rendered = workflow.render()
        interpreter = WorkflowInterpreter(rendered)

        await interpreter.run()
        assert results == ["first", "second", "third"]

    def test_interpreter_get_graph(self):
        """Test getting the workflow graph from interpreter."""

        @NodeDecorator()
        def test_node():
            return "test"

        workflow = NodeCompose(test_node)
        rendered = workflow.render()
        interpreter = WorkflowInterpreter(rendered)

        graph = interpreter.get_graph()
        assert graph is rendered

    @pytest.mark.asyncio
    async def test_run_step_by_runtime_args_unresolved_raises(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(simple_node).render()
        interpreter = WorkflowInterpreter(rendered)
        interpreter._ava_args = (interpreter, DependsFactory(lambda: None))

        original = MatcherFactory._do_runtime_resolve

        async def _fake_runtime_resolve(*args: Any, **kwargs: Any) -> bool:
            return False

        MatcherFactory._do_runtime_resolve = classmethod(_fake_runtime_resolve)  # pyright: ignore[reportAttributeAccessIssue]
        try:
            with pytest.raises(
                RuntimeError, match="Runtime arguments cannot be resolved"
            ):
                await interpreter.run_step_by().__anext__()
        finally:
            MatcherFactory._do_runtime_resolve = original

    @pytest.mark.asyncio
    async def test_run_step_by_interrupt_notice_clears_state(self):
        @NodeDecorator()
        def interrupt_node():
            raise InterruptNotice("stop")

        rendered = NodeCompose(interrupt_node).render()
        interpreter = WorkflowInterpreter(rendered)

        with pytest.raises(StopAsyncIteration):
            await interpreter.run_step_by().__anext__()

        assert not interpreter._pointer
        assert not interpreter._ret_addr_stack
        assert not interpreter._jump_marked

    @pytest.mark.asyncio
    async def test_call_raises_depends_resolve_failed(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(simple_node).render()
        interpreter = WorkflowInterpreter(rendered)

        original = MatcherFactory._resolve_dependencies
        MatcherFactory._resolve_dependencies = classmethod(
            lambda *args, **kwargs: (FailedEnum.RESOLVE_FAILED, {}, {})  # pyright: ignore[reportAttributeAccessIssue]
        )
        try:
            with pytest.raises(DependsResolveFailed):
                await interpreter._call()
        finally:
            MatcherFactory._resolve_dependencies = original

    @pytest.mark.asyncio
    async def test_call_raises_depends_inject_failed(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(simple_node).render()
        interpreter = WorkflowInterpreter(rendered)

        original_resolve = MatcherFactory._resolve_dependencies
        original_runtime = MatcherFactory._do_runtime_resolve
        MatcherFactory._resolve_dependencies = classmethod(
            lambda *args, **kwargs: (None, {}, {"x": DependsFactory(lambda: None)})  # pyright: ignore[reportAttributeAccessIssue]
        )

        async def _fake_runtime_resolve(*args: Any, **kwargs: Any) -> bool:
            return False

        MatcherFactory._do_runtime_resolve = classmethod(_fake_runtime_resolve)  # pyright: ignore[reportAttributeAccessIssue]
        try:
            with pytest.raises(DependsInjectFailed):
                await interpreter._call()
        finally:
            MatcherFactory._resolve_dependencies = original_resolve
            MatcherFactory._do_runtime_resolve = original_runtime

    @pytest.mark.asyncio
    async def test_call_uses_async_and_sync_no_wrap(self):
        @NodeDecorator(wrap_to_async=False)
        async def async_node():
            return "async"

        @NodeDecorator(wrap_to_async=False)
        def sync_node():
            return "sync"

        rendered_async = NodeCompose(async_node).render()
        interpreter_async = WorkflowInterpreter(rendered_async)
        interpreter_async._pointer = PointerVector([0])
        assert await interpreter_async._call() == "async"

        rendered_sync = NodeCompose(sync_node).render()
        interpreter_sync = WorkflowInterpreter(rendered_sync)
        interpreter_sync._pointer = PointerVector([0])
        assert await interpreter_sync._call() == "sync"

    def test_find_addr_or_none_returns_none_for_invalid_path(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(simple_node).render()
        interpreter = WorkflowInterpreter(rendered)

        assert interpreter._find_addr_or_none([0, 0, 0]) is None

    def test_advance_pointer_container_sibling_and_nested(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(simple_node, NodeCompose(simple_node)).render()
        interpreter = WorkflowInterpreter(rendered)
        interpreter._pointer = PointerVector([0])

        assert interpreter._advance_pointer()
        assert interpreter._pointer == PointerVector([1, 0])

    def test_advance_pointer_backtrack_to_nested_sibling(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(
            NodeCompose(simple_node), NodeCompose(simple_node)
        ).render()
        interpreter = WorkflowInterpreter(rendered)
        interpreter._pointer = PointerVector([0, 0])

        assert interpreter._advance_pointer()
        assert interpreter._pointer == PointerVector([1, 0])

    @pytest.mark.asyncio
    async def test_call_offset_and_call_near_preserve_pointer(self):
        @NodeDecorator()
        def target_node():
            return "target"

        workflow = NodeCompose(target_node, target_node)
        rendered = workflow.render()
        interpreter = WorkflowInterpreter(rendered)

        interpreter._pointer = PointerVector([0])
        result = await interpreter.call_offset(1)
        assert result == "target"
        assert interpreter._pointer == PointerVector([0])

        interpreter._pointer = PointerVector([0])
        result = await interpreter.call_near(1)
        assert result == "target"
        assert interpreter._pointer == PointerVector([0])

    def test_jump_methods_modify_pointer_and_raise(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        interpreter = WorkflowInterpreter(NodeCompose(simple_node).render())
        interpreter._pointer = PointerVector([1, 2])

        interpreter.jump_to_top(0)
        assert interpreter._pointer == PointerVector([0])

        interpreter = WorkflowInterpreter(NodeCompose(simple_node).render())
        interpreter._pointer = PointerVector([1, 2])
        interpreter.jump_offset_top(1)
        assert interpreter._pointer == PointerVector([2])

        interpreter = WorkflowInterpreter(NodeCompose(simple_node).render())
        interpreter._pointer = PointerVector([1, 2])
        interpreter.jump_far_ptr([0, 1])
        assert interpreter._pointer == PointerVector([0, 1])

        interpreter = WorkflowInterpreter(NodeCompose(simple_node).render())
        with pytest.raises(NullPointerException):
            interpreter.jump_to([99])

    @pytest.mark.asyncio
    async def test_call_raises_on_nodecompose(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(NodeCompose(simple_node)).render()
        interpreter = WorkflowInterpreter(rendered)
        interpreter._pointer = PointerVector([0])

        with pytest.raises(RuntimeError):
            await interpreter._call()

    def test_advance_pointer_empty_and_invalid(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        interpreter = WorkflowInterpreter(NodeCompose(simple_node).render())
        interpreter._pointer = PointerVector()
        assert not interpreter._advance_pointer()

        interpreter._pointer = PointerVector([0, 0])
        assert not interpreter._advance_pointer()

    def test_advance_pointer_nested_and_backtrack(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(NodeCompose(simple_node), simple_node).render()
        interpreter = WorkflowInterpreter(rendered)

        interpreter._pointer = PointerVector([0])
        assert interpreter._advance_pointer()
        assert interpreter._pointer == PointerVector([0, 0])

        interpreter._pointer = PointerVector([0, 0])
        assert interpreter._advance_pointer()
        assert interpreter._pointer == PointerVector([1])

    def test_advance_pointer_backtrack_from_nested_end(self):
        @NodeDecorator()
        def simple_node():
            return "hello"

        rendered = NodeCompose(NodeCompose(simple_node)).render()
        interpreter = WorkflowInterpreter(rendered)
        interpreter._pointer = PointerVector([0, 0])

        assert not interpreter._advance_pointer()
