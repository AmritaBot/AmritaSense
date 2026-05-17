from amrita_sense.instructions.alias import ALIAS, AliasNode
from amrita_sense.node.wrapper import Node as NodeDecorator


class TestAliasNode:
    """Test cases for the AliasNode class."""

    def test_alias_node_creation(self):
        """Test creating an AliasNode with a wrapped node."""

        @NodeDecorator()
        def original_node():
            return "original"

        alias_node = AliasNode(original_node, "my_alias")

        assert alias_node.node is original_node
        assert alias_node.alias == "my_alias"
        assert alias_node.address_able is True

    def test_alias_node_execution(self):
        """Test that AliasNode executes the wrapped node correctly."""

        @NodeDecorator()
        def original_node():
            return "wrapped_result"

        alias_node = AliasNode(original_node, "test_alias")
        result = alias_node()
        assert result == "wrapped_result"

    def test_alias_node_with_arguments(self):
        """Test AliasNode execution with arguments."""

        @NodeDecorator()
        def original_node(x: int, y: str) -> str:
            return f"{x}:{y}"

        alias_node = AliasNode(original_node, "arg_alias")
        result = alias_node(42, "test")
        assert result == "42:test"


class TestALIAS:
    """Test cases for the ALIAS instruction."""

    def test_alias_instruction_creation(self):
        """Test creating an ALIAS instruction."""

        @NodeDecorator()
        def target_node():
            return "target"

        alias_instruction = ALIAS(target_node, "my_alias_name")

        assert isinstance(alias_instruction, AliasNode)
        assert alias_instruction.alias == "my_alias_name"
        assert alias_instruction.node is target_node
