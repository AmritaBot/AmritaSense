"""25_call_trap.py — External trap: call_sub → CALL → FN → RET → resume

Usage:
    python demos/25_call_trap.py

An external caller can fire `call_sub(..., interrupt=True)` at a running
interpreter and make it enter a `CALL` node that lives in an
`ARCHIVED_NODES` library.  That `CALL` then enters a regular `FN` block,
which returns through `RET`, and the interpreter resumes at
**parked address + 1**.

Contrast with the flat jump-around style: the trap target is a real
`CALL` node, so the whole call/return chain is expressed by the
instructions themselves — nothing has to know the return address.
"""

import asyncio

from amrita_sense import ALIAS, Node, WorkflowInterpreter
from amrita_sense.instructions import CALL, FN
from amrita_sense.instructions.subprogram import ARCHIVED_NODES
from amrita_sense.runtime.workflow import PC_CHECKPOINT


@Node()
async def trap_point() -> None:
    print("[main] trap_point  <- parked here; the trap consumes this cycle")


@Node()
async def main_step() -> None:
    print("[main] main_step")


@Node()
async def main_tail() -> None:
    print("[main] main_tail")


@Node()
async def worker_a() -> None:
    print("  [worker] a")


@Node()
async def worker_b() -> None:
    print("  [worker] b")


async def main() -> None:
    print("=== external trap: CALL -> FN -> RET ===\n")

    # FN block: [_fn_escape, ALIAS(NOP, "worker_entry"), worker_a, worker_b, RET()]
    worker = FN("worker_entry", worker_a >> worker_b)

    # Trap library: skipped by normal flow, entered only via call_sub(interrupt=True); the trap target is the CALL node itself.
    traps = ARCHIVED_NODES(ALIAS(CALL("worker_entry"), "trap_entry"))

    comp = trap_point >> main_step >> main_tail >> traps >> worker
    pc = WorkflowInterpreter(comp.render())

    task = asyncio.create_task(pc.run())

    # Park the interpreter on a node boundary so the lock is free.
    await pc.object_io.wait_to_suspend(PC_CHECKPOINT)
    print(f"[ext]  parked at {pc._pointer}, is_running = {pc.is_running}")

    # Fire the trap: call_sub pushes the parked address, then the CALL node pushes its own address and jumps into the FN block.
    await pc.call_sub(pc.get_graph().calc.resolve_alias("trap_entry"), interrupt=True)
    pc.object_io.resume()
    await task

    print("\n[ext]  done — the parked node was consumed, flow resumed at parked + 1")


if __name__ == "__main__":
    asyncio.run(main())
