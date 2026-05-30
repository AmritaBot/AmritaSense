"""15_step_by.py — run_step_by() step-by-step debugging with pointer inspection

Usage:
    python demos/15_step_by.py
"""

import asyncio

from amrita_sense import NOP, Node, WorkflowInterpreter


@Node()
async def a() -> int:
    return 1


@Node()
async def b(prev: int) -> int:
    return prev * 10


@Node()
async def c(prev: int) -> None:
    print(f"Final value: {prev}")


async def main() -> None:
    comp = (a >> b >> c >> NOP).render()
    interpreter = WorkflowInterpreter(comp)

    step = 0
    async for result in interpreter.run_step_by():
        step += 1
        ptr = interpreter._pointer.base_addr
        print(f"Step {step}: output={result!r}, pointer={ptr}")

        # Inspect state and decide next action here.
        # e.g.: if step >= 2: break


if __name__ == "__main__":
    asyncio.run(main())
