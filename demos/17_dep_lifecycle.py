"""17_dep_lifecycle.py — generator dependencies and lifecycle scopes

Usage:
    python demos/17_dep_lifecycle.py
    python -i demos/17_dep_lifecycle.py   # same, then use `inter` / `call_scope_inter` in the REPL

A provider may be a generator: the value before `yield` is injected and the
code after it is the teardown.  `scope` decides when that teardown runs.
"""

import asyncio
from collections.abc import AsyncIterator

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.hook.matcher import Depends


class Session:
    """A stand-in for a resource that has to be opened and closed."""

    _opened = 0

    def __init__(self) -> None:
        Session._opened += 1
        self.id = Session._opened

    def __repr__(self) -> str:
        return f"<Session #{self.id}>"


async def open_session() -> AsyncIterator[Session]:
    """Async generator provider — everything after `yield` is the teardown."""
    session = Session()
    print(f"    open  {session}")
    try:
        yield session
    finally:
        print(f"    close {session}")


@Node()
async def shared_first(
    session: Session = Depends(open_session, scope="workflow"),
) -> None:
    print(f"  first  sees {session}")


@Node()
async def shared_second(
    session: Session = Depends(open_session, scope="workflow"),
) -> None:
    print(f"  second sees {session}")


@Node()
async def fresh(session: Session = Depends(open_session, scope="call")) -> None:
    print(f"  node   sees {session}")


@Node()
async def fresh_again(session: Session = Depends(open_session, scope="call")) -> None:
    print(f"  node   sees {session}")


# Module-level so a REPL can `from demos.17_dep_lifecycle import inter, call_scope_inter` and watch the teardown order.
inter = WorkflowInterpreter((shared_first >> shared_second).render())
call_scope_inter = WorkflowInterpreter((fresh >> fresh_again).render())


async def main() -> None:
    print("scope='workflow' — one instance shared by both nodes:")
    await inter.run()

    print("\nscope='call' — a new instance for every node:")
    await call_scope_inter.run()


if __name__ == "__main__":
    asyncio.run(main())
