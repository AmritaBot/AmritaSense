"""02_composition.py — Multi-node chain

Usage:
    python demos/02_composition.py
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter


@Node()
async def double() -> None:
    pass  # placeholder: real logic goes here


@Node()
async def add_one() -> None:
    pass  # placeholder: real logic goes here


@Node()
async def print_result() -> None:
    print("Composition complete")


async def main() -> None:
    composition = double >> add_one >> print_result
    rendered = composition.render()
    interpreter = WorkflowInterpreter(rendered)
    await interpreter.run()


if __name__ == "__main__":
    asyncio.run(main())
