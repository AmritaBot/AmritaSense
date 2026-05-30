"""13_ret_far.py — Manual push + GOTO + RET_FAR pop-and-return

Usage:
    python demos/13_ret_far.py
"""

import asyncio

from amrita_sense import ALIAS, NOP, Node, PointerVector, WorkflowInterpreter
from amrita_sense.instructions import GOTO, RET_FAR


@Node()
async def start() -> None:
    print("Start")


@Node()
async def save_ret_addr(pc: WorkflowInterpreter) -> None:
    """Manually push a return destination onto _ret_addr_stack."""
    print("  Saving return address...")
    return_dest = PointerVector(pc.find_addr_alias("after"))
    pc._ret_addr_stack.push(return_dest)


@Node()
async def doing_work() -> None:
    """The section we GOTO into."""
    print("  Doing work in the jumped-to section")


@Node()
async def after_return() -> None:
    """RET_FAR pops _ret_addr_stack and jumps here."""
    print("Back here (popped via RET_FAR)")


async def main() -> None:
    print("=== RET_FAR example ===")
    # Pattern: manual push → GOTO → RET_FAR pop-and-return
    #   1) save_ret_addr pushes "after" address onto _ret_addr_stack
    #   2) GOTO("work") jumps to the work section
    #   3) RET_FAR() pops the saved address and jumps back
    comp = (
        start
        >> save_ret_addr
        >> GOTO("work")
        >> ALIAS(after_return, "after")
        >> GOTO("end")
        >> ALIAS(doing_work, "work")
        >> RET_FAR()
        >> ALIAS(NOP, "end")
        >> NOP
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
