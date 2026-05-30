"""13_ret_far.py — CALL + RET_FAR nested return

Usage:
    python demos/13_ret_far.py
"""

import asyncio

from amrita_sense import ALIAS, ARCHIVED_NODES, CALL, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import RET_FAR


@Node()
async def deep_work() -> object:
    """Deep task: simulate an early-exit condition"""
    print("  Entering deep task...")
    print("  Early exit condition met — executing RET_FAR")
    return RET_FAR()  # Pop return address and jump back to the outermost caller


@Node()
async def never_reached() -> None:
    print("  This line should never print (RET_FAR already jumped out)")


@Node()
async def back_to_top() -> None:
    print("Back to top level")


async def main() -> None:
    print("=== RET_FAR example ===")
    sub = ARCHIVED_NODES(ALIAS(deep_work, "deep"))
    comp = (
        Node(lambda: print("Start"))  # type: ignore[arg-type]
        >> CALL("deep")
        >> back_to_top
        >> NOP
        >> sub
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
