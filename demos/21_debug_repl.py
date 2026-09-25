"""21_debug_repl.py — REPL debugger: inspect, step, breakpoints, crash recovery

This script demonstrates the complete REPL debugging toolkit::

    from amrita_sense.debugger import *

**All functions are sync** — no `await`, no `asyncio.run` needed.
Just call them directly in a REPL.

It walks through:
  1.  inspect / where / list_nodes / dis       — state inspection & disassembly
  2.  dis() on a multi-segment graph           — nested compose + DLL slot
  3.  step / step_over / cont                  — execution control
  4.  break_at_tag / break_at_addr             — breakpoints
  5.  list_breaks / clear_break_tag            — breakpoint management
  6.  crash → inspect → recover                — panic/recover flow
  7.  list_sub_intp                            — sub-interpreter tree

Run this demo::

    python demos/21_debug_repl.py

Or, for a genuine REPL experience, start a Python REPL and type::

    >>> from amrita_sense.debugger import *
    >>> from demos.21_debug_repl import inter
    >>> inspect(inter)
    >>> step(inter)     # no await !
"""

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.debugger import (
    backtrace,
    break_at_addr,
    break_at_tag,
    clear_break_tag,
    code_disp,
    cont,
    dis,
    inspect,
    list_breaks,
    list_nodes,
    list_sub_intp,
    step,
    step_over,
    where,
)
from amrita_sense.instructions import ALIAS, NOP
from amrita_sense.node import DLLCompose

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


#  A second workflow whose graph spans several segments: a nested composition
#  becomes its own segment, and a DLL slot becomes a placeholder segment whose
#  contents can be rebased later with `dll.apply()`.


@Node(tag="load")
def load_node() -> None:
    """Entry node of the segmented workflow."""
    print("  [load] running…")


@Node(tag="parse")
def parse_node() -> None:
    """Node inside the nested composition — segment [1]."""
    print("  [parse] running…")


@Node(tag="store")
def store_node() -> None:
    """Node inside the DLL slot — segment [2]."""
    print("  [store] running…")


dll_slot = DLLCompose(store_node.as_compose())
SEGMENTED = (
    load_node
    >> (parse_node >> store_node)  # occupies slot [1] → segment [1]
    >> dll_slot  # occupies slot [2] → segment [2]
    >> ALIAS(store_node, "restart")
    >> NOP
).render()
segmented_inter = WorkflowInterpreter(SEGMENTED)


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

    print("\n▶ 3. dis()  (GDB-style disassembly, PC window)")
    print("-" * 40)
    dis(inter)
    print("\n   dis(inter, around=None) → the whole workflow")
    dis(inter, around=None)

    print("\n▶ 4. dis()  on a multi-segment graph")
    print("-" * 40)
    print("   a nested composition becomes segment [1]; the DLL slot segment [2]")
    dis(segmented_inter, around=None)

    print("\n   step() walks across segment boundaries")
    print("   (AUTO_DIS off here, so only where() marks the position)")
    code_disp.AUTO_DIS = False
    try:
        for _ in range(4):
            step(segmented_inter)
            where(segmented_inter)
    finally:
        code_disp.AUTO_DIS = True

    #  2. Step-by-step execution
    print("\n▶ 5. step()  (execute start_node)")
    print("-" * 40)
    step(inter)
    where(inter)

    print("\n▶ 6. step_over()  (skip middle_node)")
    print("-" * 40)
    step_over(inter)
    where(inter)

    #  3. Crash & panic
    print("\n▶ 7. step()  (into crash_node 💥)")
    print("-" * 40)
    step(inter)  # panic state saved internally
    print("  step() suppressed the exception — interpreter is in PANIC")

    print("\n▶ 8. inspect  (panic state)")
    print("-" * 40)
    inspect(inter)

    #  4. Recover from panic
    print("\n▶ 9. Skip past the crash & cont() to the end")
    print("-" * 40)
    inter.advance_pointer()  # manually skip the crashing node
    where(inter)
    cont(inter)  # run_step_by() clears the panic state, then never_reached runs
    print("  never_reached ran after skipping the crash! 🎉")

    #  5. Breakpoints
    print("\n▶ 10. breakpoints: set, list, hit, clear")
    print("-" * 40)
    break_at_tag(inter, "start")
    break_at_addr(inter, [1])  # middle node
    list_breaks(inter)

    print("\n   cont() → the finished workflow restarts at [0] and stops at 'start'…")
    cont(inter)
    where(inter)

    print("\n   cont() again → 'start' runs, then stops at addr [1]…")
    cont(inter)
    where(inter)

    print("\n   clear_break_tag → remove the 'start' breakpoint")
    clear_break_tag(inter, "start")
    list_breaks(inter)

    #  6. Backtrace
    print("\n▶ 11. backtrace")
    print("-" * 40)
    backtrace(inter)

    #  7. Sub-interpreters
    print("\n▶ 12. list_sub_intp (sub-interpreter tree)")
    print("-" * 40)
    list_sub_intp(inter)

    print("\n" + "=" * 58)
    print("Demo complete! Try it yourself in the REPL:")
    print("  >>> from amrita_sense.debugger import *")
    print("  >>> step(inter)   # no await needed!")
    print("=" * 58)


if __name__ == "__main__":
    demo()
