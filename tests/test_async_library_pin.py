"""The interpreter pins aiologic's async-library detection for the duration of a run.

`aiologic.Lock` otherwise re-detects the running async library on every
operation, and the interpreter takes a lock on every step.  The pin caches an
answer that the probe would have returned anyway, so the only thing worth
asserting is that it is set inside a run and cleared afterwards.
"""

import pytest
from aiologic.lowlevel import current_async_library_tlocal

from amrita_sense import NOP, WorkflowInterpreter
from amrita_sense.node.wrapper import Node as NodeDecorator

observed: list[str | None] = []


@NodeDecorator()
async def _observe() -> None:
    observed.append(current_async_library_tlocal.name)


@pytest.mark.asyncio
async def test_library_is_pinned_while_running() -> None:
    observed.clear()
    inter = WorkflowInterpreter((NOP >> _observe).render())

    await inter.run()

    assert observed == ["asyncio"]


@pytest.mark.asyncio
async def test_library_pin_is_restored_afterwards() -> None:
    assert current_async_library_tlocal.name is None

    inter = WorkflowInterpreter((NOP >> _observe).render())
    await inter.run()

    assert current_async_library_tlocal.name is None


@pytest.mark.asyncio
async def test_library_pin_survives_a_failing_run() -> None:
    @NodeDecorator()
    async def _boom() -> None:
        raise ValueError("boom")

    inter = WorkflowInterpreter(_boom.as_compose().render())

    try:
        await inter.run()
    except ValueError:
        pass

    assert current_async_library_tlocal.name is None


@pytest.mark.asyncio
async def test_library_pin_keeps_an_existing_value() -> None:
    """A value set by an outer scope survives the run unchanged."""
    current_async_library_tlocal.name = "asyncio"
    try:
        inter = WorkflowInterpreter((NOP >> _observe).render())
        await inter.run()
        assert current_async_library_tlocal.name == "asyncio"
    finally:
        current_async_library_tlocal.name = None
