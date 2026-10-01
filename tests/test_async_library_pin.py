"""The interpreter pins aiologic's async-library detection for the duration of a run.

`aiologic.Lock` otherwise re-detects the running async library on every
operation, and the interpreter takes a lock on every step.  The pin caches an
answer that the probe would have returned anyway, so the only thing worth
asserting is that it is set inside a run and cleared afterwards.
"""

import asyncio

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


@pytest.mark.asyncio
async def test_concurrent_runs_leave_no_pin_behind() -> None:
    """Two runs sharing the loop must not restore each other out of order."""
    first = WorkflowInterpreter((NOP >> _observe >> NOP).render())
    second = WorkflowInterpreter((NOP >> _observe >> NOP).render())

    await asyncio.gather(first.run(), second.run())

    assert current_async_library_tlocal.name is None


@pytest.mark.asyncio
async def test_pin_survives_another_run_finishing_first() -> None:
    """A run that outlives another keeps its pin until it finishes itself."""
    seen: list[str | None] = []

    @NodeDecorator()
    async def _slow_probe() -> None:
        await asyncio.sleep(0.02)
        seen.append(current_async_library_tlocal.name)

    slow = WorkflowInterpreter(_slow_probe.as_compose().render())
    quick = WorkflowInterpreter((NOP >> NOP).render())

    slow_task = asyncio.create_task(slow.run())
    await asyncio.sleep(0.01)  # let the slow run take the pin

    await quick.run()  # takes and releases the pin around the slow one

    assert current_async_library_tlocal.name == "asyncio"
    await slow_task

    assert seen == ["asyncio"]
    assert current_async_library_tlocal.name is None
