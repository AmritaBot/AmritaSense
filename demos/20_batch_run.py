"""20_batch_run.py — BATCH_RUN concurrent execution demo

Usage:
    python demos/20_batch_run.py
"""

import asyncio

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.instructions.batch import BATCH_RUN

# --- Parallel bare nodes ---


@Node()
async def fetch_users() -> None:
    await asyncio.sleep(0.1)
    print("  [users] fetched")


@Node()
async def fetch_orders() -> None:
    await asyncio.sleep(0.15)
    print("  [orders] fetched")


@Node()
async def fetch_products() -> None:
    await asyncio.sleep(0.12)
    print("  [products] fetched")


# --- Parallel subgraphs ---


@Node()
async def validate() -> None:
    print("  [validate] done")


@Node()
async def enrich() -> None:
    print("  [enrich] done")


@Node()
async def clean() -> None:
    print("  [clean] done")


@Node()
async def transform() -> None:
    print("  [transform] done")


# --- fail_fast demo ---


@Node()
async def risky_node() -> None:
    raise ValueError("Simulated failure in risky_node")


@Node()
async def safe_node() -> None:
    print("  [safe] completed despite sibling failure")


async def main() -> None:
    print("=== Demo 1: Parallel bare nodes ===")
    workflow = BATCH_RUN(fetch_users, fetch_orders, fetch_products)
    await WorkflowInterpreter(workflow.as_compose().render()).run()

    print("\n=== Demo 2: Parallel subgraphs ===")
    branch_a = validate >> enrich
    branch_b = clean >> transform
    workflow2 = BATCH_RUN(branch_a, branch_b)
    await WorkflowInterpreter(workflow2.as_compose().render()).run()

    print("\n=== Demo 3: fail_fast=False ===")
    workflow3 = BATCH_RUN(risky_node, safe_node, fail_fast=False)
    try:
        await WorkflowInterpreter(workflow3.as_compose().render()).run()
    except Exception as e:
        print(f"  Exception caught: {e!r}")


if __name__ == "__main__":
    asyncio.run(main())
