"""Input loop for the SenseDBG rescue REPL.

The loop must live on a worker thread while the interpreter's event loop keeps
running, otherwise a single ``step`` command deadlocks the process (the sync
debugger wrappers join a future that only the blocked loop can complete).

Reading input goes through :func:`input` rather than ``sys.stdin.readline()``:
the latter bypasses :mod:`readline`, so arrow keys arrive as raw ``ESC [ D``
bytes and the cursor never moves.  ``input()`` installs GNU readline even on a
worker thread, which buys cursor movement, history and tab completion for free.

``SIGINT`` still cannot interrupt a blocking read from a non-main thread, so the
soft-interrupt flag is only useful while a command is running; the reader notes
an interrupt after the line is submitted.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
import signal
import sys
from typing import TYPE_CHECKING

from amrita_sense.debugger.repl.commands import REGISTRY, dispatch
from amrita_sense.debugger.repl.lexer import lex
from amrita_sense.debugger.repl.theme import (
    DIM,
    ERROR,
    PROMPT,
    Theme,
    color_enabled,
)

try:  # pragma: no cover - platform dependent
    import readline
except ImportError:  # pragma: no cover - Windows without pyreadline
    readline = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from amrita_sense.debugger.repl.session import RescueSession


def _history_path() -> pathlib.Path:
    """Where the REPL keeps history; overridable for tests and sandboxes."""
    override = os.environ.get("SDB_HISTORY")
    return pathlib.Path(override) if override else pathlib.Path.home() / ".sdb_history"


#: Names offered by tab completion: commands plus pseudo-registers.
_ACTIVE: "RescueSession | None" = None
_tag_cache: tuple[int, list[str]] | None = None

_COMPLETION_POOL = (
    *REGISTRY,
    "$pc",
    "$rp",
    "$flags",
    "$exc",
    "pc",
    "rp",
    "flags",
    "exc",
)


def _output(session: RescueSession):
    return session.echo if session.echo is not None else sys.stdout


def _prompt(session: RescueSession) -> str:
    inter = session.inter
    pc = session.read_pseudo("pc")
    if pc is None:
        return "(sdb) <end> "
    try:
        node = inter.get_graph().calc.find_addr_safe(list(pc))
        tag = getattr(node, "tag", None) or "?"
    except Exception:
        tag = "?"
    tag = str(tag).splitlines()[0][:24]
    address = ",".join(str(part) for part in pc)
    return f"(sdb) [{address}] {tag}> "


def _welcome(session: RescueSession) -> None:
    rule = session.theme.paint("=" * 62, DIM)
    session.write(rule)
    session.write(
        session.theme.paint(
            f"SenseDBG rescue — interpreter {session.inter.id[:12]}…", PROMPT
        )
    )
    exc = session.inter.get_exception()
    if exc is not None:
        session.write(session.theme.paint(f"panic: {type(exc).__name__}: {exc}", ERROR))
    session.write(
        f"pc={session.theme.paint(str(session.read_pseudo('pc')), PROMPT)}"
        f"  flags={session.read_pseudo('flags')}"
    )
    session.write(
        "`help` lists commands · `q` re-raises · `k` abandons · `py` = Python"
    )
    session.write(rule)


def _node_tags() -> list[str]:
    """Node tags of the active interpreter, cached per session."""
    global _tag_cache
    session = _ACTIVE
    if session is None:
        return []
    key = id(session.inter)
    if _tag_cache is not None and _tag_cache[0] == key:
        return _tag_cache[1]
    tags: list[str] = []
    seen: set[str] = set()
    try:
        from amrita_sense.debugger.inspect import _walk_graph

        for _addr, node in _walk_graph(session.inter.get_graph()):
            tag = getattr(node, "tag", None)
            if isinstance(tag, str) and tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
    except Exception:
        tags = []
    _tag_cache = (key, tags)
    return tags


def _complete(text: str, state: int) -> str | None:
    """Complete commands, pseudo-registers and ``tag:`` operands."""
    if text.startswith("tag:"):
        prefix = text[4:]
        matches = [f"tag:{tag}" for tag in _node_tags() if tag.startswith(prefix)]
    else:
        matches = [name for name in _COMPLETION_POOL if name.startswith(text)]
    return matches[state] if 0 <= state < len(matches) else None


def _setup_readline() -> None:
    """Give the reader the usual editing keys, history and completion.

    GNU readline and libedit accept different binding syntaxes, and
    python-build-standalone links libedit, so only the syntax matching the
    active backend is used — sending libedit syntax to GNU readline disturbs
    its default ``complete`` binding.
    """
    if readline is None:  # pragma: no cover - Windows
        return
    with contextlib.suppress(OSError):
        readline.read_history_file(_history_path())
    with contextlib.suppress(Exception):
        readline.set_history_length(500)
        readline.set_completer(_complete)
        readline.set_completer_delims(" \t\n")
        backend = readline.__doc__ or ""
        binding = "bind ^I rl_complete" if "libedit" in backend else "tab: complete"
        with contextlib.suppress(Exception):
            readline.parse_and_bind(binding)


def _teardown_readline() -> None:
    if readline is None:  # pragma: no cover - Windows
        return
    with contextlib.suppress(OSError):
        history = _history_path()
        history.parent.mkdir(parents=True, exist_ok=True)
        readline.write_history_file(history)
    with contextlib.suppress(Exception):
        readline.set_completer(None)


def _read_line(session: RescueSession, prompt: str) -> str | None:
    """Read one line with line editing; ``None`` means EOF."""
    stream = _output(session)
    # An interrupt pressed while typing must not cancel the *next* command.
    session.interrupted.clear()
    use_readline = readline is not None and stream is sys.stdout
    try:
        if use_readline:
            # input() needs the prompt: readline uses its width for the cursor column.
            line = input(session.theme.prompt(prompt, PROMPT))
        else:
            stream.write(session.theme.paint(prompt, PROMPT))
            with contextlib.suppress(Exception):
                stream.flush()
            line = input()
    except EOFError:
        stream.write("\n")
        return None
    except KeyboardInterrupt:  # pragma: no cover - main-thread fallback
        stream.write("\n")
        return ""
    if session.interrupted.is_set():
        session.interrupted.clear()
        session.warn("[interrupted] — only a running command can be cancelled")
    return line


def _thread_main(session: RescueSession) -> str:
    _welcome(session)
    while True:
        line = _read_line(session, _prompt(session))
        if line is None:
            return "quit"
        tokens = lex(line)
        reason = dispatch(session, tokens)
        if reason:
            return reason


async def run_repl(session: RescueSession, *, capture_sigint: bool = True) -> str:
    """Drive a rescue session until it ends.

    Args:
        session: The session to run.
        capture_sigint: Install a soft-interrupt handler for the duration.
            Disable it when the caller already owns SIGINT handling.

    Returns:
        ``"quit"`` or ``"kill"``.
    """
    global _ACTIVE
    loop = asyncio.get_running_loop()
    session.loop = loop
    _ACTIVE = session
    enabled = color_enabled(_output(session))
    session.color = enabled
    session.theme = Theme(enabled)
    previous = None
    if capture_sigint:
        with contextlib.suppress(ValueError, OSError):
            previous = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, session.on_sigint)
    _setup_readline()
    try:
        reason = await asyncio.to_thread(_thread_main, session)
    finally:
        _teardown_readline()
        global _tag_cache
        _ACTIVE = None
        _tag_cache = None
        if previous is not None:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(signal.SIGINT, previous)
        session.loop = None
    return reason or "quit"


__all__ = ["run_repl"]
