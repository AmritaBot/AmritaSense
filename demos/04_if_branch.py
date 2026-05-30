"""04_if_branch.py — IF / ELIF / ELSE conditional branching

Usage:
    python demos/04_if_branch.py
"""

import asyncio

from amrita_sense import IF, NOP, Node, WorkflowInterpreter


@Node()
async def check_score() -> int:
    """Simulate returning a score"""
    return 85


@Node()
async def grade_a(score: int) -> str:
    print(f"Score {score}: Excellent")
    return "A"


@Node()
async def grade_b(score: int) -> str:
    print(f"Score {score}: Good")
    return "B"


@Node()
async def grade_c(score: int) -> str:
    print(f"Score {score}: Pass")
    return "C"


@Node()
async def finished(grade: str) -> None:
    print(f"Final grade: {grade}")


async def main() -> None:
    comp = (
        IF(
            Node(lambda score: score >= 90, wrap_to_async=False),  # type: ignore[arg-type]
            grade_a,
        )
        .ELIF(Node(lambda score: score >= 75, wrap_to_async=False), grade_b)  # type: ignore[arg-type]
        .ELSE(grade_c)
        >> check_score
        >> finished
        >> NOP
    )
    rendered = comp.render()
    interpreter = WorkflowInterpreter(rendered)
    await interpreter.run()


if __name__ == "__main__":
    asyncio.run(main())
