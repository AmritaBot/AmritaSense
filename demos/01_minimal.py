"""01_minimal.py — Minimal example: single node + NOP + interpreter run

Usage:
    python demos/01_minimal.py
"""

import asyncio

from amrita_sense import NOP, Node, WorkflowInterpreter


@Node()
async def hello() -> None:
    print("Hello, AmritaSense!")


async def main() -> None:
    # Compose: hello followed by NOP sentinel node
    composition = hello >> NOP
    rendered = composition.render()

    interpreter = WorkflowInterpreter(rendered)
    await interpreter.run()


if __name__ == "__main__":
    asyncio.run(main())
