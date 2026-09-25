"""AmritaSense Debugger (SenseDBG - SDB) ― REPL-first inspection & step-by-step control.

Import everything with::

from amrita_sense.debugger import *

All functions take a :class:`WorkflowInterpreter` as their first argument.
Sync versions (`step`, `cont`, …) work directly in a REPL.
Async versions (`step_async`, `cont_async`, …) are available for use
inside existing event loops.
"""

import os
import warnings

from amrita_sense.debugger.breakpoint import (
    Breakpoint,
    BreakpointHit,
    break_at_addr,
    break_at_tag,
    cleanup,
    clear_break_addr,
    clear_break_tag,
    list_breaks,
)
from amrita_sense.debugger.code_disp import dis, disassemble
from amrita_sense.debugger.inspect import (
    backtrace,
    inspect,
    list_nodes,
    list_sub_intp,
    where,
)
from amrita_sense.debugger.step import (
    cont,
    cont_async,
    step,
    step_async,
    step_out,
    step_out_async,
    step_over,
    step_over_async,
)

_DISABLED = os.getenv("REMOVE_DEBUGGER", "false").lower() in ("true", "1", "t")
if _DISABLED:
    warnings.warn(
        "This flag is no longer supported. The debugger is now always available.",
        DeprecationWarning,
        stacklevel=2,
    )

__all__ = [
    "Breakpoint",
    "BreakpointHit",
    "backtrace",
    "break_at_addr",
    "break_at_tag",
    "cleanup",
    "clear_break_addr",
    "clear_break_tag",
    "cont",
    "cont_async",
    "dis",
    "disassemble",
    "inspect",
    "list_breaks",
    "list_nodes",
    "list_sub_intp",
    "step",
    "step_async",
    "step_out",
    "step_out_async",
    "step_over",
    "step_over_async",
    "where",
]
