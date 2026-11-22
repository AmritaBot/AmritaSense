"""d26_rescue_repl.py — keep the scene when a workflow panics.

Run it in a terminal::

    python demos/d26_rescue_repl.py

The workflow crashes on purpose.  With ``RESCUE_ON_PANIC`` enabled and a
real TTY, SenseDBG drops into the rescue REPL *at the crash site* instead of
unwinding it:

    (sdb) [1] explode> i r
    (sdb) [1] explode> bt
    (sdb) [1] explode> skip        # move past the failed node
    (sdb) [1] explode> c           # ...and finish the workflow
    (sdb) [2] cleanup> q           # leave; the original panic is re-raised

Without a TTY (CI, a bot process) nothing blocks: the same state is attached to
the exception as ``__sdb_report__`` and re-raised immediately.  That difference
is the whole safety story — a rescue must never turn a crash into a hang.
"""

from __future__ import annotations

import asyncio

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense._unsafe import __flags__

__flags__.RESCUE_ON_PANIC = True


@Node(tag="load")
def load() -> str:
    print("  [load] running…")
    return "ready"


@Node(tag="explode")
def explode() -> None:
    msg = "demo panic: keep the scene, not the hang"
    raise RuntimeError(msg)


@Node(tag="cleanup")
def cleanup() -> None:
    print("  [cleanup] recovered and ran — only possible after `skip`/`c`")


inter = WorkflowInterpreter((load >> explode >> cleanup).render())


async def main() -> None:
    await inter.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        print(f"panic re-raised as {type(exc).__name__}: {exc}")
        report = getattr(exc, "__sdb_report__", None)
        if report is not None:
            print("attached report:", report.summary())
