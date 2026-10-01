#!/usr/bin/env python3
"""Benchmark framework for AmritaSense — multi-run averaged, with variance.

Provides:
  - @benchmark decorator to register scenarios.
  - invoke() to run all registered scenarios multiple times and return
    the averaged Result objects.
  - report() to pretty-print the results table.
  - An optional JSON export holding every raw sample, so two revisions can be
    diffed mechanically instead of eyeballed.

Measurement notes
-----------------
* Timings come from ``time.perf_counter_ns`` (monotonic, nanosecond
  resolution) rather than wall-clock ``datetime.now()``.
* The GC is paused inside every measured region — a single collection can
  otherwise dominate a scenario that finishes in tens of microseconds.
* Every scenario is optionally run once up front without being recorded, so
  first-call cold state (address cache, DI cache, import-time lazily built
  tables) does not leak into the mean.
* Scenarios that flip ``_unsafe.__flags__`` must do it through
  :func:`unsafe_flags`; the flag object refuses a second write to a
  non-writable flag, so hand-rolled set/reset sequences poison every scenario
  that runs afterwards.

All scenario globals (RUNS, CHAIN_LEN, BRANCH_DEPTHS, …) are preserved.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

from typing_extensions import Self

from amrita_sense import (
    ALIAS,
    ARCHIVED_NODES,
    CALL,
    IF,
    INVOKE,
    JMP,
    NOP,
    RESET,
    TRIGGER_EVENT,
    WHILE,
    EventRegistry,
    Node,
    NodeCompose,
    NodeComposeRendered,
    NodeType,
    Try,
    WorkflowInterpreter,
    _unsafe,
)
from amrita_sense.hook.event import ConstructableEvent
from amrita_sense.hook.matcher import Depends
from amrita_sense.hook.on import on_event
from amrita_sense.instructions import INT, IRET, PUSH_CONTEXT, RET, SUSPEND
from amrita_sense.instructions.batch import BATCH_RUN
from amrita_sense.instructions.func_block import FUN_BLOCK
from amrita_sense.instructions.native import NATIVE_DO, NATIVE_IF, NATIVE_WHILE
from amrita_sense.instructions.subprogram import ARCHIVED_SEGMENT
from amrita_sense.instructions.workfl_ctrl import NOP as NOP_NODE

#  Global configuration

RUNS = int(os.environ.get("BENCHMARK_RUNS", "5"))
PREWARM = 10_000_000
DISABLE_GC_DURING_TIMING = True
WARMUP_PER_SCENARIO = True

# Scenario constants (global, preserved)

CHAIN_LEN = 200
BRANCH_DEPTHS = [3, 10, 30, 100]
LOOP_ITERS = 1000
COMPILE_NODES = 100000
BATCH_RUN_NODES = 100
BATCH_RUN_FORKS = 100
BATCH_RUN_PERFORK_NODES = 100

# Scenario constants (added alongside the new coverage)

JUMP_COUNT = 200
JUMP_SKIP = 10
CALL_COUNT = 200
INVOKE_COUNT = 200
INTERRUPT_COUNT = 100
CONTEXT_COUNT = 100
EVENT_HANDLER_COUNTS = [10, 100, 1000]
DI_UNIQUE_NODES = 64
DI_REPEATS = 8
DI_PRELOAD_BATCHES = [10, 100]
CONCURRENT_INTERPRETERS = 8
CONCURRENT_CHAIN = 50
MEMORY_CHAIN_LEN = 5000

# Set env vars
os.environ["LOG_LEVEL"] = "WARNING"

# Flags live in `amrita_sense._unsafe`; always flip them via `unsafe_flags`
# so a failing scenario cannot leave a flag set for the next one.


#  Result type


@dataclass
class Result:
    label: str
    group: str = "misc"
    sense_compile_s: float = 0.0
    sense_exec_s: float = 0.0
    compile_sd: float = 0.0
    exec_sd: float = 0.0
    mem_peak_kb: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)
    compile_samples: list[float] = field(default_factory=list)
    exec_samples: list[float] = field(default_factory=list)

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


def invoke(
    runs: int = RUNS,
    verbose: bool = True,
    warmup: bool = WARMUP_PER_SCENARIO,
) -> list[Result]:
    """Run every registered benchmark `runs` times.

    Returns a list of averaged `Result` objects (one per scenario), each
    carrying its raw samples plus the mean / standard deviation.
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
        if warmup:
            fn()
        collected: list[Result] = []
        for run in range(1, runs + 1):
            r = fn()
            collected.append(r)
            if verbose:
                print(
                    f"  run {run}/{runs}  "
                    f"S: compile={r.sense_compile_s:.6f}s  "
                    f"exec={r.sense_exec_s:.6f}s  total={r.sense_total:.6f}s"
                )
        mean = _mean_results(collected)
        if verbose:
            print(
                f"  >>> MEAN  S: total={mean.sense_total:.6f}s "
                f"(±{mean.exec_sd * 1000:.4f}ms on exec)\n"
            )
        final.append(mean)

    if verbose:
        report(final)
    return final


