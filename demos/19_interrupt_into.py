"""19_interrupt_into.py — INTERRUPT_INTO / INTERRUPT_RET interrupt-style jump

Usage:
    python demos/19_interrupt_into.py
"""

import asyncio

from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET


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
    print("=== INTERRUPT_INTO / INTERRUPT_RET demo ===\n")

    # Archived handler: skipped by normal flow, entered via INTERRUPT_INTO
    interrupt_handler = ARCHIVED_NODES(
        ALIAS(handler_entry, "int_handler"),
        handler_body,
        INTERRUPT_RET(),
    )

    comp = (
        main_start
        >> INTERRUPT_INTO("int_handler")
        >> back_to_main
        >> GOTO("done")
        >> interrupt_handler
        >> ALIAS(NOP, "done")
    )
    await WorkflowInterpreter(comp.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
