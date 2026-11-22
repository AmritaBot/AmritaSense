"""Rescue session state for the SenseDBG REPL.

A session owns exactly one interpreter, one snapshot, one Python namespace and
one driving lock.  Everything the REPL does goes through here so that the
"which interpreter am I debugging" question has a single answer.
"""

from __future__ import annotations

import asyncio
import builtins
import contextlib
import io
import sys
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from amrita_sense.debugger.repl.theme import ERROR, OK, WARN, Theme
from amrita_sense.runtime.types import Flags, PointerVector

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from amrita_sense.runtime.workflow import WorkflowInterpreter

#: Pseudo-registers exposed to the command layer and to ``py``.
PSEUDO_NAMES = ("pc", "rp", "flags", "exc")


class SessionError(RuntimeError):
    """Raised when an operation is not valid for the current session state."""


class NoActiveRescue(RuntimeError):
    """Raised when a rescue-specific accessor is called outside a session."""


@dataclass
class Snapshot:
    """The part of the interpreter state that ``undo`` restores."""

    pointer: list[int] | None
    ret_stack: list[list[int]]
    flags: int
    panic: Exception | None

    @classmethod
    def capture(cls, inter: WorkflowInterpreter) -> Snapshot:
        pointer = inter._pointer
        return cls(
            pointer=list(pointer.base_addr) if pointer else None,
            ret_stack=[list(item.base_addr) for item in inter._ret_addr_stack.stack],
            flags=int(inter.flags),
            panic=inter.get_exception(),
        )

    def restore(self, inter: WorkflowInterpreter) -> None:
        inter._pointer = (
            PointerVector(list(self.pointer)) if self.pointer else PointerVector()
        )
        stack = inter._ret_addr_stack
        stack.stack.clear()
        for addr in self.ret_stack:
            stack.stack.append(PointerVector(list(addr)))
        inter._flags = Flags(self.flags)
        inter._panic_exc = self.panic


