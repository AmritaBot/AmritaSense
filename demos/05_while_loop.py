"""05_while_loop.py — WHILE + DO-WHILE loops

Usage:
    python demos/05_while_loop.py
"""

import asyncio

from amrita_sense import DO, NOP, WHILE, Node, WorkflowInterpreter
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
    print(f"  WHILE iteration {_counter}")


@Node()
def cond_dowhile() -> bool:
    return _counter < 5


@Node()
def do_body() -> None:
    print(f"  DO-WHILE iteration {_counter}")
    if _counter >= 3:
        raise BreakLoop


async def main() -> None:
    global _counter

    print("=== WHILE example ===")
    _counter = 0
    wf = (bump >> WHILE(under_three).ACTION(body) >> NOP).render()
    await WorkflowInterpreter(wf).run()

    print("\n=== DO-WHILE example ===")
    _counter = 0
    wf2 = (bump >> DO(do_body).WHILE(cond_dowhile) >> NOP).render()
    await WorkflowInterpreter(wf2).run()


if __name__ == "__main__":
    asyncio.run(main())
