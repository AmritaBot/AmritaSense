"""03_dependency_injection.py — extra_args / extra_kwargs explicit injection

Usage:
    python demos/03_dependency_injection.py
    python -i demos/03_dependency_injection.py   # same, then use `inter` directly in the REPL
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter


@Node()
async def greet(greeting: str, name: str) -> str:
    # greeting -> injected by name via extra_kwargs; name -> injected by type (str) via extra_args
    return f"{greeting}, {name}!"


@Node()
async def display(message: str) -> None:
    print(message)


composition = greet >> display
# Module-level so a REPL can `from demos.03_dependency_injection import inter` and inspect the injected arguments.
inter = WorkflowInterpreter(
    composition.render(),
    extra_args=("World",),  # str type -> injected into `name`
    extra_kwargs={"greeting": "Hello"},  # name match -> injected into `greeting`
)


async def main() -> None:
    await inter.run()


if __name__ == "__main__":
    asyncio.run(main())
