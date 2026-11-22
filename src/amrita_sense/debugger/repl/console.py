"""Embedded Python console for the SenseDBG rescue REPL.

The outer REPL owns the command grammar; this module handles the ``py``
command, which hands the line over to a real Python interpreter so the user
can inspect and mutate anything the object model exposes.

Two details make it useful rather than merely present:

* top-level ``await`` is enabled, so ``await step_async(inter)`` works and runs
  on the interpreter's own loop instead of a throwaway one;
* edits to ``pc`` / ``flags`` / ``exc`` are re-applied on the way out, so the
  console is not a sandbox that silently discards your writes.
"""

from __future__ import annotations

import ast
import asyncio
import codeop
import contextlib
import sys
from code import InteractiveConsole
from typing import TYPE_CHECKING, Any

try:  # pragma: no cover - platform dependent
    import readline
    import rlcompleter
except ImportError:  # pragma: no cover - Windows without pyreadline
    readline = None  # type: ignore[assignment]
    rlcompleter = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from amrita_sense.debugger.repl.session import RescueSession

_MISSING = object()


def _restore(target: object, name: str, value: object) -> None:
    """Put an attribute back, deleting it when it did not exist before."""
    if value is _MISSING:
        with contextlib.suppress(AttributeError):
            delattr(target, name)
    else:
        setattr(target, name, value)


class RescueConsole(InteractiveConsole):
    """A Python console bound to one rescue session."""

    def __init__(self, session: RescueSession) -> None:
        super().__init__(locals=session.py_namespace())
        self.session = session
        self.compile = codeop.CommandCompiler()
        # py is the escape hatch; top-level await is part of Python, so accept it.
        self.compile.compiler.flags |= ast.PyCF_ALLOW_TOP_LEVEL_AWAIT

    def runcode(self, code: Any) -> None:  # type: ignore[override]
        """Execute one compiled block, keeping the console alive on errors.

        ``InteractiveConsole`` already swallows ``Exception``; this override
        keeps that behaviour while routing coroutine results to the session's
        loop and letting ``SystemExit`` mean "leave py, stay in the rescue".
        """
        try:
            result = eval(code, self.locals)
            if asyncio.iscoroutine(result):
                self.session.run_coroutine(result)
        except SystemExit:
            raise
        except BaseException:
            self.showtraceback()

    def enter(self, *, banner: str) -> None:
        """Run the console until EOF, ``exit()`` or Ctrl-D."""
        stream = self.session.echo if self.session.echo is not None else sys.stdout
        # sys.ps1 only exists in an interactive interpreter; a bot must not crash here.
        previous_ps1 = getattr(sys, "ps1", _MISSING)
        previous_ps2 = getattr(sys, "ps2", _MISSING)
        previous_completer = None
        if readline is not None and rlcompleter is not None:
            previous_completer = readline.get_completer()
            readline.set_completer(rlcompleter.Completer(self.locals).complete)
        sys.ps1, sys.ps2 = "py> ", "py. "
        try:
            # Tracebacks go to stderr; both streams share the session channel.
            with (
                contextlib.redirect_stdout(stream),
                contextlib.redirect_stderr(stream),
            ):
                with contextlib.suppress(SystemExit):
                    self.interact(banner=banner, exitmsg="")
        finally:
            _restore(sys, "ps1", previous_ps1)
            _restore(sys, "ps2", previous_ps2)
            if readline is not None and previous_completer is not None:
                readline.set_completer(previous_completer)
            applied = self.session.sync_from_namespace(self.locals)
            if applied:
                self.session.ok(f"[py] applied: {', '.join(applied)}")


def render_banner() -> str:
    """Banner shown on entry; spells out the exit semantics on purpose."""
    return (
        "SenseDBG python console — full access to `inter`.\n"
        "  await step_async(inter)  drives the workflow on its own loop\n"
        "  exit()  or Ctrl-D        returns to (sdb), keeps the session\n"
        "  pc / flags / exc         edits are applied on return\n"
        "  `del` on injected names  only affects this namespace"
    )


__all__ = ["RescueConsole", "render_banner"]
