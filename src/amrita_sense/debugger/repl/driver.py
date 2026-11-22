"""Input loop for the SenseDBG rescue REPL.

The loop runs on a worker thread while the interpreter's event loop keeps
running, otherwise a single ``step`` command deadlocks the process (the sync
debugger wrappers join a future that only the blocked loop can complete).

Three details matter here:

* reading goes through :func:`input`, not ``sys.stdin.readline()``, so
  :mod:`readline` supplies cursor movement, history and completion;
* the reader thread is a daemon created by hand rather than an executor thread,
  so cancelling ``run()`` cannot keep interpreter shutdown waiting on a blocked
  ``read()``;
* a watchdog on the *first keystroke* bounds an unattended TTY.  ``input()``
  itself cannot time out, but ``select`` can wait for the first byte before
  handing the line to readline.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
import signal
import sys
import threading
from typing import TYPE_CHECKING, Any

from amrita_sense.debugger.repl.commands import REGISTRY, dispatch
from amrita_sense.debugger.repl.lexer import lex
from amrita_sense.debugger.repl.theme import (
    DIM,
    ERROR,
    PROMPT,
    Theme,
    color_enabled,
    sanitize,
)

try:  # pragma: no cover - platform dependent
    import readline
except ImportError:  # pragma: no cover - Windows without pyreadline
    readline = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from amrita_sense.debugger.repl.session import RescueSession

#: Seconds to wait for the first keystroke before re-raising the panic.
#: ``0`` disables the watchdog.
_TIMEOUT_ENV = "SDB_REPL_TIMEOUT"
_DEFAULT_TIMEOUT = 300.0

#: Names offered by tab completion, besides node tags.
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

_tag_cache: tuple[int, list[str]] | None = None
_readline_state: dict[str, Any] = {}


def _history_path() -> pathlib.Path:
    """Where the REPL keeps history; overridable for tests and sandboxes."""
    override = os.environ.get("SDB_HISTORY")
    return pathlib.Path(override) if override else pathlib.Path.home() / ".sdb_history"


def _repl_timeout() -> float:
    raw = os.environ.get(_TIMEOUT_ENV)
    if raw is None:
        return _DEFAULT_TIMEOUT
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_TIMEOUT


def _output(session: RescueSession):
    return session.echo if session.echo is not None else sys.stdout


def _prompt(session: RescueSession) -> str:
    """Uncoloured prompt text; colouring (and readline escaping) happens later."""
    inter = session.inter
    pc = session.read_pseudo("pc")
    if pc is None:
        return "(sdb) <end> "
    try:
        node = inter.get_graph().calc.find_addr_safe(list(pc))
        tag = getattr(node, "tag", None) or "?"
    except Exception:
        tag = "?"
    # A node tag is workflow-controlled text; it must not carry escape codes
    # into the operator's prompt.
    tag = sanitize(str(tag).splitlines()[0])[:24]
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
        session.write(
            session.theme.paint(sanitize(f"panic: {type(exc).__name__}: {exc}"), ERROR)
        )
    session.write(
        f"pc={session.theme.paint(str(session.read_pseudo('pc')), PROMPT)}"
        f"  flags={session.read_pseudo('flags')}"
    )
    session.write(
        "`help` lists commands · `q` re-raises · `k` abandons · `py` = Python"
    )
    session.write(rule)


def _node_tags() -> list[str]:
    """Node tags of the thread's active interpreter, cached per session."""
    global _tag_cache
    from amrita_sense.debugger.rescue import NoActiveRescue, get_rescue_session

    try:
        session = get_rescue_session()
    except NoActiveRescue:
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
    """Take over readline, remembering what the host process had configured.

    GNU readline and libedit accept different binding syntaxes, and
    python-build-standalone links libedit, so only the syntax matching the
    active backend is used — sending libedit syntax to GNU readline disturbs
    its default ``complete`` binding.
    """
    if readline is None:  # pragma: no cover - Windows
        return
    _readline_state["completer"] = readline.get_completer()
    _readline_state["delims"] = readline.get_completer_delims()
    _readline_state["history_length"] = readline.get_history_length()
    with contextlib.suppress(OSError):
        readline.read_history_file(_history_path())
    with contextlib.suppress(Exception):
        readline.set_history_length(500)
        readline.set_completer(_complete)
        readline.set_completer_delims(" \t\n")
        backend = readline.__doc__ or ""
        binding = "bind ^I rl_complete" if "libedit" in backend else "tab: complete"
        readline.parse_and_bind(binding)