def _render_table(results: list[Result]) -> str:
    """Markdown table of averaged results; shared by stdout and the CI summary."""
    has_mem = any(r.mem_peak_kb > 0 for r in results)
    lines = [f"RESULTS  (mean of {RUNS} runs, ±1 stdev)", ""]

    header = "| Group | Scenario | compile | exec | total | exec sd |"
    rule = "|---|---|:---:|:---:|:---:|:---:|"
    if has_mem:
        header += " peak mem |"
        rule += ":---:|"
    lines += [header, rule]

    last_group: str | None = None
    for r in results:
        shown_group = "" if r.group == last_group else r.group
        last_group = r.group
        row = (
            f"| {shown_group} "
            f"| {r.label} ({_fmt_extra(r.extra)}) "
            f"| {_ms(r.sense_compile_s)} "
            f"| {_ms(r.sense_exec_s)} "
            f"| {_ms(r.sense_total)} "
            f"| {_fmt_sd(r.exec_sd)} |"
        )
        if has_mem:
            row += f" {r.mem_peak_kb:.1f}KiB |"
        lines.append(row)
    return "\n".join(lines)


def report(results: list[Result]) -> None:
    """Pretty-print a table of averaged benchmark results."""
    print()
    print("=" * 104)
    print(_render_table(results))
    print("=" * 104)


def _fmt_extra(extra: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in extra.items()) or "-"


def _ms(v: float) -> str:
    if v <= 0:
        return "N/A"
    if v < 1e-3:
        return f"{v * 1e6:.2f}µs"
    return f"{v * 1000:.4f}ms"


def _fmt_sd(v: float) -> str:
    """A standard deviation of 0 is a real (if unhelpful) value, not 'N/A'."""
    if v < 1e-3:
        return f"{v * 1e6:.2f}µs"
    return f"{v * 1000:.4f}ms"


def _mean_results(results: list[Result]) -> Result:
    """Average all fields across a list of same-label Results."""
    head = results[0]
    comp = [r.sense_compile_s for r in results]
    exe = [r.sense_exec_s for r in results]
    return Result(
        label=head.label,
        group=head.group,
        sense_compile_s=statistics.fmean(comp),
        sense_exec_s=statistics.fmean(exe),
        compile_sd=statistics.stdev(comp) if len(comp) > 1 else 0.0,
        exec_sd=statistics.stdev(exe) if len(exe) > 1 else 0.0,
        mem_peak_kb=statistics.fmean(r.mem_peak_kb for r in results),
        extra=head.extra,
        compile_samples=comp,
        exec_samples=exe,
    )


#  Timing / flag / composition helpers


class _Timer:
    """Monotonic timer that optionally parks the GC for the measured region."""

    elapsed: float = 0.0

    def __enter__(self) -> Self:
        self._gc_was_enabled = gc.isenabled()
        if DISABLE_GC_DURING_TIMING and self._gc_was_enabled:
            gc.disable()
        self._start = time.perf_counter_ns()
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed = (time.perf_counter_ns() - self._start) / 1e9
        if getattr(self, "_gc_was_enabled", False):
            gc.enable()


