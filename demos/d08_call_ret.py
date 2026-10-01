"""d08_call_ret.py — CALL + RET modern function-call pattern

Usage:
    python demos/d08_call_ret.py
    python -i demos/d08_call_ret.py   # same, then use `inter` directly in the REPL

CALL(to_adr) combines PUSH_RET + JMP:
  - from_adr=None in the main flow: the current pointer is pushed, so
    RET() rebases there and the interpreter advances onto the next
    node (after_return).
  - The function body lives in an ARCHIVED_SEGMENT (skipped by normal
    flow, entered via the jump) and ends with RET().
"""

import asyncio

from amrita_sense import ALIAS, Node, WorkflowInterpreter
from amrita_sense.instructions.ret2 import CALL, RET
from amrita_sense.instructions.subprogram import ARCHIVED_SEGMENT


@Node()
async def start() -> None:
    print("Start")


@Node()
async def doing_work() -> None:
    """The function body we jump into."""
    print("  Doing work in the called section")


@Node()
async def after_return() -> None:
    """RET rebases to the caller; advance lands here."""
    print("Back here (popped via RET)")


# Pattern: CALL(entry) -> body -> RET() — 1) pushes the current pointer and jumps into the archived segment; 2) the ALIAS proxy executes doing_work, then RET() pops the saved address, rebases there, and the interpreter advances onto after_return.
composition = (
    start
    >> CALL("doing_work")
    >> after_return
    >> ARCHIVED_SEGMENT(ALIAS(doing_work, "doing_work") >> RET())
)
# Module-level so a REPL can `from demos.d08_call_ret import inter` and step across the CALL/RET boundary.
inter = WorkflowInterpreter(composition.render())


async def main() -> None:
    print("=== CALL + RET example ===")
    await inter.run()


if __name__ == "__main__":
    asyncio.run(main())
