"""Runtime state objects shared by the interpreter and its instructions."""

from dataclasses import dataclass, field
from enum import IntFlag
from typing import Any

from amrita_sense.types import PointerVector, Stack


class Flags(IntFlag):
    """The interpreter's status register.

    The discrete control-flow bits live in one integer rather than in separate
    booleans so that snapshotting, restoring and clearing them is a single
    assignment, and so that `InterpreterContext` carries them atomically.
    """

    NONE = 0
    IF = 1 << 0
    """Inside an interrupt handler.  A nested `INT` is rejected while set."""
    HLT = 1 << 1
    """Halted on a node.  The next run has to step past it before executing."""
    JMP = 1 << 2
    """A jump already moved the pointer; the main loop must not advance it."""


#: Plain-int mirrors of the hot `Flags` bits, derived from the enum so they cannot drift; `flags & Flags.HLT` re-wraps the result via `EnumType.__call__` / `__new__` (measured ~930 ns) where `int(flags) & FLAG_HLT` is ~80 ns.
FLAG_IF = int(Flags.IF)
FLAG_HLT = int(Flags.HLT)
FLAG_JMP = int(Flags.JMP)


@dataclass
class InterpreterContext:
    ptr: PointerVector
    exception_ignored: tuple[
        type[BaseException], ...
    ]  # A snapshot of the exception ignored
    s_args: tuple | None = field(default=None)
    s_kwargs: dict[str, Any] | None = field(default=None)
    extra: dict[str, Any] = field(default_factory=dict)
    stack: Stack[PointerVector] | None = field(default=None)
    exception: Exception | None = field(default=None)
    flags: Flags = field(default=Flags.NONE)
    """Status register as of the snapshot.

    `dump_interpreter` strips `HLT` when building a snapshot: a snapshot is the
    state to come back to, and "the loop is parked on this node" is not part of
    it.  Restoring therefore never resurrects a halt.
    """
