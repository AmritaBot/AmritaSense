#!/usr/bin/env python3
"""Benchmark framework for Amrita— multi-run averaged.

Provides:
  - @benchmark decorator to register scenarios.
  - invoke() to run all registered scenarios multiple times and return
    the averaged Result objects.
  - report() to pretty-print the results table.

All scenario globals (RUNS, CHAIN_LEN, BRANCH_DEPTHS, …) are preserved.
"""

from __future__ import annotations

import asyncio
import math
import os
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from amrita_sense import (
    IF,
    Node,
    NodeCompose,
    NodeComposeRendered,
    NodeType,
    WorkflowInterpreter,
    _unsafe,
)
from amrita_sense.instructions.batch import BATCH_RUN
from amrita_sense.instructions.func_block import FUN_BLOCK
from amrita_sense.instructions.loop.while_clause import WHILE
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.utils import TimeInsighter

#  Global configuration

RUNS = 5
PREWARM = 100000000

# Scenario constants (global, preserved)

CHAIN_LEN = 200
BRANCH_DEPTHS = [3, 10, 30, 100]
LOOP_ITERS = 1000
COMPILE_NODES = 100000
BATCH_RUN_NODES = 100
BATCH_RUN_FORKS = 100
BATCH_RUN_PERFORK_NODES = 100

# Set env vars
os.environ["LOG_LEVEL"] = "WARNING"

#  Result type


@dataclass
class Result:
    label: str
    sense_compile_s: float = 0.0
    sense_exec_s: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def sense_total(self) -> float:
        return self.sense_compile_s + self.sense_exec_s


#  Framework: registry, decorator, runner

_BENCHMARKS: list[Callable[[], Result]] = []


def benchmark(func: Callable[[], Result]) -> Callable[[], Result]:
    """Decorator: register a benchmark function that returns a Result."""
    _BENCHMARKS.append(func)
    return func


def _prewarm():
    print("Pre-warming...")
    for i in range(PREWARM):
        math.sqrt(12345.6789 + i)
    print("Done.")


def invoke(runs: int = RUNS, verbose: bool = True) -> list[Result]:
    """Run every registered benchmark ``runs`` times.

    Returns a list of averaged ``Result`` objects (one per scenario).
    If *verbose* is True, per-run timings and the final report are printed.
    """
    _prewarm()
    if verbose:
        print(f"Python {sys.version}")
        print(f"Runs per scenario: {runs}\n")

    final: list[Result] = []

    for fn in _BENCHMARKS:
        label = (fn.__doc__ and fn.__doc__.strip()) or fn.__name__
        if verbose:
            print(f"-- {label} --")
        collected: list[Result] = []
        for run in range(1, runs + 1):
            r = fn()
            collected.append(r)
            if verbose:
                print(
                    f"  run {run}/{runs}  "
                    f"S: compile={r.sense_compile_s:.6f}s  exec={r.sense_exec_s:.6f}s  total={r.sense_total:.6f}s"
                )
        mean = _mean_results(collected)
        if verbose:
            print(f"  >>> MEAN  S: total={mean.sense_total:.6f}s\n")
        final.append(mean)

    if verbose:
        report(final)
    return final


def report(results: list[Result]) -> None:
    """Pretty-print a table of averaged benchmark results."""
    print()
    print("=" * 80)
    print(f"RESULTS  (mean of {RUNS} runs)")
    print("=" * 80)
    hdr = "| Scenario | compile | exec | total |"
    print(hdr)
    print("|---|:---:|:---:|:---:|")

    for r in results:

        def _ms(v: float) -> str:
            return f"{v * 1000:.4f}ms" if v > 0 else "N/A"

        print(
            f"| {r.label} ({r.extra}) "
            f"| {_ms(r.sense_compile_s)} | {_ms(r.sense_exec_s)} | {_ms(r.sense_total)} |"
        )


def _mean_results(results: list[Result]) -> Result:
    """Average all fields across a list of same-label Results."""
    return Result(
        label=results[0].label,
        sense_compile_s=statistics.mean(r.sense_compile_s for r in results),
        sense_exec_s=statistics.mean(r.sense_exec_s for r in results),
        extra=results[0].extra,
    )


#  compilation / execution helpers


def _sense_compile(compose: NodeCompose) -> tuple[NodeComposeRendered, float]:
    """Compile workflow, return (rendered_graph, compile_time_sec)."""
    with TimeInsighter() as t:
        rendered = compose.render()
    return rendered, t.t_diff.total_seconds()


def _sense_exec(rendered: NodeComposeRendered) -> float:
    """Execute a pre‑compiled workflow, return execution_time_sec."""
    pc = WorkflowInterpreter[Any](rendered)
    with TimeInsighter() as t:
        asyncio.run(pc.run())
    return t.t_diff.total_seconds()


# Benchmark scenario functions (decorated)