@contextmanager
def unsafe_flags(**overrides: Any):
    """Temporarily set `_unsafe.__flags__`, restoring the previous values.

    The flag object raises on a repeated write to a non-writable flag, so the
    `_modified_flags` bookkeeping is cleared around every write.  Restoring
    happens in a `finally`, which keeps a failing scenario from poisoning the
    scenarios that follow it.
    """
    flags = _unsafe.__flags__
    names = set(overrides)
    saved = {name: getattr(flags, name) for name in names}
    flags._modified_flags -= names
    try:
        for name, value in overrides.items():
            setattr(flags, name, value)
        yield flags
    finally:
        flags._modified_flags -= names
        for name, value in saved.items():
            setattr(flags, name, value)
        flags._modified_flags -= names


def _noop_node(async_node: bool = False):
    """Build a fresh no-op node, sync or async."""
    if async_node:

        @Node()
        async def _async_noop() -> None:
            pass

        return _async_noop

    @Node()
    def _sync_noop() -> None:
        pass

    return _sync_noop


def _build_chain(count: int, node: Any) -> NodeCompose:
    comp = node.as_compose() if hasattr(node, "as_compose") else node
    for _ in range(count - 1):
        comp >>= node
    return comp


def _sense_compile(compose: NodeCompose) -> tuple[NodeComposeRendered, float]:
    """Compile workflow, return (rendered_graph, compile_time_sec)."""
    with _Timer() as t:
        rendered = compose.render()
    return rendered, t.elapsed


def _sense_compile_self(instr: Any) -> tuple[Any, float]:
    """Extract + render a SelfCompileInstruction (Try, TRIGGER_EVENT, …)."""
    with _Timer() as t:
        rendered = instr.extract().render()
    return rendered, t.elapsed


def _sense_exec(rendered: NodeComposeRendered) -> float:
    """Execute a pre‑compiled workflow, return execution_time_sec."""
    pc = WorkflowInterpreter[Any](rendered)
    with _Timer() as t:
        asyncio.run(pc.run())
    return t.elapsed


def _sense_exec_stepwise(rendered: NodeComposeRendered) -> float:
    """Execute through the step-by-step generator instead of `run()`."""

    async def _drive() -> None:
        pc = WorkflowInterpreter[Any](rendered)
        async for _ in pc.run_step_by():
            pass

    with _Timer() as t:
        asyncio.run(_drive())
    return t.elapsed


#  Benchmark scenario functions (decorated)


@benchmark
def bench_linear_chain() -> Result:
    """Linear chain (sync nodes)"""
    comp = _build_chain(CHAIN_LEN, _noop_node())
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="Linear chain (sync nodes)",
        group="control-flow",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"nodes": CHAIN_LEN},
    )


@benchmark
def bench_linear_chain_async() -> Result:
    """Linear chain (async nodes)"""
    comp = _build_chain(CHAIN_LEN, _noop_node(async_node=True))
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="Linear chain (async nodes)",
        group="control-flow",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"nodes": CHAIN_LEN},
    )


@benchmark
def bench_linear_chain_sync_nowrap() -> Result:
    """Linear chain (sync, thread wrap off)"""
    comp = _build_chain(CHAIN_LEN, _noop_node())
    rendered, cs = _sense_compile(comp)
    with unsafe_flags(FORCE_NOT_WRAP_TO_ASYNC=True):
        es = _sense_exec(rendered)
    return Result(
        label="Linear chain (sync, no thread wrap)",
        group="control-flow",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"nodes": CHAIN_LEN},
    )


@benchmark
def bench_stepwise_exec() -> Result:
    """Step-by-step exec (async chain)"""
    comp = _build_chain(CHAIN_LEN, _noop_node(async_node=True))
    rendered, cs = _sense_compile(comp)
    es = _sense_exec_stepwise(rendered)
    return Result(
        label="Step-by-step exec",
        group="control-flow",
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
        label=f"Branching ({depth} ELIF)",
        group="control-flow",
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
        label="Tight loop",
        group="control-flow",
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

    with unsafe_flags(SQUASHED_LOOP=True):
        wf = WHILE(check).ACTION(body).extract()
        rendered, cs = _sense_compile(wf)
        es = _sense_exec(rendered)

    return Result(
        label="Tight loop-Squashed",
        group="control-flow",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"iters": LOOP_ITERS},
    )


