"""SenseDBG rescue REPL — command loop, session state and Python escape.

Public entry points live in :mod:`amrita_sense.debugger.rescue`; this package
only implements the machinery.
"""

from amrita_sense.debugger.repl.commands import REGISTRY, Command, dispatch
from amrita_sense.debugger.repl.console import RescueConsole, render_banner
from amrita_sense.debugger.repl.driver import run_repl
from amrita_sense.debugger.repl.lexer import fold, lex
from amrita_sense.debugger.repl.session import (
    NoActiveRescue,
    RescueSession,
    SessionError,
    Snapshot,
)

__all__ = [
    "REGISTRY",
    "Command",
    "NoActiveRescue",
    "RescueConsole",
    "RescueSession",
    "SessionError",
    "Snapshot",
    "dispatch",
    "fold",
    "lex",
    "render_banner",
    "run_repl",
]
