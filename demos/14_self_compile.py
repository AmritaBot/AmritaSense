"""14_self_compile.py — Custom SelfCompileInstruction

Usage:
    python demos/14_self_compile.py
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.node.core import BaseNode
from amrita_sense.node.self_compile import SelfCompileInstruction


class TimedWrapper(SelfCompileInstruction):
    """Custom self-compile instruction: logs timing marks around execution"""

    def __init__(self, inner_node: BaseNode) -> None:
        self._inner = inner_node

    def extract(self):
        from amrita_sense.node.core import NodeCompose

        # Return values are not auto-injected between nodes —
        # capture the inner node's result via a closure box instead.
        box: dict[str, str] = {}

        @Node()
        def log_start() -> None:
            print("[Start]")

        @Node()
        async def capture() -> None:
            box["result"] = await self._inner.func()

        @Node()
        def log_end() -> None:
            print(f"[End] Result: {box['result']}")

        return NodeCompose(log_start, capture, log_end)


@Node()
async def do_work() -> str:
    print("  Working...")
    return "ok"


async def main() -> None:
    # SelfCompileInstruction can be passed straight to the interpreter
    # (it extracts + renders internally) — no trailing NOP needed.
    await WorkflowInterpreter(TimedWrapper(do_work)).run()


if __name__ == "__main__":
    asyncio.run(main())
