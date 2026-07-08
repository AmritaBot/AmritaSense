"""09_interrupt_notice.py — INTERRUPT, INTERRUPT_KEEP_CTX, and InterruptKeepContext

Usage:
    python demos/09_interrupt_notice.py

Demonstrates three termination / pause mechanisms:
  1. INTERRUPT       — emergency stop (state cleared, irrecoverable)
  2. INTERRUPT_KEEP_CTX — pause with state preserved (recoverable)
  3. InterruptKeepContext raised from node code — same effect as (2)

IMPORTANT: InterruptNotice / InterruptKeepContext are caught by the
interpreter's main loop internally.  They do NOT propagate to the
caller of run().  Use interpreter.get_exception() or interpreter.is_running
to detect what happened.
"""

import asyncio

from amrita_sense import (
    INTERRUPT,
    Node,
    WorkflowInterpreter,
)
from amrita_sense.exceptions import InterruptKeepContext
from amrita_sense.instructions.workfl_ctrl import INTERRUPT_KEEP_CTX

# ---------------------------------------------------------------------------
# shared nodes
# ---------------------------------------------------------------------------


@Node()
async def step_a() -> None:
    print("  [A] First step — working")


@Node()
async def step_b() -> None:
    print("  [B] Second step — still working")


@Node()
async def this_wont_run() -> None:
    print("  [!] This line should NEVER appear (workflow already stopped)")


# ---------------------------------------------------------------------------
# Demo 1: INTERRUPT — emergency stop, state cleared
# ---------------------------------------------------------------------------


async def demo_interrupt() -> None:
    print("=== Demo 1: INTERRUPT instruction ===")

    comp = (step_a >> INTERRUPT >> this_wont_run).render()
    interpreter = WorkflowInterpreter(comp)

    await interpreter.run()
    # run() returns cleanly — no exception propagates on INTERRUPT
    print(f"  Interpreter is_running: {interpreter.is_running}")
    print("  ✓ Workflow exited cleanly (state cleared, irrecoverable)\n")


# ---------------------------------------------------------------------------
# Demo 2: INTERRUPT_KEEP_CTX — context-preserving pause
# ---------------------------------------------------------------------------


async def demo_keep_context() -> None:
    print("=== Demo 2: INTERRUPT_KEEP_CTX instruction ===")

    comp = (step_a >> step_b >> INTERRUPT_KEEP_CTX >> this_wont_run).render()
    interpreter = WorkflowInterpreter(comp)

    await interpreter.run()
    exc = interpreter.get_exception()
    exc_name = type(exc).__name__ if exc is not None else "(none)"
    print(f"  get_exception(): {exc_name}")
    print(f"  is_running: {interpreter.is_running}")
    print("  ✓ State preserved — call run() again to resume\n")


# ---------------------------------------------------------------------------
# Demo 3: raise InterruptKeepContext from node code
# ---------------------------------------------------------------------------


@Node()
async def guarded_work(pc: WorkflowInterpreter) -> None:
    print("  Working...")
    pc_dump = pc._pointer.copy() if pc._pointer else []
    print(f"  Pointer at: {pc_dump}")
    print("  Raising InterruptKeepContext from node code")
    raise InterruptKeepContext("condition-triggered-pause")


async def demo_raise_keep_context() -> None:
    print("=== Demo 3: raise InterruptKeepContext from node ===\n")

    comp = (guarded_work >> this_wont_run).render()
    interpreter = WorkflowInterpreter(comp)

    await interpreter.run()
    exc = interpreter.get_exception()
    exc_name = type(exc).__name__ if exc is not None else "(none)"
    print(f"  get_exception(): {exc_name}")
    print(f"  is_running: {interpreter.is_running}")
    print("  ✓ State preserved from node-level raise\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


async def main() -> None:
    await demo_interrupt()
    await demo_keep_context()
    await demo_raise_keep_context()


if __name__ == "__main__":
    asyncio.run(main())
