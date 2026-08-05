"""01_minimal.py — Minimal example: single node + interpreter run

Usage:
    python demos/01_minimal.py
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter


@Node()
async def hello() -> None:
    print("Hello, AmritaSense!")


async def main() -> None:
    # A single node is composed via as_compose() — no NOP sentinel needed;
    # the interpreter finishes when the workflow reaches its end.
    composition = hello.as_compose()
    rendered = composition.render()

    interpreter = WorkflowInterpreter(rendered)
    await interpreter.run()


if __name__ == "__main__":
    asyncio.run(main())
