"""Deprecated instruction names kept for source compatibility with 0.8.x.

Everything in this module is scheduled for removal in 2.0.  Deprecation here is
**static only**: the `@deprecated` markers sit under `if TYPE_CHECKING`, so type
checkers and IDEs strike the old names through, while at runtime each name is a
plain reference to its replacement — no import-time warnings, no wrapper call.

Two limitations are worth knowing about:

* `INTERRUPT` / `INTERRUPT_KEEP_CTX` are module-level *constants*.  PEP 702 has
  no decorator form for variables, so they are silent aliases — a type checker
  will not flag them.  They are listed in the migration table in the docs.
* The old `CALL` (a single-step `call_sub`) is **not** aliased: its name was
  taken over by the far-call instruction, so `CALL(alias)` now means "push a
  return address and jump".  That rename is intentionally breaking; use
  `INVOKE` instead.

This module is a *thin* layer: the runtime objects live next to their
replacements, and the aliases below only attach the static markers to the names
re-exported by :mod:`amrita_sense.instructions` and :mod:`amrita_sense`.  Deep
imports such as `from amrita_sense.instructions.ret2 import PUSH_STACK` keep
working through the aliases defined in those modules, but those are plain
variables and therefore carry no static marker.
"""

from typing import TYPE_CHECKING, NoReturn

from amrita_sense.node import NodeType

from . import interrupt as _interrupt
from . import jump as _jump
from . import ret2 as _ret2
from . import workfl_ctrl as _workfl_ctrl
from .jump import JumpNode

if TYPE_CHECKING:
    from typing_extensions import deprecated

    @deprecated("Renamed to JMP")
    def GOTO(aliasOrIdata: str | list[int]) -> JumpNode: ...

    @deprecated("Renamed to PUSH_RET")
    def PUSH_STACK(alias_or_idata: str | list[int]) -> NodeType[None]: ...

    @deprecated("Renamed to RET")
    def RET_FAR() -> NodeType[None]: ...

    @deprecated(
        "Renamed to CALL(to_adr, *, from_adr=None) — the argument order changed"
    )
    def PUSH_AND_GOTO(
        from_adr: str | list[int] | None, to_adr: str | list[int]
    ) -> NodeType[None]: ...

    @deprecated("Renamed to INT")
    def INTERRUPT_INTO(
        jump_to: str | list[int],
        ret_to: str | list[int] | None = None,
        if_state: bool = False,
    ) -> NodeType[None]: ...

    @deprecated("Renamed to IRET")
    def INTERRUPT_RET(reset_mark: bool = True) -> NodeType[None]: ...

else:
    GOTO = _jump.GOTO
    PUSH_STACK = _ret2.PUSH_STACK
    RET_FAR = _ret2.RET_FAR
    PUSH_AND_GOTO = _ret2.PUSH_AND_GOTO
    INTERRUPT_INTO = _interrupt.INTERRUPT_INTO
    INTERRUPT_RET = _interrupt.INTERRUPT_RET


#  Constants cannot carry a PEP 702 marker, so these two are silent aliases.
INTERRUPT: NodeType[NoReturn] = _workfl_ctrl.RESET
"""Deprecated alias of :data:`~amrita_sense.instructions.workfl_ctrl.RESET`."""

INTERRUPT_KEEP_CTX: NodeType[NoReturn] = _workfl_ctrl.SUSPEND
"""Deprecated alias of :data:`~amrita_sense.instructions.workfl_ctrl.SUSPEND`."""

__all__ = [
    "GOTO",
    "INTERRUPT",
    "INTERRUPT_INTO",
    "INTERRUPT_KEEP_CTX",
    "INTERRUPT_RET",
    "PUSH_AND_GOTO",
    "PUSH_STACK",
    "RET_FAR",
]
