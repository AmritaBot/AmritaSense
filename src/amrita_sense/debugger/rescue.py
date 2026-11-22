"""Panic rescue for SenseDBG — the ``RESCUE_ON_PANIC`` implementation.

The contract is deliberately conservative: **rescuing never changes control
flow**.  After the REPL ends, the original exception is re-raised by the caller
(``WorkflowInterpreter.run``).  A debugger that silently swallows a failure is
worse than no debugger, so "rescue" here means "keep the body alive long enough
to look at it", not "make the error go away".

Without a TTY there is nobody to talk to, so the same information is attached
to the exception itself: a ``__sdb_report__`` attribute plus (on 3.11+) a
``add_note`` summary.  The exception's *type* is never changed — wrapping it
would silently break every ``except RuntimeError`` upstream.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import threading
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from amrita_sense.debugger.repl import NoActiveRescue, RescueSession, run_repl

if TYPE_CHECKING:
    from amrita_sense.runtime.workflow import WorkflowInterpreter

#: Serialises every push/pop so a session cannot be popped by the wrong thread.
_sessions: list[RescueSession] = []
_sessions_lock = threading.RLock()

_FORCE_ENV = "SDB_REPL_FORCE"
_DISABLE_ENV = "SDB_REPL_DISABLE"
_TRUTHY = {"1", "true", "yes", "on"}


# --------------------------------------------------------------- pty gate


def stdin_is_tty() -> bool:
    """Report whether stdin is an interactive terminal.

    ``isatty`` alone is not enough: a background process reading a tty is
    stopped by SIGTTIN (which looks exactly like a hang), and ``TERM=dumb``
    means line editing and colour are meaningless.  ``script``/``expect``
    still pass this check — the read timeout in the driver is the backstop.
    """
    if os.environ.get(_FORCE_ENV, "").lower() in _TRUTHY:
        return True
    if os.environ.get(_DISABLE_ENV, "").lower() in _TRUTHY:
        return False

    stream = sys.stdin
    if stream is None:
        return False
    try:
        fd = stream.fileno()
    except (OSError, ValueError, AttributeError):
        return False
    try:
        if not os.isatty(fd):
            return False
    except OSError:
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    with contextlib.suppress(OSError):
        if os.tcgetpgrp(fd) != os.getpgrp():
            return False
    return True


# ----------------------------------------------------------------- report


@dataclass
class PanicReport:
    """The state of a failed interpreter, rendered for non-interactive callers."""

    interpreter: str
    panic_type: str
    panic_message: str
    pointer: list[int] | None
    flags: int
    traceback: str = ""
    inspect: str = ""
    disassembly: str = ""
    backtrace: str = ""
    extras: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        """Short, log-safe form (no disassembly)."""
        address = self.pointer if self.pointer is not None else "<end>"
        return (
            f"[SenseDBG] interpreter={self.interpreter} "
            f"panic={self.panic_type}: {self.panic_message} "
            f"pc={address} flags={self.flags}"
        )

    def to_text(self) -> str:
        """Full report, suitable for a file dump."""
        lines = [
            "SenseDBG panic report",
            "=" * 62,
            f"interpreter : {self.interpreter}",
            f"panic       : {self.panic_type}: {self.panic_message}",
            f"pointer     : {self.pointer}",
            f"flags       : {self.flags}",
        ]
        for name, value in self.extras.items():
            lines.append(f"{name:<12}: {value}")
        for title, body in (
            ("traceback", self.traceback),
            ("inspect", self.inspect),
            ("backtrace", self.backtrace),
            ("disassembly", self.disassembly),
        ):
            if body:
                lines.extend(
                    ["", f"--- {title} " + "-" * max(1, 50 - len(title)), body]
                )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _capture(render: object) -> str:
    """Run a print-based debugger view and return its text, colour-free."""
    from amrita_sense.debugger import code_disp

    previous = code_disp.COLOR
    code_disp.COLOR = False
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            render()  # type: ignore[operator]
    except Exception as exc:
        return f"<unavailable: {exc!r}>"
    finally:
        code_disp.COLOR = previous
    return buffer.getvalue()


def build_report(inter: WorkflowInterpreter, exc: BaseException) -> PanicReport:
    """Collect the post-mortem state of *inter*."""
    from amrita_sense.debugger.code_disp import dis
    from amrita_sense.debugger.inspect import backtrace
    from amrita_sense.debugger.inspect import inspect as inspect_view

    pointer = inter._pointer
    report = PanicReport(
        interpreter=str(inter.id),
        panic_type=type(exc).__name__,
        panic_message=str(exc),
        pointer=list(pointer.base_addr) if pointer is not None else None,
        flags=int(inter.flags),
        traceback=inter._make_traceback(),
        inspect=_capture(lambda: inspect_view(inter)),
        backtrace=_capture(lambda: backtrace(inter)),
        disassembly=_capture(lambda: dis(inter)),
    )
    try:
        node = _current_node(inter)
        report.extras["node"] = (
            str(getattr(node, "tag", "<none>")) if node else "<none>"
        )
    except Exception:
        report.extras["node"] = "<unknown>"
    with contextlib.suppress(Exception):
        report.extras["running"] = str(inter.is_running)
    return report


def _current_node(inter: WorkflowInterpreter) -> object | None:
    with contextlib.suppress(Exception):
        pointer = inter._pointer
        if pointer is None:
            return None
        return inter.get_graph().calc.find_addr_safe(list(pointer.base_addr))
    return None


def attach_report(exc: BaseException, report: PanicReport) -> PanicReport:
    """Attach *report* to *exc* without changing its type."""
    with contextlib.suppress(Exception):
        exc.__sdb_report__ = report  # type: ignore[attr-defined]
    add_note = getattr(exc, "add_note", None)
    if callable(add_note):
        with contextlib.suppress(Exception):
            add_note(report.summary())
    return report


# ------------------------------------------------------------ session stack


def push_session(session: RescueSession) -> None:
    with _sessions_lock:
        _sessions.append(session)


def pop_session(session: RescueSession) -> None:
    with _sessions_lock, contextlib.suppress(ValueError):
        _sessions.remove(session)


def get_rescue_session() -> RescueSession:
    """Return the innermost active rescue session.

    Raises:
        NoActiveRescue: When called outside a rescue (including after it ends),
            rather than handing back a closed interpreter.
    """
    with _sessions_lock:
        if not _sessions:
            raise NoActiveRescue(
                "no active rescue session; this helper only works inside one"
            )
        return _sessions[-1]


def get_rescue_intp() -> WorkflowInterpreter:
    """Return the interpreter under rescue.

    Raises:
        NoActiveRescue: When called outside a rescue session.
    """
    return get_rescue_session().inter


def active_sessions() -> list[RescueSession]:
    """Snapshot of the session stack, outermost first."""
    with _sessions_lock:
        return list(_sessions)


# ------------------------------------------------------------------ rescue


async def rescue_on_panic(
    inter: WorkflowInterpreter,
    exc: BaseException,
    *,
    interactive: bool | None = None,
) -> str:
    """Handle a panic: open a REPL on a TTY, otherwise attach a report.

    Args:
        inter: The interpreter that panicked.
        exc: The exception that reached the top of ``run_step_by``.
        interactive: Override the TTY probe (tests, and callers that already
            know whether a human is present).

    Returns:
        ``"repl"``, ``"report"``, ``"quit"``, ``"kill"`` or ``"suppress"``.
    """
    use_repl = stdin_is_tty() if interactive is None else interactive
    if not use_repl:
        attach_report(exc, build_report(inter, exc))
        return "report"

    session = RescueSession(inter)
    push_session(session)
    try:
        reason = await run_repl(session)
        if reason == "suppress":
            # Keep the evidence reachable from the API, not just in the log.
            with contextlib.suppress(Exception):
                inter._panic_suppressed = True
        if reason in {"kill", "suppress"}:
            with contextlib.suppress(Exception):
                await inter._close_workflow_scope()
        return reason
    finally:
        pop_session(session)


__all__ = [
    "NoActiveRescue",
    "PanicReport",
    "active_sessions",
    "attach_report",
    "build_report",
    "get_rescue_intp",
    "get_rescue_session",
    "pop_session",
    "push_session",
    "rescue_on_panic",
    "stdin_is_tty",
]