def _build_jump_chain(count: int, skip: int) -> NodeCompose:
    comp = NOP.as_compose()
    for i in range(count):
        target = f"jmp_target_{i}"
        comp >>= JMP(target)
        for _ in range(skip):
            comp >>= NOP_NODE
        comp >>= ALIAS(NOP, target)
    return comp


@benchmark
def bench_jump_chain() -> Result:
    """JMP chain"""
    comp = _build_jump_chain(JUMP_COUNT, JUMP_SKIP)
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="JMP chain",
        group="jump-and-call",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"jumps": JUMP_COUNT, "skipped": JUMP_SKIP},
    )


def _build_call_chain(count: int) -> NodeCompose:
    comp = NOP.as_compose()
    segment = NOP.as_compose()
    for i in range(count):
        entry = f"call_body_{i}"
        comp >>= CALL(entry)
        comp >>= NOP_NODE
        segment >>= ALIAS(_noop_node(), entry) >> RET()
    comp >>= ARCHIVED_SEGMENT(segment)
    return comp


@benchmark
def bench_call_ret() -> Result:
    """CALL / RET chain"""
    comp = _build_call_chain(CALL_COUNT)
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="CALL / RET chain",
        group="jump-and-call",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"calls": CALL_COUNT},
    )


def _build_invoke_chain(count: int) -> NodeCompose:
    comp = NOP.as_compose()
    archive: list[Any] = []
    for i in range(count):
        entry = f"invoke_target_{i}"
        comp >>= INVOKE(entry)
        archive.append(ALIAS(_noop_node(), entry))
    comp >>= ARCHIVED_NODES(*archive)
    return comp


@benchmark
def bench_invoke() -> Result:
    """INVOKE chain"""
    comp = _build_invoke_chain(INVOKE_COUNT)
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="INVOKE chain",
        group="jump-and-call",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"invokes": INVOKE_COUNT},
    )


def _build_interrupt_chain(count: int) -> NodeCompose:
    comp = NOP.as_compose()
    segment = NOP.as_compose()
    for i in range(count):
        handler = f"int_handler_{i}"
        comp >>= INT(handler, None)
        comp >>= NOP_NODE
        segment >>= ALIAS(_noop_node(), handler) >> IRET()
    comp >>= ARCHIVED_SEGMENT(segment)
    return comp


@benchmark
def bench_interrupt_iret() -> Result:
    """INT / IRET chain"""
    comp = _build_interrupt_chain(INTERRUPT_COUNT)
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="INT / IRET chain",
        group="interrupt",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"interrupts": INTERRUPT_COUNT},
    )


def _build_context_chain(count: int) -> NodeCompose:
    comp = NOP.as_compose()
    segment = NOP.as_compose()
    for i in range(count):
        resume = f"ctx_resume_{i}"
        sub = f"ctx_sub_{i}"
        comp >>= PUSH_CONTEXT(resume)
        comp >>= JMP(sub)
        comp >>= ALIAS(NOP, resume)
        comp >>= NOP_NODE
        segment >>= ALIAS(_noop_node(), sub) >> IRET()
    comp >>= ARCHIVED_SEGMENT(segment)
    return comp


@benchmark
def bench_push_context_iret() -> Result:
    """PUSH_CONTEXT / IRET chain"""
    comp = _build_context_chain(CONTEXT_COUNT)
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="PUSH_CONTEXT / IRET chain",
        group="interrupt",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"restores": CONTEXT_COUNT},
    )


@benchmark
def bench_reset() -> Result:
    """RESET (early exit)"""
    comp = NOP.as_compose() >> RESET >> _noop_node()
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="RESET (early exit)",
        group="interrupt",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={},
    )


@benchmark
def bench_suspend() -> Result:
    """SUSPEND (pause, context kept)"""
    comp = NOP.as_compose() >> _noop_node() >> SUSPEND >> _noop_node()
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="SUSPEND (pause, context kept)",
        group="interrupt",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={},
    )


@Node()
async def _boom() -> None:
    raise ValueError("benchmark")


