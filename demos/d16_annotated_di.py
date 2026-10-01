"""d16_annotated_di.py — Annotated[...] dependency declarations

Usage:
    python demos/d16_annotated_di.py
    python -i demos/d16_annotated_di.py   # same, then use `inter` directly in the REPL

Shows the two equivalent ways to declare a dependency, that a parameter must
not use both at once, and how a malformed declaration fails at construction
time rather than at run time.
"""

import asyncio
from typing import Annotated

from amrita_sense import Node, NodeCompose, WorkflowInterpreter
from amrita_sense.exceptions import DependsDeclarationError
from amrita_sense.hook.matcher import Depends


async def get_greeting() -> str:
    return "Hello"


async def get_target() -> str:
    return "Annotated"


# Both spellings are equivalent: `Depends` in the default value, and `Depends` inside the annotation.  Only the type inside `Annotated` takes part in type-based matching; the extra metadata is ignored.
@Node()
async def greet(
    by_annotation: Annotated[str, Depends(get_target)],
    by_default: str = Depends(get_greeting),
) -> None:
    print(f"{by_default}, {by_annotation}!")


composition = NodeCompose(greet)
# Module-level so a REPL can `from demos.d16_annotated_di import inter` and inspect the resolved dependencies.
inter = WorkflowInterpreter(composition.render())


def show_malformed_declaration() -> None:
    """A contradictory declaration is rejected while the node is built."""

    async def provider() -> str:
        return "unused"

    try:

        @Node()
        async def broken(
            value: Annotated[str, Depends(provider)] = Depends(provider),
        ) -> None: ...

    except DependsDeclarationError as exc:
        print(f"DependsDeclarationError: {exc}")


async def main() -> None:
    await inter.run()
    show_malformed_declaration()


if __name__ == "__main__":
    asyncio.run(main())
