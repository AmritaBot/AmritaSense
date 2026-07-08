"""17_unsafe_flags.py — _unsafe flag configuration demo

Usage:
    python demos/17_unsafe_flags.py

IMPORTANT: Flags must be set BEFORE any WorkflowInterpreter is created.
Once set, a flag cannot be changed — attempting to do so raises RuntimeError.
"""

import asyncio

# Uncomment to test different flags:
# __flags__.FORCE_NOT_WRAP_TO_ASYNC = True
# __flags__.ALLOW_CALL_NODECOMPOSE = True
# __flags__.DISABLE_EXC_IGNORED = True
# __flags__.NO_DEPENDENCY_META_CACHE = True
# __flags__.NO_SHARED_MIDDLEWARE = True
# __flags__.JIT_OPTIMIZE = True
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter

# ✅ Correct: configure flags at the very top of the entry point
from amrita_sense._unsafe import __flags__


@Node()
async def step_one() -> None:
    print("[1] First step")


@Node()
async def step_two() -> None:
    print("[2] Second step")


@Node()
async def step_three() -> None:
    print("[3] Third step")


async def demo_normal() -> None:
    """Default behavior with all flags at defaults."""
    print("=== Demo 1: Default flags ===")
    comp = (step_one >> step_two >> step_three >> ALIAS(NOP, "done")).render()
    interpreter = WorkflowInterpreter(comp)
    await interpreter.run()


async def demo_flag_lock() -> None:
    """Demonstrate that flags are locked after first set."""
    print("\n=== Demo 2: Flag locking behavior ===")

    # Flags that haven't been set can be set once
    print(f"FORCE_NOT_WRAP_TO_ASYNC (before set): {__flags__.FORCE_NOT_WRAP_TO_ASYNC}")

    # But trying to set it a second time raises RuntimeError
    try:
        __flags__.FORCE_NOT_WRAP_TO_ASYNC = True
        print(
            f"FORCE_NOT_WRAP_TO_ASYNC (after set): {__flags__.FORCE_NOT_WRAP_TO_ASYNC}"
        )
        __flags__.FORCE_NOT_WRAP_TO_ASYNC = False  # This will fail!
    except RuntimeError as e:
        print(f"RuntimeError (expected): {e}")


async def demo_jit_optimize() -> None:
    """Demonstrate JIT_OPTIMIZE flag behavior.

    When JIT_OPTIMIZE is enabled, NOP nodes are skipped entirely in _call(),
    avoiding the per-node overhead of dependency injection and lock acquire/release.
    """
    print("\n=== Demo 3: JIT_OPTIMIZE flag ===")
    print(f"JIT_OPTIMIZE (before any set): {__flags__.JIT_OPTIMIZE}")


async def main() -> None:
    await demo_normal()
    await demo_flag_lock()
    await demo_jit_optimize()


if __name__ == "__main__":
    asyncio.run(main())
