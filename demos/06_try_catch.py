"""06_try_catch.py — TRY / CATCH / FINALLY / THEN exception handling

Usage:
    python demos/06_try_catch.py
"""

import asyncio

from amrita_sense import NOP, Node, NodeType, Try, WorkflowInterpreter


@Node()
async def may_fail() -> str:
    """Always raises ValueError"""
    raise ValueError("something went wrong")


@Node()
async def handle_error(exc_val: ValueError):
    """Catch ValueError and return fallback"""
    print(f"Caught: {exc_val}")


@Node()
async def on_success() -> None:
    """Executes when TRY succeeds (THEN)"""
    print("Success: all good")


@Node()
async def cleanup() -> None:
    """Always runs — success or failure (FINALLY)"""
    print("Cleanup complete")


async def example_1() -> None:
    """Exception caught by CATCH"""
    print("=== Example 1: ValueError → caught by CATCH ===")
    comp = Try(may_fail).CATCH(ValueError, handle_error) >> NOP
    rendered = comp.render()
    await WorkflowInterpreter(rendered).run()


async def example_2() -> None:
    """Normal execution + THEN + FINALLY"""
    print("\n=== Example 2: normal execution + THEN + FINALLY ===")
    comp = (
        Try(NodeType(lambda: "all good", wrap_to_async=False, address_able=False, tag=None))  # type: ignore[arg-type]
        .THEN(on_success)
        .CATCH(ValueError, handle_error)
        .FINALLY(cleanup)
        >> NOP
    )
    rendered = comp.render()
    await WorkflowInterpreter(rendered).run()


async def main() -> None:
    await example_1()
    await example_2()


if __name__ == "__main__":
    asyncio.run(main())
