"""06_try_catch.py — TRY / CATCH / FINALLY / THEN exception handling

Usage:
    python demos/06_try_catch.py
    python -i demos/06_try_catch.py   # same, then use `inter` / `success_inter` in the REPL
"""

import asyncio

from amrita_sense import Node, Try, WorkflowInterpreter


@Node()
async def may_fail() -> str:
    """Always raises ValueError"""
    raise ValueError("something went wrong")


@Node()
async def handle_error(exc_val: ValueError) -> None:
    """Catch ValueError"""
    print(f"Caught: {exc_val}")


@Node()
async def on_success() -> None:
    """Executes when TRY succeeds (THEN)"""
    print("Success: all good")


@Node()
async def cleanup() -> None:
    """Always runs — success or failure (FINALLY)"""
    print("Cleanup complete")


@Node()
async def always_ok() -> str:
    return "all good"


# TryClause is a SelfCompileInstruction — pass it straight to the interpreter; module-level so a REPL can drive both paths.
inter = WorkflowInterpreter(Try(may_fail).CATCH(ValueError, handle_error))
success_inter = WorkflowInterpreter(
    Try(always_ok).THEN(on_success).CATCH(ValueError, handle_error).FINALLY(cleanup)
)


async def main() -> None:
    print("=== Example 1: ValueError -> caught by CATCH ===")
    await inter.run()

    print("\n=== Example 2: normal execution + THEN + FINALLY ===")
    await success_inter.run()


if __name__ == "__main__":
    asyncio.run(main())
