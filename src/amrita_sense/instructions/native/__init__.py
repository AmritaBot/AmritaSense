"""Native fast-path control-flow instructions.

These replace the traditional `call_sub`-based branching with the
lightweight `PUSH / JMP / CONTINUE / BREAK_LOOP` pattern, avoiding
lock acquisition, middleware invocation, and DI resolution on every
branch entry.

All body paths end with `CONTINUE()` — single-node bodies are
auto‑wrapped.  `BREAK_LOOP()` targets are configured at compile-time
via `_configure_loop_control_nodes()`.
"""

from .break_loop import BREAK_LOOP
from .continue_loop import CONTINUE
from .do_native import NATIVE_DO
from .if_native import NATIVE_IF
from .while_native import NATIVE_WHILE

__all__ = ("BREAK_LOOP", "CONTINUE", "NATIVE_DO", "NATIVE_IF", "NATIVE_WHILE")