@Node()
async def _catch_any(exc_val: ValueError) -> None:
    pass


@Node()
async def _ok() -> None:
    pass


@benchmark
def bench_try_success() -> Result:
    """Try (no exception, THEN)"""
    clause = Try(_ok).THEN(_noop_node()).CATCH(ValueError, _catch_any)
    rendered, cs = _sense_compile_self(clause)
    es = _sense_exec(rendered)
    return Result(
        label="Try (no exception, THEN)",
        group="exceptions",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={},
    )


@benchmark
def bench_try_caught() -> Result:
    """Try (exception caught)"""
    clause = Try(_boom).CATCH(ValueError, _catch_any)
    rendered, cs = _sense_compile_self(clause)
    es = _sense_exec(rendered)
    return Result(
        label="Try (exception caught)",
        group="exceptions",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={},
    )


@benchmark
def bench_try_caught_finally() -> Result:
    """Try (exception caught + FINALLY)"""
    clause = Try(_boom).CATCH(ValueError, _catch_any).FINALLY(_noop_node())
    rendered, cs = _sense_compile_self(clause)
    es = _sense_exec(rendered)
    return Result(
        label="Try (caught + FINALLY)",
        group="exceptions",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={},
    )


def _make_event_type(event_type: str) -> type[ConstructableEvent]:
    @dataclass
    class _BenchEvent(ConstructableEvent):
        @property
        def event_type(self) -> str:
            return event_type

        def get_event_type(self) -> str:
            return event_type

        @classmethod
        def constructor(cls):
            return cls()

    return _BenchEvent


def _register_event_handlers(event_type: str, count: int) -> None:
    # `block=True` (the default) stops the dispatch loop after the first
    # handler, which would make every handler-count scenario measure the same
    # single call.  `block=False` lets the whole list run.
    for _ in range(count):

        @on_event(event_type, block=False).handle()
        async def _handler() -> None:
            return None


def _setup_events() -> dict[int, type[ConstructableEvent]]:
    events: dict[int, type[ConstructableEvent]] = {}
    registry = EventRegistry()
    for count in EVENT_HANDLER_COUNTS:
        event_type = f"amrita_bench_event_{count}"
        events[count] = _make_event_type(event_type)
        _register_event_handlers(event_type, count)
        registered = sum(
            len(bucket) for bucket in registry.get_handlers(event_type).values()
        )
        if registered != count:
            raise RuntimeError(
                f"event handler registration mismatch for {event_type}: "
                f"expected {count}, registered {registered}"
            )
    return events


_EVENT_TYPES = _setup_events()


def _bench_event_dispatch(count: int) -> Result:
    event_cls = _EVENT_TYPES[count]
    comp = NOP.as_compose() >> TRIGGER_EVENT(event_cls)
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label=f"Event dispatch ({count} handlers)",
        group="events",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"handlers": count},
    )


@benchmark
def bench_event_dispatch_10() -> Result:
    """Event dispatch (10 handlers)"""
    return _bench_event_dispatch(10)


@benchmark
def bench_event_dispatch_100() -> Result:
    """Event dispatch (100 handlers)"""
    return _bench_event_dispatch(100)


@benchmark
def bench_event_dispatch_1000() -> Result:
    """Event dispatch (1000 handlers)"""
    return _bench_event_dispatch(1000)


async def _di_provider_a() -> int:
    return 1


async def _di_provider_b() -> str:
    return "b"


async def _di_provider_c() -> float:
    return 1.0


async def _di_provider_d() -> bytes:
    return b"d"


def _make_di_node():
    """A node whose resolution cost is wide enough for a cache to pay off."""

    @Node()
    async def _consumer(
        a: int = Depends(_di_provider_a),
        b: str = Depends(_di_provider_b),
        c: float = Depends(_di_provider_c),
        d: bytes = Depends(_di_provider_d),
    ) -> None:
        pass

    return _consumer


def _build_di_composition() -> NodeCompose:
    nodes = [_make_di_node() for _ in range(DI_UNIQUE_NODES)]
    comp = nodes[0].as_compose()
    for i in range(1, DI_UNIQUE_NODES * DI_REPEATS):
        comp >>= nodes[i % DI_UNIQUE_NODES]
    return comp


