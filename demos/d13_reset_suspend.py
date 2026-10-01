"""d13_reset_suspend.py — RESET, SUSPEND, and InterruptKeepContext

Usage:
    python demos/d13_reset_suspend.py
    python -i demos/d13_reset_suspend.py   # same, then use `inter` / `suspend_inter` / `raise_inter` in the REPL

Demonstrates three termination / pause mechanisms:
  1. RESET            — emergency stop (state cleared, irrecoverable)
  2. SUSPEND          — pause with state preserved (recoverable)
  3. InterruptKeepContext raised from node code — same effect as (2)

IMPORTANT: InterruptNotice / InterruptKeepContext are caught by the
interpreter's main loop internally.  They do NOT propagate to the
caller of run().  Use interpreter.get_exception() or interpreter.is_running
to detect what happened.
"""

import asyncio

from amrita_sense import (
    RESET,
    Node,
    WorkflowInterpreter,
)
from amrita_sense.exceptions import InterruptKeepContext
from amrita_sense.instructions.workfl_ctrl import SUSPEND

# shared nodes


@Node()
async def step_a() -> None:
    print("  [A] First step — working")


@Node()
async def step_b() -> None:
    print("  [B] Second step — still working")


@Node()
async def this_wont_run() -> None:
    print("  [!] This line should NEVER appear (workflow already stopped)")


@Node()
async def guarded_work(pc: WorkflowInterpreter) -> None:
    print("  Working...")
    pc_dump = pc._pointer.copy() if pc._pointer else []
    print(f"  Pointer at: {pc_dump}")
    print("  Raising InterruptKeepContext from node code")
    raise InterruptKeepContext("condition-triggered-pause")


# Module-level so a REPL can drive all three; demo 1 is RESET — emergency stop, state cleared.
inter = WorkflowInterpreter((step_a >> RESET >> this_wont_run).render())

# Demo 2: SUSPEND — context-preserving pause.
suspend_inter = WorkflowInterpreter(
    (step_a >> step_b >> SUSPEND >> this_wont_run).render()
)

# Demo 3: raise InterruptKeepContext from node code.
raise_inter = WorkflowInterpreter((guarded_work >> this_wont_run).render())


async def demo_interrupt() -> None:
    print("=== Demo 1: RESET instruction ===")

    await inter.run()
    # run() returns cleanly — no exception propagates on RESET
    print(f"  Interpreter is_running: {inter.is_running}")
    print("  ✓ Workflow exited cleanly (state cleared, irrecoverable)\n")


async def demo_keep_context() -> None:
    print("=== Demo 2: SUSPEND instruction ===")

    await suspend_inter.run()
    exc = suspend_inter.get_exception()
    exc_name = type(exc).__name__ if exc is not None else "(none)"
    print(f"  get_exception(): {exc_name}")
    print(f"  is_running: {suspend_inter.is_running}")
    print("  ✓ State preserved — call run() again to resume\n")


async def demo_raise_keep_context() -> None:
    print("=== Demo 3: raise InterruptKeepContext from node ===\n")

    await raise_inter.run()
    exc = raise_inter.get_exception()
    exc_name = type(exc).__name__ if exc is not None else "(none)"
    print(f"  get_exception(): {exc_name}")
    print(f"  is_running: {raise_inter.is_running}")
    print("  ✓ State preserved from node-level raise\n")


async def main() -> None:
    await demo_interrupt()
    await demo_keep_context()
    await demo_raise_keep_context()


if __name__ == "__main__":
    asyncio.run(main())
