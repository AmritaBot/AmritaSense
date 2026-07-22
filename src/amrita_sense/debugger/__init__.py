"""AmritaSense Debugger (SenseDBG - SDB) ― REPL-first inspection & step-by-step control.

Import everything with::

    from amrita_sense.debugger import *

All functions take a :class:`WorkflowInterpreter` as their first argument.
Sync versions (``step``, ``cont``, …) work directly in a REPL.
Async versions (``step_async``, ``cont_async``, …) are available for use
inside existing event loops.

**Security:**  Set the environment variable ``REMOVE_DEBUGGER=true`` to
physically gut the module at import time.  Any attempt to access
``amrita_sense.debugger`` will then raise ``AttributeError``.  This
prevents SSTI-based leakage of debugger internals into production
environments.
"""

import os
import sys
import types

_DISABLED = os.getenv("REMOVE_DEBUGGER", "false").lower() in ("true", "1", "t")

if _DISABLED:
    __path__: list[str] = []
    __all__: list[str] = []

    class _DebuggerDisabled(types.ModuleType):
        """Proxy that blocks all attribute access on the disabled debugger."""

        def __getattr__(self, name: str) -> None:
            raise AttributeError(
                f"Debugger is disabled. Access to '{name}' is forbidden. "
                "Set environment var REMOVE_DEBUGGER=false to enable it."
            )

        def __dir__(self) -> list[str]:
            return []

    # Replace *this* module with the disabled proxy.
    sys.modules[__name__] = _DebuggerDisabled(__name__)  # type: ignore[assignment]

else:
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
