import pytest

from amrita_sense.node.core import NodeCompose
from amrita_sense.node.wrapper import Node as NodeDecorator
from amrita_sense.runtime.workflow import WorkflowInterpreter


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