@benchmark
def bench_linear_chain() -> Result:
    """Linear chain"""

    @Node()
    def _noop() -> None:
        pass

    comp: NodeCompose = _noop  # type: ignore[assignment]
    for _ in range(CHAIN_LEN - 1):
        comp >>= _noop

    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)

    return Result(
        "Linear chain",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"nodes": CHAIN_LEN},
    )


def _bench_branching_n(depth: int) -> Result:
    @Node()
    def _body() -> None:
        pass

    conds = [
        NodeType(lambda: False, wrap_to_async=False, address_able=False, tag=None)
        for _ in range(depth)
    ]
    conds[-1] = NodeType(
        lambda: True, wrap_to_async=False, address_able=False, tag=None
    )

    chain = IF(conds[0], _body)  # type: ignore[arg-type]
    for c in conds[1:]:
        chain = chain.ELIF(c, _body)  # type: ignore[arg-type]
    chain = chain.ELSE(_body).extract()

    rendered, cs = _sense_compile(chain)
    es = _sense_exec(rendered)

    return Result(
        f"Branching ({depth} ELIF)",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"depth": depth},
    )


@benchmark
def bench_branching_3() -> Result:
    """Branching (3 ELIF)"""
    return _bench_branching_n(3)


@benchmark
def bench_branching_10() -> Result:
    """Branching (10 ELIF)"""
    return _bench_branching_n(10)


@benchmark
def bench_branching_30() -> Result:
    """Branching (30 ELIF)"""
    return _bench_branching_n(30)


@benchmark
def bench_branching_100() -> Result:
    """Branching (100 ELIF)"""
    return _bench_branching_n(100)


@benchmark
def bench_tight_loop() -> Result:
    """Tight loop"""
    counter = [0]

    @Node()
    def body() -> None:
        counter[0] += 1

    @Node()
    def check() -> bool:
        return counter[0] < LOOP_ITERS

    wf = WHILE(check).ACTION(body).extract()
    rendered, cs = _sense_compile(wf)
    es = _sense_exec(rendered)

    return Result(
        "Tight loop",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"iters": LOOP_ITERS},
    )


@benchmark
def bench_tight_loop_squashed() -> Result:
    """Tight loop (Squashed)"""
    counter = [0]

    @Node()
    def body() -> None:
        counter[0] += 1

    @Node()
    def check() -> bool:
        return counter[0] < LOOP_ITERS

    # Squash the loop
    _unsafe.__flags__.SQUASHED_LOOP = True

    wf = WHILE(check).ACTION(body).extract()
    rendered, cs = _sense_compile(wf)
    es = _sense_exec(rendered)

    # Reset flags
    _unsafe.__flags__._modified_flags.clear()
    _unsafe.__flags__.SQUASHED_LOOP = False
    _unsafe.__flags__._modified_flags.clear()

    return Result(
        "Tight loop-Squashed",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"iters": LOOP_ITERS},
    )


@benchmark
def bench_subgraph_sense() -> Result:
    """Sense: 1000 sequential sub‑workflow invocations using FUN_BLOCK"""

    @Node()
    def node_a() -> None: ...

    na = node_a.as_compose().render()
    cmp = NOP.as_compose()
    for _ in range(1000):
        cmp >>= FUN_BLOCK(na)

    rendered, cs = _sense_compile(cmp)
    es = _sense_exec(rendered)

    return Result(
        "Subgraph (1000)",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"iterations": 1000},
    )


@benchmark
def bench_compile_only() -> Result:
    """Compilation-only"""

    @Node()
    def _noop() -> None:
        pass

    comp: NodeCompose = _noop  # type: ignore[assignment]
    for _ in range(COMPILE_NODES - 1):
        comp >>= _noop

    _, t = _sense_compile(comp)  # only compile, no execution

    return Result(
        "Compilation-only",
        sense_compile_s=t,
        extra={"nodes": COMPILE_NODES},
    )


@benchmark
def bench_batch_run() -> Result:
    """Batch run"""
    batch = BATCH_RUN(*([NOP] * BATCH_RUN_NODES)).as_compose()
    rendered, time = _sense_compile(batch)
    called = _sense_exec(rendered)
    return Result(
        "Batch run nodes",
        sense_compile_s=time,
        sense_exec_s=called,
        extra={"nodes": BATCH_RUN_NODES},
    )


@benchmark
def bench_batch_run_forks() -> Result:
    """Batch run"""
    fork = NOP
    for i in range(BATCH_RUN_PERFORK_NODES - 1):
        fork >>= NOP

    batch = BATCH_RUN(*[fork for _ in range(BATCH_RUN_FORKS)]).as_compose()
    rendered, time = _sense_compile(batch)
    called = _sense_exec(rendered)
    return Result(
        "Batch run forks",
        sense_compile_s=time,
        sense_exec_s=called,
        extra={"forks": BATCH_RUN_FORKS, "perfork": BATCH_RUN_PERFORK_NODES},
    )


# Entry point

if __name__ == "__main__":
    invoke()  # runs all @benchmark functions, prints report, returns results
