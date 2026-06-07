"""Tests for func_block.py — FUN_BLOCK instruction and FuncBlock node."""

import pytest

from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions.func_block import FUN_BLOCK, FuncBlock
from amrita_sense.node.core import NodeComposeRendered
from amrita_sense.runtime.workflow import UNSET


@Node()
async def sub_start() -> None:
    pass


@Node()
async def sub_end() -> None:
    pass


def _render_sub() -> NodeComposeRendered:
    return (sub_start >> sub_end >> ALIAS(NOP, "done")).render()


@Node()
async def main_start() -> None:
    pass


@Node()
async def main_after() -> None:
    pass


@Node()
async def main_end() -> None:
    pass


# -- Unit tests ---------------------------------------------------------------


def test_fun_block_returns_funcblock():
    fb = FUN_BLOCK(_render_sub(), middleware=None)
    assert isinstance(fb, FuncBlock)
    assert fb._comp_rendered is not None
    assert fb._onetime is False
    assert fb._mdw is None


def test_fun_block_one_time():
    fb = FUN_BLOCK(_render_sub(), middleware=None, one_time_interp=True)
    assert fb._onetime is True


def test_fun_block_default_middleware():
    fb = FUN_BLOCK(_render_sub())
    assert fb._mdw is UNSET


def test_fun_block_node_attrs():
    fb = FUN_BLOCK(_render_sub(), middleware=None)
    assert hasattr(fb, "tag")
    assert hasattr(fb, "func")
    assert fb.wrap_to_async is False
    assert fb.address_able is True


# -- Integration tests --------------------------------------------------------


@pytest.mark.asyncio
async def test_fun_block_basic_execution():
    comp = main_start >> FUN_BLOCK(_render_sub(), middleware=None) >> ALIAS(NOP, "done")
    await WorkflowInterpreter(comp.render()).run()


@pytest.mark.asyncio
async def test_fun_block_one_time_interp():
    comp = (
        main_start
        >> FUN_BLOCK(_render_sub(), middleware=None, one_time_interp=True)
        >> FUN_BLOCK(_render_sub(), middleware=None, one_time_interp=True)
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(comp.render()).run()


@pytest.mark.asyncio
async def test_fun_block_reusable():
    comp = (
        main_start
        >> FUN_BLOCK(_render_sub(), middleware=None, one_time_interp=False)
        >> FUN_BLOCK(_render_sub(), middleware=None, one_time_interp=False)
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(comp.render()).run()


@pytest.mark.asyncio
async def test_fun_block_error_propagation():
    @Node()
    async def fail_node() -> None:
        raise ValueError("boom")

    failing_comp = (sub_start >> fail_node >> ALIAS(NOP, "done")).render()

    comp = (
        main_start
        >> FUN_BLOCK(failing_comp, middleware=None, one_time_interp=True)
        >> ALIAS(NOP, "done")
    )
    with pytest.raises(ValueError, match="boom"):
        await WorkflowInterpreter(comp.render()).run()


@pytest.mark.asyncio
async def test_fun_block_in_composition_chain():
    comp = (
        main_start
        >> FUN_BLOCK(_render_sub(), middleware=None, one_time_interp=True)
        >> main_after
        >> FUN_BLOCK(_render_sub(), middleware=None, one_time_interp=True)
        >> main_end
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(comp.render()).run()
