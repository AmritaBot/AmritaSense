"""End-to-end tests for the rescue REPL over a real PTY.

These are separated from the unit suite because they need a pseudo-terminal and
a child process.  Everything else in ``test_rescue_repl.py`` stays headless.
"""

from __future__ import annotations

import contextlib
import os
import pty
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="pty is POSIX-only")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Prompt matching has to ignore colour escapes and readline's ignore markers.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _visible(text: str) -> str:
    return _ANSI.sub("", text).replace("\x01", "").replace("\x02", "")


DEMO = r"""
import asyncio
from amrita_sense import Node, WorkflowInterpreter
from amrita_sense._unsafe import __flags__

__flags__.RESCUE_ON_PANIC = True


@Node(tag="start")
def start() -> str:
    print("start ran")
    return "ok"


@Node(tag="crash")
def crash() -> None:
    raise RuntimeError("boom-e2e")


@Node(tag="after")
def after() -> None:
    print("after ran")


inter = WorkflowInterpreter((start >> crash >> after).render())
asyncio.run(inter.run())
"""


def _drive(
    commands: list[str],
    timeout: float = 25.0,
    extra_env: dict[str, str] | None = None,
) -> tuple[str, int]:
    """Run the demo under a PTY, sending *commands* as prompts appear."""
    try:
        master, slave = pty.openpty()
    except OSError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"pty unavailable: {exc}")

    process = subprocess.Popen(
        [sys.executable, "-u", "-c", DEMO],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        close_fds=True,
        cwd=PROJECT_ROOT,
        env={"SDB_REPL_FORCE": "1", **os.environ, **(extra_env or {})},
    )
    os.close(slave)

    transcript = ""
    pending = ""
    index = 0
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(master, 4096).decode("utf-8", "replace")
                except OSError:  # pragma: no cover - child closed the pty
                    break
                if not chunk:
                    break
                transcript += chunk
                pending += chunk
            while index < len(commands) and _visible(pending).rstrip().endswith(">"):
                os.write(master, (commands[index] + "\n").encode())
                index += 1
                pending = ""
            if process.poll() is not None and index >= len(commands):
                break
        process.wait(timeout=10)
    finally:
        if process.poll() is None:  # pragma: no cover - hung child
            process.kill()
            process.wait()
        with contextlib.suppress(OSError):
            os.close(master)
    return transcript, process.returncode


def test_rescue_repl_stops_at_the_panic_and_reraises(tmp_path) -> None:
    transcript, code = _drive(
        ["i r", "p $pc", "x 2", "q"],
        extra_env={"SDB_HISTORY": str(tmp_path / "history")},
    )

    assert "SenseDBG rescue" in transcript
    assert "panic: RuntimeError: boom-e2e" in transcript
    assert "(sdb) [1] crash>" in transcript
    assert "leaving rescue" in transcript
    # The original failure survives the rescue unchanged.
    assert code == 1
    assert "RuntimeError: boom-e2e" in transcript
    assert "start ran" in transcript
    assert "after ran" not in transcript


def test_rescue_repl_recovers_by_skipping_the_failed_node(tmp_path) -> None:
    transcript, code = _drive(
        ["skip", "py await step_async(inter)", "q"],
        extra_env={"SDB_HISTORY": str(tmp_path / "history")},
    )

    assert "pc -> [2]" in transcript
    # `await` inside `py` ran the remaining node on the interpreter's loop.
    assert "after ran" in transcript
    assert code == 1
    assert "RuntimeError: boom-e2e" in transcript


def test_arrow_keys_edit_the_current_line(tmp_path) -> None:
    """Left-arrow must move the cursor, not emit a raw ESC sequence.

    Type ``i``, move one character left, insert ``s``: the submitted line is
    ``si``, so the REPL reports an unknown command named exactly ``si``.  With
    plain ``readline()`` the bytes would arrive as ``i\\x1b[Ds`` instead.
    """
    transcript, code = _drive(
        ["i\x1b[Ds", "q"],
        extra_env={"SDB_HISTORY": str(tmp_path / "history")},
    )
    assert "unknown command: si" in transcript
    assert code == 1


