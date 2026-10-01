"""d07_jmp_invoke.py — JMP + INVOKE + ALIAS + ARCHIVED_NODES

Usage:
    python demos/d07_jmp_invoke.py
    python -i demos/d07_jmp_invoke.py   # same, then use `inter` / `invoke_inter` in the REPL
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


# JMP("target") skips skip_me and goes directly to after_jump.
inter = WorkflowInterpreter(
    (start >> JMP("target") >> skip_me >> ALIAS(after_jump, "target")).render()
)

# INVOKE("greeter") runs the archived subroutine inline, then returns to continue.
_subprogram = ARCHIVED_NODES(ALIAS(reusable_greet, "greeter"))
invoke_inter = WorkflowInterpreter(
    (start >> INVOKE("greeter") >> done >> _subprogram).render()
)


async def main() -> None:
    print("=== JMP example ===")
    await inter.run()

    print("\n=== INVOKE example ===")
    await invoke_inter.run()


if __name__ == "__main__":
    asyncio.run(main())