@benchmark
def bench_di_cache() -> Result:
    """DI resolve (cache on)"""
    comp = _build_di_composition()
    rendered, cs = _sense_compile(comp)
    es = _sense_exec(rendered)
    return Result(
        label="DI resolve (cache on)",
        group="dependency-injection",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"unique": DI_UNIQUE_NODES, "calls": DI_UNIQUE_NODES * DI_REPEATS},
    )


@benchmark
def bench_di_no_cache() -> Result:
    """DI resolve (cache off)"""
    comp = _build_di_composition()
    rendered, cs = _sense_compile(comp)
    with unsafe_flags(WORKFLOW_DI_NO_CACHE=True):
        es = _sense_exec(rendered)
    return Result(
        label="DI resolve (cache off)",
        group="dependency-injection",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"unique": DI_UNIQUE_NODES, "calls": DI_UNIQUE_NODES * DI_REPEATS},
    )


def _bench_di_preload(batch: int) -> Result:
    comp = _build_di_composition()
    rendered, cs = _sense_compile(comp)
    with unsafe_flags(
        WORKFLOW_DI_PRELOAD_CACHE=True,
        WORKFLOW_DI_PRELOAD_BATCH=batch,
    ):
        es = _sense_exec(rendered)
    return Result(
        label=f"DI preload (batch={batch})",
        group="dependency-injection",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"unique": DI_UNIQUE_NODES, "calls": DI_UNIQUE_NODES * DI_REPEATS},
    )


@benchmark
def bench_di_preload_10() -> Result:
    """DI preload (batch=10)"""
    return _bench_di_preload(10)


@benchmark
def bench_di_preload_100() -> Result:
    """DI preload (batch=100)"""
    return _bench_di_preload(100)


@benchmark
def bench_concurrent_interpreters() -> Result:
    """Concurrent interpreters (8)"""
    rendered = _build_chain(CONCURRENT_CHAIN, _noop_node(async_node=True)).render()

    async def _drive() -> None:
        interpreters = [
            WorkflowInterpreter[Any](rendered) for _ in range(CONCURRENT_INTERPRETERS)
        ]
        await asyncio.gather(*(pc.run() for pc in interpreters))

    with _Timer() as t:
        asyncio.run(_drive())

    return Result(
        label="Concurrent interpreters",
        group="concurrency",
        sense_compile_s=0.0,
        sense_exec_s=t.elapsed,
        extra={
            "interpreters": CONCURRENT_INTERPRETERS,
            "nodes": CONCURRENT_CHAIN,
        },
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
        label="Subgraph (1000)",
        group="composition",
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
        label="Compilation-only",
        group="composition",
        sense_compile_s=t,
        extra={"nodes": COMPILE_NODES},
    )


@benchmark
def bench_memory_deep_chain() -> Result:
    """Memory: build + compile + exec peak"""
    tracemalloc.start()
    try:
        comp = _build_chain(MEMORY_CHAIN_LEN, _noop_node(async_node=True))
        rendered, cs = _sense_compile(comp)
        pc = WorkflowInterpreter[Any](rendered)
        with _Timer() as t:
            asyncio.run(pc.run())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return Result(
        label="Memory: build+compile+exec peak",
        group="memory",
        sense_compile_s=cs,
        sense_exec_s=t.elapsed,
        mem_peak_kb=peak / 1024,
        extra={"nodes": MEMORY_CHAIN_LEN},
    )


@benchmark
def bench_batch_run() -> Result:
    """Batch run nodes"""
    batch = BATCH_RUN(*([NOP] * BATCH_RUN_NODES)).as_compose()
    rendered, time = _sense_compile(batch)
    called = _sense_exec(rendered)
    return Result(
        label="Batch run nodes",
        group="batch",
        sense_compile_s=time,
        sense_exec_s=called,
        extra={"nodes": BATCH_RUN_NODES},
    )


