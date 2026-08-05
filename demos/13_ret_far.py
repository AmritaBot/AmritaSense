"""13_ret_far.py — PUSH_AND_GOTO + RET_FAR modern function-call pattern

Usage:
    python demos/13_ret_far.py

PUSH_AND_GOTO(from_adr, to_adr) combines PUSH_STACK + GOTO:
  - from_adr=None in the main flow: the current pointer is pushed, so
    RET_FAR() rebases there and the interpreter advances onto the next
    node (after_return).
  - The function body lives in an ARCHIVED_SEGMENT (skipped by normal
    flow, entered via the jump) and ends with RET_FAR().
"""

import asyncio

from amrita_sense import ALIAS, Node, WorkflowInterpreter
from amrita_sense.instructions.ret2 import PUSH_AND_GOTO, RET_FAR
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
    """RET_FAR rebases to the caller; advance lands here."""
    print("Back here (popped via RET_FAR)")


async def main() -> None:
    print("=== PUSH_AND_GOTO + RET_FAR example ===")
    # Pattern: PUSH_AND_GOTO(None, entry) -> body -> RET_FAR()
    #   1) PUSH_AND_GOTO(None, "doing_work") pushes the current pointer
    #      and jumps into the archived segment
    #   2) The ALIAS proxy executes doing_work, then RET_FAR() pops the
    #      saved address, rebases the pointer there, and the interpreter
    #      advances onto after_return
    comp = (
        start
        >> PUSH_AND_GOTO(None, "doing_work")
        >> after_return
        >> ARCHIVED_SEGMENT(ALIAS(doing_work, "doing_work") >> RET_FAR())
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
