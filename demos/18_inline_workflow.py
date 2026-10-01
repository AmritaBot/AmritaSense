"""18_inline_workflow.py — Inline workflow: encapsulate a workflow in a class

Usage:
    python demos/18_inline_workflow.py
    python -i demos/18_inline_workflow.py   # same, then use `inter` / `workflow` in the REPL
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter


class SimpleWorkflow:
    """Self-contained workflow: accepts constructor args, holds compose and interpreter"""

    def __init__(self, value: int) -> None:
        self.value = value
        self.result: str | None = None

        # Node functions must be parameterless — DI cannot resolve `self`; closure nodes capture the instance instead.
        @Node()
        async def double() -> None:
            self.value *= 2

        @Node()
        async def format() -> str:
            self.result = f"Processed: {self.value}"
            return self.result

        # Compose -> render -> create interpreter
        rendered = (double >> format).render()
        self.interpreter = WorkflowInterpreter(rendered)

    async def run(self) -> str | None:
        await self.interpreter.run()
        return self.result


# Module-level so a REPL can `from demos.18_inline_workflow import inter`; `inter` is the workflow's interpreter.
workflow = SimpleWorkflow(value=21)
inter = workflow.interpreter


async def main() -> None:
    print(await workflow.run())


if __name__ == "__main__":
    asyncio.run(main())
