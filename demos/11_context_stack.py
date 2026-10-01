"""11_context_stack.py — PUSH_CONTEXT / IRET save & restore

Usage:
    python demos/11_context_stack.py
    python -i demos/11_context_stack.py   # same, then use `inter` directly in the REPL

PUSH_CONTEXT(target) only SNAPSHOTS the interpreter state (it does NOT
jump).  To enter the sub-flow you must jump explicitly with JMP, and
IRET() pops the snapshot and restores it.

IRET restores via rebase_context (no jump flag), so execution
resumes at the node AFTER the saved address — the saved address should be
the predecessor of the real resume point (the "resume" NOP below).
"""

import asyncio

from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import IRET, JMP, PUSH_CONTEXT


@Node()
async def start() -> None:
    print("Start — about to PUSH_CONTEXT and JMP to the sub-flow")


@Node()
async def sub_work() -> None:
    print("  [sub-flow] Doing work in isolated context")


@Node()
async def after_restore() -> None:
    print("Back — IRET restored the saved context")


@Node()
async def finish() -> None:
    print("Finish — workflow complete")


composition = (
    start
    >> PUSH_CONTEXT("resume")  # snapshot state; return address = resume NOP
    >> JMP("sub_entry")  # explicit jump into the sub-flow
    >> ALIAS(NOP, "resume")  # IRET rebases here -> advance to after_restore
    >> after_restore  # resumed here after IRET
    >> finish
    >> JMP("done")
    >> ALIAS(sub_work, "sub_entry")  # jumped to here
    >> IRET()  # pop & restore
    >> ALIAS(NOP, "done")
)
# Module-level so a REPL can `from demos.11_context_stack import inter` and inspect `inter.context_stack`.
inter = WorkflowInterpreter(composition.render())


async def main() -> None:
    print("=== PUSH_CONTEXT + IRET demo ===\n")
    await inter.run()


if __name__ == "__main__":
    asyncio.run(main())
