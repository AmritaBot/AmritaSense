"""18_context_stack.py — PUSH_CONTEXT / INTERRUPT_RET save & restore

Usage:
    python demos/18_context_stack.py

Since v0.6.0, PUSH_CONTEXT(target) only SNAPSHOTS the interpreter state
(it does NOT jump).  To enter the sub-flow you must jump explicitly with
GOTO, and INTERRUPT_RET() pops the snapshot and restores it.

INTERRUPT_RET restores via rebase_context (no jump flag), so execution
resumes at the node AFTER the saved address — the saved address should be
the predecessor of the real resume point (the "resume" NOP below).
"""

import asyncio

from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_RET, PUSH_CONTEXT


@Node()
async def start() -> None:
    print("Start — about to PUSH_CONTEXT and GOTO the sub-flow")


@Node()
async def sub_work() -> None:
    print("  [sub-flow] Doing work in isolated context")


@Node()
async def after_restore() -> None:
    print("Back — INTERRUPT_RET restored the saved context")


@Node()
async def finish() -> None:
    print("Finish — workflow complete")


async def main() -> None:
    print("=== PUSH_CONTEXT + INTERRUPT_RET demo ===\n")

    comp = (
        start
        >> PUSH_CONTEXT("resume")  # snapshot state; return address = resume NOP
        >> GOTO("sub_entry")  # explicit jump into the sub-flow
        >> ALIAS(
            NOP, "resume"
        )  # INTERRUPT_RET rebases here -> advance to after_restore
        >> after_restore  # resumed here after INTERRUPT_RET
        >> finish
        >> GOTO("done")
        >> ALIAS(sub_work, "sub_entry")  # jumped to here
        >> INTERRUPT_RET()  # pop & restore
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
