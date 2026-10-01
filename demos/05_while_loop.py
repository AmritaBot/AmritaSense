"""05_while_loop.py — WHILE + DO-WHILE loops

Usage:
    python demos/05_while_loop.py
    python -i demos/05_while_loop.py   # same, then use `inter` / `do_while_inter` in the REPL
"""

import asyncio

from amrita_sense import DO, WHILE, Node, WorkflowInterpreter
from amrita_sense.exceptions import BreakLoop

_counter = 0


@Node()
def bump() -> None:
    global _counter
    _counter += 1


@Node()
def under_three() -> bool:
    return _counter < 3


@Node()
def body() -> None:
    global _counter
    _counter += 1
    print(f"  WHILE iteration {_counter}")


@Node()
def cond_dowhile() -> bool:
    return _counter < 5


@Node()
def do_body() -> None:
    global _counter
    _counter += 1
    print(f"  DO-WHILE iteration {_counter}")
    if _counter >= 3:
        raise BreakLoop


# Module-level so a REPL can `from demos.05_while_loop import inter, do_while_inter`; reset `_counter` between runs.
inter = WorkflowInterpreter((bump >> WHILE(under_three).ACTION(body)).render())
do_while_inter = WorkflowInterpreter((bump >> DO(do_body).WHILE(cond_dowhile)).render())


async def main() -> None:
    global _counter

    print("=== WHILE example ===")
    _counter = 0
    await inter.run()

    print("\n=== DO-WHILE example ===")
    _counter = 0
    await do_while_inter.run()


if __name__ == "__main__":
    asyncio.run(main())
