"""03_dependency_injection.py — extra_args / extra_kwargs explicit injection

Usage:
    python demos/03_dependency_injection.py
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter


@Node()
async def greet(greeting: str, name: str) -> str:
    # greeting -> injected by name via extra_kwargs
    # name -> injected by type (str) via extra_args
    return f"{greeting}, {name}!"


@Node()
async def display(message: str) -> None:
    print(message)


async def main() -> None:
    composition = greet >> display
    rendered = composition.render()
    interpreter = WorkflowInterpreter(
        rendered,
        extra_args=("World",),  # str type -> injected into `name`
        extra_kwargs={"greeting": "Hello"},  # name match -> injected into `greeting`
    )
    await interpreter.run()


if __name__ == "__main__":
    asyncio.run(main())
