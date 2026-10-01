"""20_native_if.py — NATIVE_IF / NATIVE_WHILE / NATIVE_DO demo.

Usage:
    python demos/20_native_if.py
    python -i demos/20_native_if.py   # same, then use `inter` / `else_inter` / `while_inter` / `do_inter` / `bubble_inter` in the REPL
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.instructions.native import NATIVE_DO, NATIVE_IF, NATIVE_WHILE


@Node()
async def cond_true() -> bool:
    print("  cond → True")
    return True


@Node()
async def cond_false() -> bool:
    print("  cond → False")
    return False


@Node()
async def if_body() -> None:
    print("  IF body executed")


@Node()
async def else_body() -> None:
    print("  ELSE body executed")


# Mutable boxes so the closure nodes can keep their state at module scope.
_while_counter = [0]


@Node()
async def wh_cond() -> bool:
    _while_counter[0] += 1
    print(f"  WHILE cond iteration {_while_counter[0]}")
    return _while_counter[0] <= 1


@Node()
async def wh_body() -> None:
    print(f"  WHILE body iteration {_while_counter[0]}")


_do_counter = [0]


@Node()
async def do_cond() -> bool:
    _do_counter[0] += 1
    print(f"  DO cond iteration {_do_counter[0]}")
    return _do_counter[0] < 1  # execute twice then stop


@Node()
async def do_body() -> None:
    print(f"  DO body iteration {_do_counter[0] + 1}")


@Node()
async def bubble_step_a() -> None:
    print("  bubble step A")


@Node()
async def bubble_step_b() -> None:
    print("  bubble step B")


# Module-level so a REPL can `from demos.20_native_if import inter, ...` and step through each native form.
inter = WorkflowInterpreter(
    NATIVE_IF(cond_true, if_body).ELSE(else_body).extract().render()
)
else_inter = WorkflowInterpreter(
    NATIVE_IF(cond_false, if_body).ELSE(else_body).extract().render()
)
while_inter = WorkflowInterpreter(
    NATIVE_WHILE(wh_cond).ACTION(wh_body).extract().render()
)
do_inter = WorkflowInterpreter(NATIVE_DO(do_body).WHILE(do_cond).extract().render())
bubble_inter = WorkflowInterpreter(
    NATIVE_IF(cond_true, bubble_step_a >> bubble_step_b).extract().render()
)


async def main() -> None:
    print("=== NATIVE_IF (condition True) ===")
    await inter.run()

    print("\n=== NATIVE_IF (condition False → ELSE) ===")
    await else_inter.run()

    print("\n=== NATIVE_WHILE (1 iteration) ===")
    await while_inter.run()

    print("\n=== NATIVE_DO (1 iteration) ===")
    await do_inter.run()

    print("\n=== NATIVE_IF bubble body ===")
    await bubble_inter.run()

    print("\n=== ALL DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
