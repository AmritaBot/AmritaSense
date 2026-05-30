"""15_step_by.py — run_step_by() step-by-step debugging with pointer inspection

Usage:
    python demos/15_step_by.py
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter


@Node()
async def a() -> None:
    print("Node A")


@Node()
async def b() -> None:
    print("Node B")


@Node()
async def c() -> None:
    print("Node C")


async def main() -> None:
    comp = (a >> b >> c).render()
    interpreter = WorkflowInterpreter(comp)

    step = 0
    async for result in interpreter.run_step_by():
        step += 1
        ptr = interpreter._pointer.base_addr
        print(f"Step {step}: output={result!r}, pointer={ptr}")


if __name__ == "__main__":
    asyncio.run(main())
