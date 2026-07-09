"""04_if_branch.py — IF / ELIF / ELSE conditional branching

Usage:
    python demos/04_if_branch.py
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


async def main() -> None:
    # Inline condition nodes via NodeType
    cond_a = NodeType(lambda: False, wrap_to_async=False, address_able=False, tag=None)
    cond_b = NodeType(lambda: True, wrap_to_async=False, address_able=False, tag=None)

    comp = IF(cond_a, grade_a).ELIF(cond_b, grade_b).ELSE(grade_c).extract()
    rendered = comp.render()
    interpreter = WorkflowInterpreter(rendered)
    await interpreter.run()


if __name__ == "__main__":
    asyncio.run(main())
