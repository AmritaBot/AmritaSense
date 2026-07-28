"""Native fast-path control-flow instructions.

These replace the traditional ``call_sub``-based branching with the
lightweight ``PUSH / JMP / RET_FAR`` pattern, avoiding lock acquisition,
middleware invocation, and DI resolution on every branch entry.

Single-node bodies stay on the fast ``call_offset`` path with zero
additional overhead.
"""

from .do_native import NATIVE_DO
from .if_native import NATIVE_IF
from .while_native import NATIVE_WHILE

__all__ = ("NATIVE_DO", "NATIVE_IF", "NATIVE_WHILE")
