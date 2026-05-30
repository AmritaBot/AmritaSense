"""08_interrupt_suspend.py — run_step_by() step-by-step debugging

Usage:
    python demos/08_interrupt_suspend.py
"""

import asyncio

from amrita_sense import NOP, Node, WorkflowInterpreter


@Node()
async def step_one() -> None:
    print("[1] First step")


@Node()
async def step_two() -> None:
    print("[2] Second step")


@Node()
async def step_three() -> None:
    print("[3] Third step")


async def main() -> None:
    print("=== Using run_step_by() to inspect between steps ===")
    comp = (step_one >> step_two >> step_three >> NOP).render()
    interpreter = WorkflowInterpreter(comp)

    async for result in interpreter.run_step_by():
        print(f"  → Node output: {result}")
        # You can pause, inspect the pointer, or decide whether to continue here


if __name__ == "__main__":
    asyncio.run(main())