def _teardown_readline() -> None:
    if readline is None:  # pragma: no cover - Windows
        return
    with contextlib.suppress(OSError):
        history = _history_path()
        history.parent.mkdir(parents=True, exist_ok=True)
        readline.write_history_file(history)
    with contextlib.suppress(Exception):
        if "history_length" in _readline_state:
            readline.set_history_length(_readline_state["history_length"])
        if "completer" in _readline_state:
            readline.set_completer(_readline_state["completer"])
        if "delims" in _readline_state:
            readline.set_completer_delims(_readline_state["delims"])
    _readline_state.clear()


def _read_line(session: RescueSession, prompt: str) -> str | None:
    """Read one line with line editing; ``None`` means "leave the rescue"."""
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
    from amrita_sense.debugger.rescue import bind_thread_session, unbind_thread_session

    bind_thread_session(session)
    try:
        _welcome(session)
        while True:
            line = _read_line(session, _prompt(session))
            if line is None:
                return session.exit_reason or "quit"
            if session.cancelled:
                return "timeout"
            tokens = lex(line)
            reason = dispatch(session, tokens)
            if reason:
                return reason
    finally:
        unbind_thread_session()


async def _run_worker(session: RescueSession) -> str:
    """Run the reader on a daemon thread and await its result.

    A daemon thread (rather than ``asyncio.to_thread``) keeps interpreter
    shutdown from waiting on a ``read()`` that cancellation cannot interrupt.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()

    def _resolve(result: str | None, error: BaseException | None) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result or "quit")

    def runner() -> None:
        try:
            result = _thread_main(session)
        except BaseException as exc:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(_resolve, None, exc)
        else:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(_resolve, result, None)

    threading.Thread(target=runner, name="sdb-repl", daemon=True).start()
    try:
        return await future
    except asyncio.CancelledError:
        # The reader may still be blocked in read(); it is a daemon, and the
        # session is marked so it exits at the next line instead of continuing.
        session.cancelled = True
        raise


async def run_repl(session: RescueSession, *, capture_sigint: bool = True) -> str:
    """Drive a rescue session until it ends.

    Args:
        session: The session to run.
        capture_sigint: Install a soft-interrupt handler for the duration.
            Disable it when the caller already owns SIGINT handling.

    Returns:
        ``"quit"``, ``"kill"``, ``"suppress"`` or ``"timeout"``.
    """
    loop = asyncio.get_running_loop()
    session.loop = loop
    enabled = color_enabled(_output(session))
    session.color = enabled
    session.theme = Theme(enabled)
    previous = None
    if capture_sigint:
        with contextlib.suppress(ValueError, OSError):
            previous = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, session.on_sigint)
    _setup_readline()
    timeout = _repl_timeout()
    try:
        if timeout > 0:
            try:
                reason = await asyncio.wait_for(_run_worker(session), timeout)
            except asyncio.TimeoutError:
                session.cancelled = True
                session.warn(
                    f"[rescue timeout after {timeout:.0f}s] no input; re-raising the panic"
                )
                session.exit_reason = "timeout"
                reason = "timeout"
        else:
            reason = await _run_worker(session)
    finally:
        _teardown_readline()
        global _tag_cache
        _tag_cache = None
        if previous is not None:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(signal.SIGINT, previous)
        session.loop = None
    return reason or "quit"


__all__ = ["run_repl"]
