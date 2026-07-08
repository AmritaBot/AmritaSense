"""18_context_stack.py — PUSH_CONTEXT / POP_CONTEXT + rebase_context

Usage:
    python demos/18_context_stack.py
"""

import asyncio

from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, PUSH_CONTEXT


@Node()
async def start() -> None:
    print("Start — saving context before sub-flow")


@Node()
async def sub_work() -> None:
    print("  [sub-flow] Doing work in isolated context")


@Node()
async def inspect_and_restore(pc: WorkflowInterpreter) -> None:
    # Manually pop the context that PUSH_CONTEXT saved
    ctx = pc.context_stack.pop()
    print(f"  Context snapshot — ptr was at: {ctx.ptr}")
    print(f"  Ignored exceptions: {ctx.exception_ignored}")
    print("  Context inspected — continuing without rebase in this demo")


@Node()
async def finish() -> None:
    print("Finish — back in original flow")


async def main() -> None:
    print("=== PUSH_CONTEXT / POP_CONTEXT demo ===\n")

    comp = (
        start
        >> PUSH_CONTEXT()
        >> GOTO("sub")
        >> ALIAS(sub_work, "sub")
        >> inspect_and_restore
        >> finish
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
