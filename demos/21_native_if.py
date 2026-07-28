"""21_native_if.py — NATIVE_IF / NATIVE_WHILE / NATIVE_DO demo.

Usage:
    python demos/21_native_if.py
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


@Node()
async def while_body() -> None:
    print("  WHILE body iteration")


@Node()
async def do_body() -> None:
    print("  DO body iteration")


async def main() -> None:
    ### NATIVE_IF single node ###
    print("=== NATIVE_IF (condition True) ===")
    comp = NATIVE_IF(cond_true, if_body).ELSE(else_body)
    await WorkflowInterpreter(comp.extract().render()).run()

    print("\n=== NATIVE_IF (condition False → ELSE) ===")
    comp = NATIVE_IF(cond_false, if_body).ELSE(else_body)
    await WorkflowInterpreter(comp.extract().render()).run()

    ### NATIVE_WHILE single node (1 iteration then false) ###
    print("\n=== NATIVE_WHILE (1 iteration) ===")
    counter = [0]

    @Node()
    async def wh_cond() -> bool:
        counter[0] += 1
        print(f"  WHILE cond iteration {counter[0]}")
        return counter[0] <= 1

    @Node()
    async def wh_body() -> None:
        print(f"  WHILE body iteration {counter[0]}")

    comp = NATIVE_WHILE(wh_cond).ACTION(wh_body)
    await WorkflowInterpreter(comp.extract().render()).run()

    ### NATIVE_DO single node ###
    print("\n=== NATIVE_DO (1 iteration) ===")
    counter2 = [0]

    @Node()
    async def do_cond() -> bool:
        counter2[0] += 1
        print(f"  DO cond iteration {counter2[0]}")
        return counter2[0] < 1  # execute twice then stop

    @Node()
    async def do_bd() -> None:
        print(f"  DO body iteration {counter2[0] + 1}")

    comp = NATIVE_DO(do_bd).WHILE(do_cond)
    await WorkflowInterpreter(comp.extract().render()).run()

    ### NATIVE_IF with NodeCompose body (bubble) ###
    print("\n=== NATIVE_IF bubble body ===")

    @Node()
    async def bubble_step_a() -> None:
        print("  bubble step A")

    @Node()
    async def bubble_step_b() -> None:
        print("  bubble step B")

    comp = NATIVE_IF(cond_true, bubble_step_a >> bubble_step_b)
    await WorkflowInterpreter(comp.extract().render()).run()

    print("\n=== ALL DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
