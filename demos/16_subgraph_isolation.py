"""16_subgraph_isolation.py — fork_interpreter + interpreter tree lifecycle

Usage:
    python demos/16_subgraph_isolation.py

Demonstrates: fork_interpreter(), asyncio.gather for parallel execution,
terminate() for early stop, and interpreter tree properties (parent, id).
"""

import asyncio
import contextlib

from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter

# --- Sub-workflow ---


@Node()
async def sub_start() -> None:
    print("  [sub] started")


@Node()
async def sub_step1() -> None:
    print("  [sub] step 1")


@Node()
async def sub_step2() -> None:
    print("  [sub] step 2")


sub_comp = sub_start >> sub_step1 >> sub_step2 >> ALIAS(NOP, "done")


# --- Main node ---


@Node()
async def main_start() -> None:
    print("[main] started")


async def demo_parallel() -> None:
    """Fork two children and run parent + children concurrently via gather."""
    print("\n=== Demo 1: parallel execution via asyncio.gather ===")

    parent = WorkflowInterpreter((main_start >> ALIAS(NOP, "done")).render())

    child_a = parent.fork_interpreter(compose=sub_comp.render(), middleware=None)
    child_b = parent.fork_interpreter(compose=sub_comp.render(), middleware=None)
    assert child_a.parent
    assert child_b.parent

    print(f"[main] parent id:  {parent.id}")
    print(f"[main] child_a id: {child_a.id}  parent: {child_a.parent.id}")
    print(f"[main] child_b id: {child_b.id}  parent: {child_b.parent.id}")
    print(f"[main] child_a top: {child_a.top_interpreter.id}")
    print(f"[main] child_b top: {child_b.top_interpreter.id}")

    # asyncio.gather runs all to completion — no manual wait needed
    await asyncio.gather(
        parent.run(),
        child_a.run(),
        child_b.run(),
    )

    print("[main] all interpreters finished")
    print(f"[main] parent.sub_interpreters: {list(parent.sub_interpreters.keys())}")


async def demo_terminate() -> None:
    """Early termination: cancel a child before it finishes."""
    print("\n=== Demo 2: early termination ===")

    parent = WorkflowInterpreter((main_start >> ALIAS(NOP, "done")).render())
    child = parent.fork_interpreter(compose=sub_comp.render(), middleware=None)

    child_task = asyncio.create_task(child.run())
    print(f"[main] child is_running: {child.is_running}")

    # Terminate the child mid-execution
    await child.terminate(eol=True)
    print(f"[main] child terminated, is_running: {child.is_running}")

    child_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await child_task

    await parent.run()
    print(f"[main] parent finished, children left: {parent.sub_interpreters}")


async def main() -> None:
    await demo_parallel()
    await demo_terminate()


if __name__ == "__main__":
    asyncio.run(main())
