"""02_composition.py — Multi-node chain + DI return-value passing

Usage:
    python demos/02_composition.py
"""

import asyncio

from amrita_sense import NOP, Node, WorkflowInterpreter


@Node()
async def double() -> int:
    return 42


@Node()
async def add_one(value: int) -> int:
    # DI injects the return value (42) from double into `value`
    return value + 1


@Node()
async def print_result(value: int) -> None:
    print(f"Final result: {value}")


async def main() -> None:
    composition = double >> add_one >> print_result >> NOP
    rendered = composition.render()
    interpreter = WorkflowInterpreter(rendered)
    await interpreter.run()


if __name__ == "__main__":
    asyncio.run(main())
