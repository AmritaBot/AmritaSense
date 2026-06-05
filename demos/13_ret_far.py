"""13_ret_far.py — PUSH_STACK + GOTO + RET_FAR pop-and-return

Usage:
    python demos/13_ret_far.py
"""

import asyncio

from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, PUSH_STACK, RET_FAR


@Node()
async def start() -> None:
    print("Start")


@Node()
async def doing_work() -> None:
    """The section we GOTO into."""
    print("  Doing work in the jumped-to section")


@Node()
async def after_return() -> None:
    """RET_FAR pops _ret_addr_stack and jumps here."""
    print("Back here (popped via RET_FAR)")


async def main() -> None:
    print("=== PUSH_STACK + GOTO + RET_FAR example ===")
    # Pattern: PUSH_STACK → GOTO → RET_FAR pop-and-return
    #   1) PUSH_STACK("after") pushes "after" address onto _ret_addr_stack
    #   2) GOTO("work") jumps to the work section
    #   3) RET_FAR() pops the saved address and jumps back
    comp = (
        start
        >> PUSH_STACK("after")
        >> GOTO("work")
        >> ALIAS(after_return, "after")
        >> GOTO("end")
        >> ALIAS(doing_work, "work")
        >> RET_FAR()
        >> ALIAS(NOP, "end")
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
