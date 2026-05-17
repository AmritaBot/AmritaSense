from amrita_sense.node.core import BaseNode, Node, NodeCompose, NodeComposeRendered
from amrita_sense.node.wrapper import Node as NodeDecorator


class TestBaseNode:
    """Test cases for the BaseNode class."""

    def test_base_node_direct_instantiation(self):
        """Test that BaseNode can be instantiated directly with required parameters."""
        import inspect

        def dummy_func():
            return "dummy"

        frame = inspect.currentframe()
        node = BaseNode()
        node._init(
            func=dummy_func,
            tag="test_node",
            wrap_to_async=True,
            address_able=False,
            frame=frame,
        )

        assert node.func == dummy_func
        assert node.tag == "test_node"
        assert node.wrap_to_async is True
        assert node.address_able is False


class TestNode:
    """Test cases for the Node class."""

    def test_node_creation_with_decorator(self):
        """Test creating a Node using the @Node decorator."""

        @NodeDecorator()
        def simple_function():
            return 42

        assert isinstance(simple_function, Node)
        assert simple_function() == 42

    def test_node_creation_with_parameters(self):
        """Test creating a Node with custom parameters."""

        @NodeDecorator(tag="custom_tag", wrap_to_async=False, address_able=True)
        def parameterized_function(x: int) -> int:
            return x * 2

        node = parameterized_function
        assert node.tag == "custom_tag"
        assert node.wrap_to_async is False
        assert node.address_able is True
        assert node(5) == 10

    def test_node_with_arguments(self):
        """Test Node execution with arguments."""

        @NodeDecorator()
        def function_with_args(a: int, b: str = "default") -> str:
            return f"{a}:{b}"

        result = function_with_args(42, "test")
        assert result == "42:test"

        result_default = function_with_args(42)
        assert result_default == "42:default"


class TestNodeCompose:
    """Test cases for the NodeCompose class."""

    def test_node_compose_creation(self):
        """Test creating a NodeCompose with multiple nodes."""

        @NodeDecorator()
        def node1():
            return "node1"

        @NodeDecorator()
        def node2():
            return "node2"

        compose = NodeCompose(node1, node2)
        assert len(compose._graph) == 2
        assert compose._graph[0] is node1
        assert compose._graph[1] is node2

    def test_node_compose_empty(self):
        """Test creating an empty NodeCompose."""
        compose = NodeCompose()
        assert len(compose._graph) == 0

    def test_node_compose_render(self):
        """Test that NodeCompose can be rendered."""

        @NodeDecorator()
        def test_node():
            return "test"

        compose = NodeCompose(test_node)
        rendered = compose.render()
        assert isinstance(rendered, NodeComposeRendered)


class TestNodeComposeRendered:
    """Test cases for the NodeComposeRendered class."""

    def test_node_compose_rendered_creation(self):
        """Test creating a NodeComposeRendered instance via render()."""

        @NodeDecorator()
        def test_node():
            return "test"

        workflow = NodeCompose(test_node)
        rendered = workflow.render()

        rendered.alias2vector_map
