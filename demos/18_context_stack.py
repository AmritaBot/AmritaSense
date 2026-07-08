"""18_context_stack.py — PUSH_CONTEXT / INTERRUPT_RET save & restore

Usage:
    python demos/18_context_stack.py

PUSH_CONTEXT(target) saves full interpreter state then JUMPS to target.
Pair with INTERRUPT_RET() to pop and restore.
"""

import asyncio

from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_RET, PUSH_CONTEXT


@Node()
async def start() -> None:
    print("Start — about to PUSH_CONTEXT and jump to sub-flow")


@Node()
async def sub_work() -> None:
    print("  [sub-flow] Doing work in isolated context")


@Node()
async def after_restore() -> None:
    print("Back — INTERRUPT_RET restored the original pointer")


@Node()
async def finish() -> None:
    print("Finish — workflow complete")


async def main() -> None:
    print("=== PUSH_CONTEXT + INTERRUPT_RET demo ===\n")

    comp = (
        start
        >> PUSH_CONTEXT("sub_entry")  # save state, jump to sub_entry
        >> after_restore  # resumed here after INTERRUPT_RET
        >> finish
        >> GOTO("done")
        >> ALIAS(sub_work, "sub_entry")  # jumped to here
        >> INTERRUPT_RET()  # pop & restore, resume at after_restore
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
