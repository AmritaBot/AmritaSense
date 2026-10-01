"""d04_if_branch.py — IF / ELIF / ELSE conditional branching

Usage:
    python demos/d04_if_branch.py
    python -i demos/d04_if_branch.py   # same, then use `inter` directly in the REPL
"""

import asyncio

from amrita_sense import IF, Node, NodeType, WorkflowInterpreter


@Node()
async def grade_a() -> str:
    print("Excellent")
    return "A"


@Node()
async def grade_b() -> str:
    print("Good")
    return "B"


@Node()
async def grade_c() -> str:
    print("Pass")
    return "C"


# Inline condition nodes via NodeType.
cond_a = NodeType(lambda: False, wrap_to_async=False, address_able=False, tag=None)
cond_b = NodeType(lambda: True, wrap_to_async=False, address_able=False, tag=None)

composition = IF(cond_a, grade_a).ELIF(cond_b, grade_b).ELSE(grade_c).extract()
# Module-level so a REPL can `from demos.d04_if_branch import inter` and step through the branches.
inter = WorkflowInterpreter(composition.render())


async def main() -> None:
    await inter.run()


if __name__ == "__main__":
    asyncio.run(main())