@benchmark
def bench_batch_run_forks() -> Result:
    """Batch run forks"""
    fork = NOP
    for i in range(BATCH_RUN_PERFORK_NODES - 1):
        fork >>= NOP

    batch = BATCH_RUN(*[fork for _ in range(BATCH_RUN_FORKS)]).as_compose()
    rendered, time = _sense_compile(batch)
    called = _sense_exec(rendered)
    return Result(
        label="Batch run forks",
        group="batch",
        sense_compile_s=time,
        sense_exec_s=called,
        extra={"forks": BATCH_RUN_FORKS, "perfork": BATCH_RUN_PERFORK_NODES},
    )


#  Native instruction benchmarks


@benchmark
def bench_native_if_chain() -> Result:
    """Native-IF chain (100 ELIF)"""
    depth = 100

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

    chain = NATIVE_IF(conds[0], _body)  # type: ignore[arg-type]
    for c in conds[1:]:
        chain = chain.ELIF(c, _body)  # type: ignore[arg-type]
    chain = chain.ELSE(_body).extract()

    rendered, cs = _sense_compile(chain)
    es = _sense_exec(rendered)

    return Result(
        label="Native-IF (100 ELIF)",
        group="native",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"depth": depth},
    )


@benchmark
def bench_native_while_tight() -> Result:
    """Native-WHILE tight loop"""
    counter = [0]

    @Node()
    def body() -> None:
        counter[0] += 1

    @Node()
    def check() -> bool:
        return counter[0] < LOOP_ITERS

    wf = NATIVE_WHILE(check).ACTION(body).extract()
    rendered, cs = _sense_compile(wf)
    es = _sense_exec(rendered)

    return Result(
        label="Native-WHILE tight",
        group="native",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"iters": LOOP_ITERS},
    )


@benchmark
def bench_native_do_tight() -> Result:
    """Native-DO tight loop"""
    counter = [0]

    @Node()
    def body() -> None:
        counter[0] += 1

    @Node()
    def check() -> bool:
        return counter[0] < LOOP_ITERS

    wf = NATIVE_DO(body).WHILE(check).extract()
    rendered, cs = _sense_compile(wf)
    es = _sense_exec(rendered)

    return Result(
        label="Native-DO tight",
        group="native",
        sense_compile_s=cs,
        sense_exec_s=es,
        extra={"iters": LOOP_ITERS},
    )


#  Reporting / export


def _stats(samples: list[float]) -> dict[str, float | None]:
    if not samples:
        return {"mean": None, "sd": None, "min": None, "max": None}
    return {
        "mean": statistics.fmean(samples),
        "sd": statistics.stdev(samples) if len(samples) > 1 else 0.0,
        "min": min(samples),
        "max": max(samples),
    }


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fp:
            for line in fp:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


def _package_version(name: str) -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version(name)
        except PackageNotFoundError:
            return "unknown"
    except ImportError:  # pragma: no cover
        return "unknown"