def test_tab_completion_expands_a_command(tmp_path) -> None:
    """Typing `he<TAB>` must complete to `help`, not submit `he`."""
    transcript, _code = _drive(
        ["he\t\n", "q"],
        extra_env={"SDB_HISTORY": str(tmp_path / "history")},
    )
    assert "unknown command: he" not in transcript
    assert "step" in transcript  # the help listing rendered


def test_prompt_and_panic_are_coloured(tmp_path) -> None:
    """ANSI must reach the terminal, but never the cursor arithmetic."""
    transcript, _ = _drive(
        ["q"],
        extra_env={
            "SDB_HISTORY": str(tmp_path / "history"),
            "TERM": "xterm-256color",
            "NO_COLOR": "",
        },
    )
    assert "\x1b[36m" in transcript  # cyan prompt
    assert "\x1b[31m" in transcript  # red panic line
    assert "(sdb) [1] crash>" in transcript


def test_up_arrow_recalls_the_previous_command(tmp_path) -> None:
    """Up must refill the line, so appending a digit edits the old command."""
    transcript, _ = _drive(
        ["p 12345", "\x1b[A0\n", "q"],
        extra_env={"SDB_HISTORY": str(tmp_path / "history")},
    )
    assert "123450" in transcript
    assert "unknown command: 0" not in transcript


def test_tab_completes_node_tags(tmp_path) -> None:
    """`b tag:cr<TAB>` must complete a real node tag from the graph."""
    transcript, _ = _drive(
        ["b tag:cr\t\n", "q"],
        extra_env={"SDB_HISTORY": str(tmp_path / "history")},
    )
    assert "break at tag 'crash'" in transcript
    assert "unknown command" not in transcript


def test_help_rows_are_not_dimmed(tmp_path) -> None:
    """Help text must stay readable: names accent-coloured, descriptions plain.

    Dim (bright black) is nearly invisible on dark terminals, so it is reserved
    for the banner rules only.
    """
    transcript, _ = _drive(
        ["help", "q"],
        extra_env={
            "SDB_HISTORY": str(tmp_path / "history"),
            "TERM": "xterm-256color",
            "NO_COLOR": "",
        },
    )
    rows = [line for line in transcript.splitlines() if "s/step" in line]
    assert rows, "help listing missing"
    row = rows[-1]
    assert "\x1b[36m" in row  # command name accent
    assert "\x1b[90m" not in row  # description must not be dimmed


def test_suppress_returns_normally(tmp_path) -> None:
    """`suppress` swallows the panic: the process exits cleanly, nothing re-raised."""
    transcript, code = _drive(
        ["suppress"],
        extra_env={"SDB_HISTORY": str(tmp_path / "history")},
    )
    assert "suppressing the panic" in transcript
    assert "panic re-raised" not in transcript
    assert code == 0


def test_suppress_continue_runs_the_rest_then_returns(tmp_path) -> None:
    transcript, code = _drive(
        ["suppress continue"],
        extra_env={"SDB_HISTORY": str(tmp_path / "history")},
    )
    assert "after ran" in transcript
    assert "ran to completion" in transcript
    assert code == 0


def _drain_until_exit(timeout: float = 20.0) -> tuple[str, int]:
    """Run the demo under a PTY without ever typing, and wait for it to leave."""
    try:
        master, slave = pty.openpty()
    except OSError as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"pty unavailable: {exc}")

    process = subprocess.Popen(
        [sys.executable, "-u", "-c", DEMO],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        close_fds=True,
        cwd=PROJECT_ROOT,
        env={
            "SDB_REPL_FORCE": "1",
            "SDB_REPL_TIMEOUT": "0.5",
            "SDB_HISTORY": "/tmp/sdb_pty_timeout_history",
            **os.environ,
        },
    )
    os.close(slave)
    transcript = ""
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(master, 4096).decode("utf-8", "replace")
                except OSError:
                    break
                if not chunk:
                    break
                transcript += chunk
            if process.poll() is not None and not ready:
                break
        process.wait(timeout=10)
    finally:
        if process.poll() is None:  # pragma: no cover - hung child
            process.kill()
            process.wait()
        with contextlib.suppress(OSError):
            os.close(master)
    return transcript, process.returncode


def test_unattended_tty_times_out() -> None:
    """Nobody types: the watchdog returns control instead of hanging run()."""
    transcript, code = _drain_until_exit()
    assert "rescue timeout" in _visible(transcript)
    assert code == 1
