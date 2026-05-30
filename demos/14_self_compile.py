"""14_self_compile.py — Custom SelfCompileInstruction

Usage:
    python demos/14_self_compile.py
"""

import asyncio

from amrita_sense import NOP, Node, WorkflowInterpreter
from amrita_sense.node.core import BaseNode
from amrita_sense.node.self_compile import SelfCompileInstruction


class TimedWrapper(SelfCompileInstruction):
    """Custom self-compile instruction: logs timing marks around execution"""

    def __init__(self, inner_node: BaseNode) -> None:
        self._inner = inner_node

    def extract(self):
        from amrita_sense.node.core import NodeCompose

        @Node()
        def log_start() -> None:
            print("[Start]")

        @Node()
        def log_end(result: str) -> str:
            print(f"[End] Result: {result}")
            return result

        return NodeCompose(log_start, self._inner, log_end)


@Node()
async def do_work() -> str:
    print("  Working...")
    return "ok"


async def main() -> None:
    comp = (TimedWrapper(do_work) >> NOP).render()
    await WorkflowInterpreter(comp).run()


if __name__ == "__main__":
    asyncio.run(main())
