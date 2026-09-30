"""13_ret_far.py — CALL + RET modern function-call pattern

Usage:
    python demos/13_ret_far.py

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


async def main() -> None:
    print("=== CALL + RET example ===")
    # Pattern: CALL(entry) -> body -> RET() — 1) pushes the current pointer and jumps into the archived segment; 2) the ALIAS proxy executes doing_work, then RET() pops the saved address, rebases there, and the interpreter advances onto after_return
    comp = (
        start
        >> CALL("doing_work")
        >> after_return
        >> ARCHIVED_SEGMENT(ALIAS(doing_work, "doing_work") >> RET())
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
