"""07_jmp_invoke.py — JMP + INVOKE + ALIAS + ARCHIVED_NODES

Usage:
    python demos/07_jmp_invoke.py
"""

import asyncio

from amrita_sense import ALIAS, ARCHIVED_NODES, INVOKE, JMP, Node, WorkflowInterpreter


@Node()
async def start() -> None:
    print("Start")


@Node()
async def skip_me() -> None:
    print("This line should never appear")


@Node()
async def after_jump() -> None:
    print("Arrived after JMP jump")


_greet_result: str = ""


@Node()
async def reusable_greet(name: str = "World") -> str:
    global _greet_result
    print(f"  Hello, {name}!")
    _greet_result = name
    return name


@Node()
async def done() -> None:
    print(f"INVOKE returned: {_greet_result}")


async def main() -> None:
    print("=== JMP example ===")

    # JMP("target") skips skip_me, goes directly to after_jump
    comp = start >> JMP("target") >> skip_me >> ALIAS(after_jump, "target")
    await WorkflowInterpreter(comp.render()).run()

    print("\n=== INVOKE example ===")

    # INVOKE("greeter") runs the subroutine inline, then returns to continue
    sub = ARCHIVED_NODES(ALIAS(reusable_greet, "greeter"))
    comp2 = start >> INVOKE("greeter") >> done >> sub
    await WorkflowInterpreter(comp2.render()).run()


if __name__ == "__main__":
    asyncio.run(main())
