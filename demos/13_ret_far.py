"""13_ret_far.py — PUSH_STACK + GOTO + RET_FAR pop-and-return

Usage:
    python demos/13_ret_far.py

Note: v0.3.0+ also provides PUSH_AND_GOTO(from_adr, to_adr) as a convenience
instruction that combines PUSH_STACK + GOTO into a single node.
"""

import asyncio

from amrita_sense import ALIAS, Node, WorkflowInterpreter
from amrita_sense.instructions.ret2 import PUSH_AND_GOTO
from amrita_sense.instructions.subprogram import ARCHIVED_SEGMENT


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
    comp = (
        start
        >> PUSH_AND_GOTO(None, "doing_work")
        >> after_return
        >> ARCHIVED_SEGMENT(ALIAS(doing_work, "doing_work") >> doing_work)
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