class RescueSession:
    """One interactive rescue of one interpreter."""

    def __init__(
        self,
        inter: WorkflowInterpreter,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        echo: Any = None,
    ) -> None:
        self.inter = inter
        self.snapshot = Snapshot.capture(inter)
        self.loop = loop
        self.echo = echo
        self.interrupted = threading.Event()
        self.detached = False
        self.exit_reason: str | None = None
        self.py_locals: dict[str, Any] = {}
        self.last_tokens: list[str] | None = None
        self.color = False
        self.theme = Theme(False)
        self._driving = threading.Lock()
        self._history: list[str] = []

    # --------------------------------------------------------------- signal

    def on_sigint(self, signum: int, frame: Any) -> None:
        """Convert Ctrl-C into a soft interrupt the REPL can poll."""
        self.interrupted.set()

    # ------------------------------------------------------------------ io

    def write(self, text: str = "") -> None:
        """Write one line (or a pre-rendered block) to the session output."""
        stream = self.echo if self.echo is not None else sys.stdout
        stream.write(text)
        if not text.endswith("\n"):
            stream.write("\n")
        with contextlib.suppress(Exception):
            stream.flush()

    def error(self, text: str) -> None:
        """Report a failure; the leading ``!`` stays greppable without colour."""
        self.write(self.theme.paint(f"! {text}", ERROR))

    def warn(self, text: str) -> None:
        self.write(self.theme.paint(text, WARN))

    def ok(self, text: str) -> None:
        self.write(self.theme.paint(text, OK))

    def note(self, text: str) -> None:
        """Secondary information.

        Deliberately uncoloured: ``DIM`` (bright black) is close to invisible on
        dark terminals, and this carries help text the user has to read.
        """
        self.write(text)

    # --------------------------------------------------------- pseudo regs

    def read_pseudo(self, name: str) -> Any:
        """Read a pseudo-register (``pc``/``rp``/``flags``/``exc``)."""
        key = name.lstrip("$").lower()
        inter = self.inter
        if key == "pc":
            pointer = inter._pointer
            return list(pointer.base_addr) if pointer else None
        if key == "rp":
            stack = inter._ret_addr_stack.stack
            return list(stack[-1].base_addr) if stack else None
        if key == "flags":
            return int(inter.flags)
        if key == "exc":
            return inter.get_exception()
        raise SessionError(f"unknown register: {name}")

    def write_pseudo(self, name: str, value: Any) -> None:
        """Write a pseudo-register, validating the pointer before it lands."""
        key = name.lstrip("$").lower()
        inter = self.inter
        if key == "pc":
            addr = _as_addr(value)
            self.validate_addr(addr)
            inter._pointer = PointerVector(addr)
            return
        if key == "flags":
            try:
                inter._flags = Flags(int(value))
            except (TypeError, ValueError) as exc:
                raise SessionError(f"flags must be an int, got {value!r}") from exc
            return
        if key == "exc":
            if value is not None and not isinstance(value, Exception):
                raise SessionError("exc must be an exception instance or None")
            inter._panic_exc = value
            return
        if key == "rp":
            raise SessionError("rp is read-only; edit the return stack in py")
        raise SessionError(f"unknown register: {name}")

    def validate_addr(self, addr: list[int]) -> None:
        """Reject addresses that the graph cannot resolve.

        An unresolvable PC turns the next ``cont`` into an IndexError, which
        then panics again and burns the nested-rescue budget for nothing.
        """
        if not addr:
            raise SessionError("empty address vector")
        try:
            node = self.inter.get_graph().calc.find_addr_safe(list(addr))
        except Exception as exc:
            raise SessionError(f"address {addr} is not resolvable: {exc}") from exc
        if node is None:
            raise SessionError(f"address {addr} does not exist in this graph")

    # ------------------------------------------------------------- driving

    def claim_driver(self) -> None:
        """Take the single driving token, or refuse loudly."""
        if not self._driving.acquire(blocking=False):
            raise SessionError(
                "another drive command is still running; wait for it to finish"
            )

    def release_driver(self) -> None:
        with contextlib.suppress(RuntimeError):
            self._driving.release()

    def run_coroutine(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Run *coro* on the interpreter's loop, polling for a soft interrupt.

        The REPL itself lives on a worker thread while the loop keeps the
        process alive, so a plain ``await`` is impossible here.  Polling the
        future instead of blocking on it is what makes Ctrl-C able to cancel a
        running command.
        """
        loop = self.loop
        if loop is None or loop.is_closed() or not loop.is_running():
            return asyncio.run(coro)
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        while True:
            try:
                return future.result(timeout=0.2)
            except FutureTimeoutError:  # noqa: PERF203 - polling is the point
                if self.interrupted.is_set():
                    self.interrupted.clear()
                    future.cancel()
                    raise KeyboardInterrupt("interrupted") from None

    # ------------------------------------------------------------ snapshot

    def undo(self) -> None:
        """Restore the state captured when the session opened."""
        self.snapshot.restore(self.inter)

    # --------------------------------------------------------- py namespace

    def py_namespace(self) -> dict[str, Any]:
        """Build the namespace handed to the embedded Python console.

        The debugger's public names are injected so ``step_async(inter)`` works
        without an import; ``sdb`` is also provided because imported ``inspect``
        shadows the stdlib module of the same name.
        """
        from amrita_sense import debugger as sdb_module
        from amrita_sense.debugger.rescue import get_rescue_intp, get_rescue_session

        namespace: dict[str, Any] = dict(self.py_locals)
        namespace.update(
            {
                "inter": self.inter,
                "sdb": sdb_module,
                "get_rescue_intp": get_rescue_intp,
                "get_rescue_session": get_rescue_session,
                "pc": self.read_pseudo("pc"),
                "rp": self.read_pseudo("rp"),
                "flags": self.read_pseudo("flags"),
                "exc": self.read_pseudo("exc"),
                "__builtins__": builtins,
                "__name__": "__sdb_console__",
            }
        )
        for name in getattr(sdb_module, "__all__", ()):
            namespace.setdefault(name, getattr(sdb_module, name))
        return namespace

    def sync_from_namespace(self, namespace: dict[str, Any]) -> list[str]:
        """Push edited namespace values back into the interpreter.

        Returns the list of registers that were applied.  Values that did not
        change are ignored, so a bare ``pc`` read never rewrites the pointer.
        """
        applied: list[str] = []
        for key in PSEUDO_NAMES:
            if key not in namespace:
                continue
            try:
                current = self.read_pseudo(key)
            except SessionError:
                continue
            candidate = namespace[key]
            if _same(current, candidate):
                continue
            try:
                self.write_pseudo(key, candidate)
            except SessionError as exc:
                self.write(f"! {key}: {exc}")
                continue
            applied.append(key)
        self.py_locals = {
            key: value
            for key, value in namespace.items()
            if key not in PSEUDO_NAMES
            and key
            not in {
                "inter",
                "sdb",
                "get_rescue_intp",
                "get_rescue_session",
                "__builtins__",
                "__name__",
            }
        }
        return applied

    # -------------------------------------------------------------- output

    def render_block(self, render: Any, *, color: bool | None = None) -> str:
        """Capture a print-based debugger view into a string.

        Colour is force-disabled first: ``code_disp`` caches its stdout TTY
        decision, so a redirect alone would still leave ANSI escapes in dumps.
        """
        from amrita_sense.debugger import code_disp

        previous = code_disp.COLOR
        buffer = io.StringIO()
        code_disp.COLOR = self.color if color is None else color
        try:
            with contextlib.redirect_stdout(buffer):
                render()
        except Exception as exc:
            return f"! view failed: {exc!r}"
        finally:
            code_disp.COLOR = previous
        return buffer.getvalue()


def _as_addr(value: Any) -> list[int]:
    if isinstance(value, PointerVector):
        return list(value.base_addr)
    if isinstance(value, (list, tuple)) and value:
        try:
            return [int(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise SessionError(f"address must be ints, got {value!r}") from exc
    raise SessionError(f"address must be a non-empty list, got {value!r}")


def _same(left: Any, right: Any) -> bool:
    try:
        return bool(left == right)
    except Exception:
        return False


__all__ = [
    "PSEUDO_NAMES",
    "NoActiveRescue",
    "RescueSession",
    "SessionError",
    "Snapshot",
]
