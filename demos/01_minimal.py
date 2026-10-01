"""01_minimal.py — Minimal example: single node + interpreter run

Usage:
    python demos/01_minimal.py
    python -i demos/01_minimal.py   # same, then use `inter` directly in the REPL
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter


@Node()
async def hello() -> None:
    print("Hello, AmritaSense!")


# A single node is composed via as_compose() — no NOP sentinel needed; the interpreter finishes when the workflow reaches its end.
composition = hello.as_compose()
# Module-level so a REPL can `from demos.01_minimal import inter` and drive it directly.
inter = WorkflowInterpreter(composition.render())


async def main() -> None:
    await inter.run()


if __name__ == "__main__":
    asyncio.run(main())
