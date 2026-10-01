import asyncio

import pytest

from amrita_sense import WorkflowInterpreter
from amrita_sense.instructions.alias import ALIAS, AliasNode
from amrita_sense.instructions.ret2 import CALL
from amrita_sense.instructions.subprogram import ARCHIVED_NODES, INVOKE, InvokeNode
from amrita_sense.node.wrapper import Node as NodeDecorator
from amrita_sense.runtime.workflow import PC_CHECKPOINT


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


class TestAliasHookForwarding:
    """An alias forwards `__call__` at run time, so it must forward `_post_compile` too."""

    def test_aliased_invoke_resolves_its_target(self):
        """An aliased INVOKE still resolves its alias during rendering."""

        @NodeDecorator()
        def target():
            return "target"

        comp = ALIAS(INVOKE("sub"), "entry") >> ARCHIVED_NODES(ALIAS(target, "sub"))
        rendered = comp.render()
        node = rendered.calc.find_addr(rendered.alias2vector_map["entry"])
        assert isinstance(node, AliasNode)
        assert isinstance(node.node, InvokeNode)
        assert node.node._addr == rendered.alias2vector_map["sub"]

    @pytest.mark.asyncio
    async def test_aliased_call_trap_invokes_fn_and_returns(self):
        """An external trap on an aliased CALL runs the FN and resumes at current + 1."""
        from amrita_sense.instructions.func_block import FN

        log: list[str] = []

        @NodeDecorator()
        async def trap_point() -> None:
            log.append("trap_point")

        @NodeDecorator()
        async def main_step() -> None:
            log.append("main_step")

        @NodeDecorator()
        async def worker() -> None:
            log.append("worker")

        # FN renders as [_fn_escape, ALIAS(NOP, "worker_entry"), worker, RET()]
        worker_fn = FN("worker_entry", worker)
        traps = ARCHIVED_NODES(ALIAS(CALL("worker_entry"), "trap_entry"))

        comp = trap_point >> main_step >> traps >> worker_fn
        pc = WorkflowInterpreter(comp.render())

        task = asyncio.create_task(pc.run())
        await pc.object_io.wait_to_suspend(PC_CHECKPOINT)
        parked = pc._pointer.base_addr.copy()
        await pc.call_sub(
            pc.get_graph().calc.resolve_alias("trap_entry"), interrupt=True
        )
        pc.object_io.resume()
        await task

        # The trap consumes the parked cycle, then execution resumes at parked + 1.
        assert log == ["worker", "main_step"]
        assert parked == [0]
