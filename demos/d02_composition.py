"""d02_composition.py — Multi-node chain

Usage:
    python demos/d02_composition.py
    python -i demos/d02_composition.py   # same, then use `inter` directly in the REPL
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


composition = double >> add_one >> print_result
# Module-level so a REPL can `from demos.d02_composition import inter` and drive it directly.
inter = WorkflowInterpreter(composition.render())


async def main() -> None:
    await inter.run()


if __name__ == "__main__":
    asyncio.run(main())
