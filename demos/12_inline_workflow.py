"""12_inline_workflow.py — Inline workflow: encapsulate a workflow in a class

Usage:
    python demos/12_inline_workflow.py
"""

import asyncio

from amrita_sense import NOP, Node, WorkflowInterpreter


class SimpleWorkflow:
    """Self-contained workflow: accepts constructor args, holds compose and interpreter"""

    def __init__(self, value: int) -> None:
        self.value = value
        self.result: str | None = None

        # Compose → render → create interpreter
        rendered = (self.double >> self.format >> NOP).render()
        self.interpreter = WorkflowInterpreter(rendered)

    @Node()
    async def double(self) -> int:
        return self.value * 2

    @Node()
    async def format(self, prev: int) -> str:
        self.result = f"Processed: {prev}"
        return self.result

    async def run(self) -> str | None:
        await self.interpreter.run()
        return self.result


async def main() -> None:
    wf = SimpleWorkflow(value=21)
    result = await wf.run()
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
