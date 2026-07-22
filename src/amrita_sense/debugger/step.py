"""Step-by-step execution control for the AmritaSense debugger.

Two API flavours are provided:

* **sync**  (``step``, ``step_over``, ``step_out``, ``cont``) —
  callable directly in a Python REPL **without** ``await``.  Each wraps
  ``asyncio.run()`` internally and catches ``BreakpointHit`` /
  ``KeyboardInterrupt`` so the REPL stays clean.

* **async** (``step_async``, ``step_over_async``, …) —
  the raw async implementations for use inside an existing event loop.

Both sets are exported from ``amrita_sense.debugger``.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from amrita_sense.debugger.breakpoint import BreakpointHit, _get_state
from amrita_sense.runtime.workflow import PC_CHECKPOINT

if TYPE_CHECKING:
    from amrita_sense.runtime.workflow import WorkflowInterpreter
    from amrita_sense.streaming import SuspendObjectStream


# Internal async primitive


async def _step_one(inter: WorkflowInterpreter[SuspendObjectStream]) -> None:
    """Execute exactly **one** node using direct ``_call()`` + lock."""
    # --- recover from panic (mimics run_step_by preamble) ---
    if inter._panic_exc is not None:
        inter._panic_exc = None

    # --- per-node suspension check ---
    await inter.object_io._wait_for_continue(PC_CHECKPOINT)

    # --- initialise pointer if empty ---
    if not inter._pointer:
        if not inter.get_graph():
            return
        inter._pointer.append(0)

    # --- execute ONE node with lock ---
    try:
        async with inter._interpret_lock:
            if inter._middleware is not None:
                await inter._middleware(inter)
            else:
                await inter._call(no_cache=True)

            # advance pointer (unless a jump was performed)
            if inter._jump_marked:
                inter._jump_marked = False
            else:
                inter.advance_pointer()
    except Exception as e:
        # Save panic state (mimics run_step_by's exception handling)
        inter._panic_exc = e
        raise


# Async API  (step_async, step_over_async, …)


async def step_async(inter: WorkflowInterpreter[SuspendObjectStream]) -> None:
    """Execute exactly **one** node and stop (async).

    Breakpoints are **skipped** during stepping (the ``stepping`` flag
    is set, so the composite middleware only checks breakpoints during
    ``cont_async()``).
    """
    state = _get_state(inter)
    state["stepping"] = True
    try:
        await _step_one(inter)
    except BreakpointHit as bp:
        print(f"⏸️  Breakpoint (unexpected during step): {bp.bp}")
    except KeyboardInterrupt:
        print(f"⏸️  Stop at: {inter._pointer.base_addr}")
    finally:
        state["stepping"] = False


async def step_over_async(inter: WorkflowInterpreter[SuspendObjectStream]) -> None:
    """Execute nodes until the return-address stack depth ≤ current (async)."""
    base_depth = len(inter._ret_addr_stack)
    try:
        await step_async(inter)
        while len(inter._ret_addr_stack) > base_depth:
            await step_async(inter)
    except KeyboardInterrupt:
        print(f"⏸️  Stop at: {inter._pointer.base_addr}")


async def step_out_async(inter: WorkflowInterpreter) -> None:
    """Execute nodes until the return-address stack becomes shallower (async)."""
    base_depth = len(inter._ret_addr_stack)
    try:
        while len(inter._ret_addr_stack) >= base_depth:
            if not inter._pointer:
                break
            await step_async(inter)
    except KeyboardInterrupt:
        print(f"⏸️  Stop at: {inter._pointer.base_addr}")


async def cont_async(inter: WorkflowInterpreter[SuspendObjectStream]) -> None:
    """Continue until a breakpoint or workflow end (async).

    Breakpoints are active — the ``stepping`` flag is cleared.
    """
    state = _get_state(inter)
    state["stepping"] = False
    try:
        async for _ in inter.run_step_by():
            pass
    except BreakpointHit as bp:
        print(f"⏸️  Hit breakpoint: {bp.bp}")
    except KeyboardInterrupt:
        print(f"⏸️  Stop at: {inter._pointer.base_addr}")


# Sync API  (step, step_over, step_out, cont)


def _run_sync(coro, inter: WorkflowInterpreter) -> None:
    """Run *coro* synchronously.  Only ``BreakpointHit`` and
    ``KeyboardInterrupt`` are caught & printed; other exceptions
    propagate so the user can see the real error."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        #  no running loop
        _do(asyncio.run, coro, inter)
    else:
        #  loop already running
        exc: list[BaseException] = []

        def _in_thread() -> None:
            try:
                asyncio.run_coroutine_threadsafe(coro, loop).result()
            except BaseException as e:
                exc.append(e)

        t = threading.Thread(target=_in_thread, daemon=True)
        t.start()
        t.join()
        if exc:
            e = exc[0]
            if isinstance(e, BreakpointHit):
                print(f"⏸️  Hit breakpoint: {e.bp}")
            elif isinstance(e, KeyboardInterrupt):
                print(f"⏸️  Stop at: {inter._pointer.base_addr}")
            elif isinstance(e, Exception):
                print(f"⚠️  Node crashed: {e!r}. Panic saved, use inspect().")
            else:
                raise e


def _do(runner, coro, inter: WorkflowInterpreter) -> None:
    try:
        runner(coro)
    except BreakpointHit as bp:
        print(f"⏸️  Hit breakpoint: {bp.bp}")
    except KeyboardInterrupt:
        print(f"⏸️  Stop at: {inter._pointer.base_addr}")
    except Exception as e:
        print(f"⚠️  Node crashed: {e!r}. Panic saved, use inspect().")


def step(inter: WorkflowInterpreter) -> None:
    """Execute exactly **one** node and stop (sync)."""
    _run_sync(step_async(inter), inter)


def step_over(inter: WorkflowInterpreter) -> None:
    """Step over subroutine calls (sync, REPL-safe)."""
    _run_sync(step_over_async(inter), inter)


def step_out(inter: WorkflowInterpreter) -> None:
    """Run to end of current frame (sync, REPL-safe)."""
    _run_sync(step_out_async(inter), inter)


def cont(inter: WorkflowInterpreter) -> None:
    """Continue to next breakpoint or workflow end (sync, REPL-safe)."""
    _run_sync(cont_async(inter), inter)
