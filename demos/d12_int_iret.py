"""d12_int_iret.py — INT / IRET interrupt-style jump

Usage:
    python demos/d12_int_iret.py
    python -i demos/d12_int_iret.py   # same, then use `inter` directly in the REPL

INT(jump_to, ret_to=None) snapshots the interpreter state and
jumps to the handler:
  - jump_to: where to go NOW (the interrupt handler)
  - ret_to:  where IRET will resume.  None (default) in the main
             flow means "the current pointer" — after the restore the
             interpreter advances onto the next node (back_to_main).
"""

import asyncio

from amrita_sense import ALIAS, Node, WorkflowInterpreter
from amrita_sense.instructions import INT, IRET
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


# Archived handler: skipped by normal flow, entered via INT.
interrupt_handler = ARCHIVED_SEGMENT(
    ALIAS(handler_entry, "int_handler") >> handler_body >> IRET(),
)

composition = (
    main_start
    >> INT("int_handler", None)  # Restore at the next command.
    >> back_to_main  # executes after restore
    >> interrupt_handler
)
# Module-level so a REPL can `from demos.d12_int_iret import inter` and watch `if_flag` / `context_stack`.
inter = WorkflowInterpreter(composition.render())


async def main() -> None:
    print("=== INT + IRET demo ===\n")
    await inter.run()


if __name__ == "__main__":
    asyncio.run(main())
