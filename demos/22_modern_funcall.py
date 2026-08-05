"""22_modern_funcall.py — FN / INTER_FN modern function-call patterns

Usage:
    python demos/22_modern_funcall.py

AmritaSense "function blocks" are control-flow transfers, NOT real
computer function calls — there is no function context: no stack frame,
no local variables, no argument passing, no return-value convention.

Two patterns:

1. FN(entrypoint, block)  — a regular function block.  Call it with
   PUSH_AND_GOTO(None, entrypoint); the block ends with RET_FAR() which
   pops the caller's return address and resumes after the call site.

2. INTER_FN(entrypoint, block) — an interrupt service routine.  Enter it
   with INTERRUPT_INTO(entrypoint, None); the block ends with
   INTERRUPT_RET() which restores the saved interpreter context.

Both start with a hidden _fn_escape node so normal sequential flow
jumps over the whole block (rebase_ptr + offset(3)).
"""

import asyncio

from amrita_sense import ALIAS, Node, WorkflowInterpreter
from amrita_sense.instructions import (
    FN,
    INTERRUPT_INTO,
    INTER_FN,
    PUSH_AND_GOTO,
)


@Node()
async def main_start() -> None:
    print("[main] start")


# --- FN: regular function block ---


@Node()
async def fn_body() -> None:
    print("  [fn] inside fn_body()")


@Node()
async def after_fn() -> None:
    print("[main] resumed after FN call")


# --- INTER_FN: interrupt service routine ---


@Node()
async def isr_body() -> None:
    print("  [isr] inside isr_body()")


@Node()
async def after_isr() -> None:
    print("[main] resumed after interrupt routine")


async def main() -> None:
    print("=== FN / INTER_FN modern function-call demo ===\n")

    # Pattern 1: FN + PUSH_AND_GOTO(None, entrypoint)
    #   fn_block layout: [_fn_escape, NOP("fn_entry"), fn_body, RET_FAR]
    fn_block = FN(
        "fn_entry",
        fn_body,
    )

    # Pattern 2: INTER_FN + INTERRUPT_INTO(entrypoint, None)
    #   isr_block layout: [_fn_escape, NOP("isr_entry"), isr_body, INTERRUPT_RET]
    isr_block = INTER_FN(
        "isr_entry",
        isr_body,
    )

    comp = (
        main_start
        >> PUSH_AND_GOTO(None, "fn_entry")  # call fn_block; None = return after this node
        >> after_fn
        >> fn_block  # skipped by normal flow via _fn_escape
        >> INTERRUPT_INTO("isr_entry", None)  # dispatch interrupt; None = return after this node
        >> after_isr
        >> isr_block  # skipped by normal flow via _fn_escape
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
