"""24_step_by.py — run_step_by() step-by-step debugging with pointer inspection

Usage:
    python demos/24_step_by.py
    python -i demos/24_step_by.py   # same, then use `inter` directly in the REPL
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


composition = a >> b >> c
# Module-level so a REPL can `from demos.24_step_by import inter` and pull one step at a time.
inter = WorkflowInterpreter(composition.render())


async def main() -> None:
    step = 0
    async for result in inter.run_step_by():
        step += 1
        ptr = inter._pointer.base_addr
        print(f"Step {step}: output={result!r}, pointer={ptr}")


if __name__ == "__main__":
    asyncio.run(main())
