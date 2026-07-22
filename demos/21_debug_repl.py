#!/usr/bin/env python3
"""Demo: AmritaSense REPL Debugger — interactive debugging workflow.

This script demonstrates the complete REPL debugging toolkit::

    from amrita_sense.debugger import *

**All functions are sync** — no ``await``, no ``asyncio.run`` needed.
Just call them directly in a REPL.

It walks through:
  1.  inspect / where / list_nodes             — state inspection
  2.  step / step_over / cont                  — execution control
  3.  break_at_tag / break_at_addr             — breakpoints
  4.  list_breaks / clear_break_tag            — breakpoint management
  5.  crash → inspect → recover                — panic/recover flow
  6.  list_sub_intp                            — sub-interpreter tree

Run this demo::

    python demos/21_debug_repl.py

Or, for a genuine REPL experience, start a Python REPL and type::

    >>> from amrita_sense.debugger import *
    >>> from demos.21_debug_repl import inter
    >>> inspect(inter)
    >>> step(inter)     # no await !
"""

from __future__ import annotations

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.debugger import (
    backtrace,
    break_at_addr,
    break_at_tag,
    clear_break_tag,
    cont,
    inspect,
    list_breaks,
    list_nodes,
    list_sub_intp,
    step,
    step_over,
    where,
)

#  Build a demo workflow


@Node(tag="start")
async def start_node() -> str:
    """First node — sets up initial state."""
    print("  [start] running…")
    return "hello"


@Node(tag="middle")
async def middle_node() -> None:
    """Middle node — does some work."""
    print("  [middle] running…")


@Node(tag="crash_here")
def crash_node() -> None:
    """This node always crashes — great for testing panic/recover."""
    print("  [crash_here] about to explode 💥")
    msg = "planned crash for demo"
    raise RuntimeError(msg)


@Node(tag="never_reached")
def never_reached() -> None:
    """Should never execute unless we recover from the crash."""
    print("  [never_reached] recovered successfully! 🎉")


#  Create the interpreter

# Workflow: start → middle → crash_here → never_reached
COMPOSE = (start_node >> middle_node >> crash_node >> never_reached).render()
inter = WorkflowInterpreter(COMPOSE)


#  Demo runner


def demo() -> None:
    """Run the full debugger demo — all calls are sync, no await."""
    print("=" * 58)
    print("AmritaSense Debugger — REPL Demo  (sync)")
    print("=" * 58)

    #  1. Inspection
    print("\n▶ 1. INSPECT (initial state)")
    print("-" * 40)
    inspect(inter)

    print("\n▶ 2. list_nodes")
    print("-" * 40)
    list_nodes(inter)

    #  2. Step-by-step execution
    print("\n▶ 3. step()  (execute start_node)")
    print("-" * 40)
    step(inter)
    where(inter)

    print("\n▶ 4. step_over()  (skip middle_node)")
    print("-" * 40)
    step_over(inter)
    where(inter)

    #  3. Crash & panic
    print("\n▶ 5. step()  (into crash_node 💥)")
    print("-" * 40)
    step(inter)  # panic state saved internally
    print("  step() suppressed the exception — interpreter is in PANIC")

    print("\n▶ 6. inspect  (panic state)")
    print("-" * 40)
    inspect(inter)

    #  4. Recover from panic
    print("\n▶ 7. Skip past crash & cont() to never_reached")
    print("-" * 40)
    inter.advance_pointer()  # manually skip crashing node
    where(inter)
    break_at_tag(inter, "never_reached")
    cont(inter)  # recovers from panic internally
    print("  Reached never_reached after skipping crash! 🎉")

    #  5. Breakpoints
    print("\n▶ 8. breakpoints: set, list, hit, clear")
    print("-" * 40)
    break_at_tag(inter, "start")
    break_at_addr(inter, [1])  # middle node
    list_breaks(inter)

    print("\n   cont() → should hit breakpoint at 'start'…")
    cont(inter)
    where(inter)

    print("\n   cont() again → should hit breakpoint at addr [1]…")
    cont(inter)
    where(inter)

    print("\n   clear_break_tag → remove 'start' breakpoint")
    clear_break_tag(inter, "start")
    list_breaks(inter)

    #  6. Backtrace
    print("\n▶ 9. backtrace")
    print("-" * 40)
    backtrace(inter)

    #  7. Sub-interpreters
    print("\n▶ 10. list_sub_intp (sub-interpreter tree)")
    print("-" * 40)
    list_sub_intp(inter)

    print("\n" + "=" * 58)
    print("Demo complete! Try it yourself in the REPL:")
    print("  >>> from amrita_sense.debugger import *")
    print("  >>> step(inter)   # no await needed!")
    print("=" * 58)


if __name__ == "__main__":
    demo()