def environment_meta() -> dict[str, Any]:
    """Capture enough of the host to make two runs comparable."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "runs": RUNS,
        "gc_disabled_during_timing": DISABLE_GC_DURING_TIMING,
        "amrita_sense": _package_version("amrita-sense"),
        "git_commit": _git_commit(),
    }


def to_json(results: list[Result], path: str) -> None:
    """Dump every scenario plus its raw samples for trend diffing."""
    payload = {
        "meta": environment_meta(),
        "results": [
            {
                "label": r.label,
                "group": r.group,
                "extra": r.extra,
                "compile": _stats(r.compile_samples),
                "exec": _stats(r.exec_samples),
                "mem_peak_kb": r.mem_peak_kb,
            }
            for r in results
        ],
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, ensure_ascii=False)
        fp.write("\n")


def _scenario_detail(r: Result) -> str:
    return (
        f"group: {r.group}\n"
        f"params: {_fmt_extra(r.extra)}\n"
        f"compile: {r.sense_compile_s:.6f}s (sd {r.compile_sd:.6f})\n"
        f"exec: {r.sense_exec_s:.6f}s (sd {r.exec_sd:.6f})\n"
        f"total: {r.sense_total:.6f}s\n"
        f"peak mem: {r.mem_peak_kb:.1f}KiB\n"
        f"compile samples: {[round(v, 6) for v in r.compile_samples]}\n"
        f"exec samples: {[round(v, 6) for v in r.exec_samples]}"
    )


def to_junit(results: list[Result], path: str) -> None:
    """Emit a JUnit report so CI can render per-scenario timings as a check run.

    Every scenario is recorded as a passing test case; the timings and the raw
    samples travel in the case's `system-out`.  Nothing here is a pass/fail
    gate — the point is visibility, not enforcement.
    """
    suite = ElementTree.Element(
        "testsuite",
        {
            "name": "AmritaSense Benchmarks",
            "tests": str(len(results)),
            "failures": "0",
            "errors": "0",
            "skipped": "0",
            "time": f"{sum(r.sense_total for r in results):.6f}",
        },
    )
    properties = ElementTree.SubElement(suite, "properties")
    for key, value in environment_meta().items():
        ElementTree.SubElement(
            properties, "property", {"name": key, "value": str(value)}
        )
    for r in results:
        case = ElementTree.SubElement(
            suite,
            "testcase",
            {
                "classname": f"benchmark.{r.group}",
                "name": r.label,
                "time": f"{r.sense_total:.6f}",
            },
        )
        ElementTree.SubElement(case, "system-out").text = _scenario_detail(r)

    tree = ElementTree.ElementTree(suite)
    ElementTree.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def to_summary(results: list[Result], path: str) -> None:
    """Write the results table as Markdown, for $GITHUB_STEP_SUMMARY."""
    meta = environment_meta()
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("## Benchmark results\n\n")
        fp.write(
            f"`{meta['amrita_sense']}` on Python {meta['python']} "
            f"({meta['cpu']}, {meta['cpu_count']} cores), "
            f"commit `{meta['git_commit']}`\n\n"
        )
        fp.write(_render_table(results))
        fp.write("\n")


def main(argv: list[str] | None = None) -> int:
    global RUNS

    parser = argparse.ArgumentParser(description="AmritaSense benchmark suite")
    parser.add_argument(
        "--runs",
        type=int,
        default=RUNS,
        help=f"measured runs per scenario (default {RUNS})",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default=os.environ.get("BENCHMARK_JSON", "benchmark-results.json"),
        help="where to write the JSON export",
    )
    parser.add_argument("--no-json", action="store_true", help="skip the JSON export")
    parser.add_argument(
        "--junit",
        dest="junit_path",
        default=os.environ.get("BENCHMARK_JUNIT", "benchmark-results.xml"),
        help="where to write the JUnit XML report",
    )
    parser.add_argument(
        "--no-junit", action="store_true", help="skip the JUnit XML report"
    )
    parser.add_argument(
        "--summary",
        dest="summary_path",
        default=os.environ.get("BENCHMARK_SUMMARY", "benchmark-summary.md"),
        help="where to write the Markdown summary",
    )
    parser.add_argument(
        "--no-summary", action="store_true", help="skip the Markdown summary"
    )
    parser.add_argument(
        "--no-warmup", action="store_true", help="skip the per-scenario warm-up"
    )
    parser.add_argument("--quiet", action="store_true", help="only print the table")
    parser.add_argument(
        "--list", action="store_true", help="list registered scenarios and exit"
    )
    args = parser.parse_args(argv)

    if args.runs < 1:
        parser.error("--runs must be at least 1")

    RUNS = args.runs

    if args.list:
        for fn in _BENCHMARKS:
            label = (fn.__doc__ and fn.__doc__.strip()) or fn.__name__
            print(f"{fn.__name__}: {label}")
        return 0

    results = invoke(
        runs=RUNS,
        verbose=not args.quiet,
        warmup=not args.no_warmup,
    )
    if args.quiet:
        # `--quiet` drops the per-run chatter, not the results.
        report(results)

    if not args.no_json:
        to_json(results, args.json_path)
        print(f"\nJSON written to {args.json_path}")
    if not args.no_junit:
        to_junit(results, args.junit_path)
        print(f"JUnit XML written to {args.junit_path}")
    if not args.no_summary:
        to_summary(results, args.summary_path)
        print(f"Markdown summary written to {args.summary_path}")

    return 0


# Entry point

if __name__ == "__main__":
    raise SystemExit(main())
