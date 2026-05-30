"""07_goto_call.py — GOTO + CALL + ALIAS + ARCHIVED_NODES

Usage:
    python demos/07_goto_call.py
"""

import asyncio

from amrita_sense import ALIAS, ARCHIVED_NODES, CALL, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO


@Node()
async def start() -> None:
    print("Start")


@Node()
async def skip_me() -> None:
    print("This line should never appear")


@Node()
async def after_jump() -> None:
    print("Arrived after GOTO jump")


@Node()
async def reusable_greet(name: str = "World") -> str:
    print(f"  Hello, {name}!")
    return name


@Node()
async def done(result: str) -> None:
    print(f"CALL returned: {result}")


async def main() -> None:
    print("=== GOTO example ===")

    # GOTO("target") skips skip_me, goes directly to after_jump
    comp = start >> GOTO("target") >> skip_me >> ALIAS(after_jump, "target")
    await WorkflowInterpreter(comp.render()).run()

    print("\n=== CALL example ===")

    # CALL("greeter") invokes the subroutine, then returns to continue
    sub = ARCHIVED_NODES(ALIAS(reusable_greet, "greeter"))
    comp2 = start >> CALL("greeter") >> done >> sub
    await WorkflowInterpreter(comp2.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
