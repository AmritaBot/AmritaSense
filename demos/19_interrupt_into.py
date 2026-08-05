"""19_interrupt_into.py — INTERRUPT_INTO / INTERRUPT_RET interrupt-style jump

Usage:
    python demos/19_interrupt_into.py

INTERRUPT_INTO(jump_to, ret_to=None) snapshots the interpreter state and
jumps to the handler:
  - jump_to: where to go NOW (the interrupt handler)
  - ret_to:  where INTERRUPT_RET will resume.  None (default) in the main
             flow means "the current pointer" — after the restore the
             interpreter advances onto the next node (back_to_main).
"""

import asyncio

from amrita_sense import ALIAS, Node, WorkflowInterpreter
from amrita_sense.instructions import INTERRUPT_INTO, INTERRUPT_RET
from amrita_sense.instructions.subprogram import ARCHIVED_SEGMENT


@Node()
async def main_start() -> None:
    print("[main] Starting — about to trigger interrupt")


@Node()
async def handler_entry() -> None:
    print("  [handler] Interrupt handler started")


@Node()
async def handler_body() -> None:
    print("  [handler] Processing interrupt...")


@Node()
async def back_to_main() -> None:
    print("[main] Back from interrupt — resuming normal flow")


async def main() -> None:
    print("=== INTERRUPT_INTO + INTERRUPT_RET demo ===\n")

    # Archived handler: skipped by normal flow, entered via INTERRUPT_INTO
    interrupt_handler = ARCHIVED_SEGMENT(
        ALIAS(handler_entry, "int_handler") >> handler_body >> INTERRUPT_RET(),
    )

    comp = (
        main_start
        >> INTERRUPT_INTO("int_handler", None)  # Restore at the next command.
        >> back_to_main  # executes after restore
        >> interrupt_handler
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
