"""05_while_loop.py — WHILE + DO-WHILE loops

Usage:
    python demos/05_while_loop.py
"""

import asyncio

from amrita_sense import DO, NOP, WHILE, Node, WorkflowInterpreter
from amrita_sense.exceptions import BreakLoop


@Node()
def counter() -> int:
    """Increment and return the counter on each call"""
    if not hasattr(counter, "n"):
        counter.n = 1  # type: ignore[attr-defined]
    else:
        counter.n += 1  # type: ignore[attr-defined]
    return counter.n  # type: ignore[attr-defined]


@Node()
async def under_three(n: int) -> bool:
    """WHILE loop condition"""
    return n < 3


@Node()
def body(n: int) -> None:
    """Loop body"""
    print(f"  WHILE iteration {n}")


@Node()
def early_break(n: int) -> None:
    """DO loop body: break out on iteration 3"""
    print(f"  DO-WHILE iteration {n}")
    if n >= 3:
        raise BreakLoop


async def main() -> None:
    print("=== WHILE example ===")
    wf = (counter >> WHILE(under_three).ACTION(body) >> NOP).render()
    await WorkflowInterpreter(wf).run()

    # Reset counter
    counter.n = 0  # type: ignore[attr-defined]

    print("\n=== DO-WHILE example ===")
    wf2 = (
        counter >> DO(early_break).WHILE(Node(lambda n: n < 5, wrap_to_async=False)) >> NOP  # type: ignore[arg-type]
    ).render()
    await WorkflowInterpreter(wf2).run()


if __name__ == "__main__":
    asyncio.run(main())
