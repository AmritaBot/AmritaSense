"""09_interrupt_notice.py — INTERRUPT node + InterruptNotice forced termination

Usage:
    python demos/09_interrupt_notice.py
"""

import asyncio

from amrita_sense import INTERRUPT, Node, WorkflowInterpreter
from amrita_sense.exceptions import InterruptNotice


@Node()
async def normal_work() -> int:
    print("Running normally...")
    return 42


@Node()
async def critical_check(value: int) -> None:
    if value > 40:
        print("Dangerous condition detected — forcing termination!")
        raise InterruptNotice("value exceeds threshold")


@Node()
async def this_wont_run(value: int) -> None:
    print("This line won't execute (workflow already terminated)")


async def main() -> None:
    print("=== InterruptNotice forced termination example ===")
    comp = (normal_work >> critical_check >> this_wont_run).render()

    try:
        await WorkflowInterpreter(comp).run()
    except InterruptNotice as e:
        print(f"Workflow terminated: {e}")

    print("\n=== INTERRUPT instruction example ===")
    comp2 = (normal_work >> INTERRUPT >> this_wont_run).render()
    try:
        await WorkflowInterpreter(comp2).run()
    except InterruptNotice:
        print("Workflow terminated by INTERRUPT instruction")


if __name__ == "__main__":
    asyncio.run(main())
