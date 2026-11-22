"""Unit tests for the SenseDBG rescue REPL (``RESCUE_ON_PANIC``).

The suite is split by layer: lexing, session state, command dispatch, the
embedded Python console, the panic report, and the driver loop.  The PTY
end-to-end path lives in ``test_rescue_pty.py`` so this file stays deterministic
on machines without a terminal.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import sys

import pytest

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense._unsafe import __flags__
from amrita_sense.debugger import code_disp, rescue
from amrita_sense.debugger.repl.commands import dispatch
from amrita_sense.debugger.repl.console import RescueConsole
from amrita_sense.debugger.repl.driver import run_repl
from amrita_sense.debugger.repl.lexer import fold, lex
from amrita_sense.debugger.repl.session import (
    NoActiveRescue,
    RescueSession,
    SessionError,
    Snapshot,
)


@Node(tag="alpha")
def alpha() -> int:
    return 1


@Node(tag="beta")
def beta() -> int:
    return 2


@Node(tag="gamma")
def gamma() -> int:
    return 3


@Node(tag="boom")
def boom() -> None:
    raise RuntimeError("planned")


def make_inter(*, crashing: bool = False) -> WorkflowInterpreter:
    if crashing:
        return WorkflowInterpreter((alpha >> boom >> gamma).render())
    return WorkflowInterpreter((alpha >> beta >> gamma).render())


def make_session(inter: WorkflowInterpreter | None = None) -> RescueSession:
    return RescueSession(inter or make_inter(), echo=io.StringIO())


def output(session: RescueSession) -> str:
    assert isinstance(session.echo, io.StringIO)
    return session.echo.getvalue()


def test_lex_blank_and_comment() -> None:
    assert lex("") == []
    assert lex("   \t ") == []
    assert lex("# only a comment") == []
    assert lex("s 2 # trailing") == ["s", "2"]


def test_lex_keeps_quotes_for_python() -> None:
    # `py` must receive the literal back, quotes included.
    assert lex("py print('a b')") == ["py", "print('a b')"]
    assert lex('b tag:"my node"') == ["b", 'tag:"my node"']


def test_lex_folds_full_width_punctuation() -> None:
    assert lex("set $pc ＝ ［1, 0］") == ["set", "$pc", "=", "[1,", "0]"]
    assert fold("s 2\r\n") == "s 2"


def test_lex_unterminated_quote_takes_rest() -> None:
    assert lex('b tag:"unclosed') == ["b", 'tag:"unclosed']


def test_pseudo_registers_round_trip() -> None:
    session = make_session()
    assert session.read_pseudo("$pc") == [0]
    assert session.read_pseudo("rp") is None
    assert session.read_pseudo("flags") == 0
    assert session.read_pseudo("exc") is None

    session.write_pseudo("$pc", [2])
    assert session.read_pseudo("pc") == [2]

    session.write_pseudo("$flags", 4)
    assert session.read_pseudo("flags") == 4

    boom_exc = RuntimeError("x")
    session.write_pseudo("$exc", boom_exc)
    assert session.inter.get_exception() is boom_exc
    session.write_pseudo("$exc", None)
    assert session.inter.get_exception() is None


def test_pseudo_register_rejects_junk() -> None:
    session = make_session()
    with pytest.raises(SessionError):
        session.read_pseudo("$nope")
    with pytest.raises(SessionError):
        session.write_pseudo("$pc", [99, 99])
    with pytest.raises(SessionError):
        session.write_pseudo("$pc", "not-an-address")
    with pytest.raises(SessionError):
        session.write_pseudo("$flags", "blue")
    with pytest.raises(SessionError):
        session.write_pseudo("$exc", 5)
    with pytest.raises(SessionError):
        session.write_pseudo("$rp", [0])


def test_pointer_vector_is_accepted_as_address() -> None:
    from amrita_sense.types import PointerVector

    session = make_session()
    session.write_pseudo("$pc", PointerVector([1]))
    assert session.read_pseudo("pc") == [1]


def test_snapshot_restores_return_stack_and_flags() -> None:
    from amrita_sense.runtime.types import Flags
    from amrita_sense.types import PointerVector

    inter = make_inter()
    inter._ret_addr_stack.stack.append(PointerVector([0]))
    inter._flags = Flags(4)
    snapshot = Snapshot.capture(inter)

    inter._ret_addr_stack.stack.clear()
    inter._flags = Flags(0)
    inter._pointer = PointerVector([2])

    snapshot.restore(inter)
    assert [item.base_addr for item in inter._ret_addr_stack.stack] == [[0]]
    assert int(inter.flags) == 4
    assert inter._pointer.base_addr == [0]


def test_driver_token_is_exclusive() -> None:
    session = make_session()
    session.claim_driver()
    try:
        with pytest.raises(SessionError):
            session.claim_driver()
    finally:
        session.release_driver()
    session.claim_driver()  # released again
    session.release_driver()


def test_render_block_is_colour_free_and_restores_setting() -> None:
    session = make_session()
    previous = code_disp.COLOR
    code_disp.COLOR = True
    try:
        text = session.render_block(lambda: print("plain"))
        assert text.strip() == "plain"
        assert code_disp.COLOR is True
    finally:
        code_disp.COLOR = previous


def test_render_block_survives_a_broken_view() -> None:
    session = make_session()

    def explode() -> None:
        raise ValueError("view bug")

    text = session.render_block(explode)
    assert "view failed" in text


def test_step_advances_one_node() -> None:
    session = make_session()
    assert dispatch(session, lex("s")) is None
    assert session.read_pseudo("pc") == [1]
    dispatch(session, lex("s"))
    assert session.read_pseudo("pc") == [2]
    dispatch(session, lex("s"))
    assert session.read_pseudo("pc") is None


def test_step_accepts_a_count() -> None:
    session = make_session()
    dispatch(session, lex("s 2"))
    assert session.read_pseudo("pc") == [2]


def test_step_rejects_bad_counts() -> None:
    session = make_session()
    dispatch(session, lex("s nope"))
    assert "expected an integer" in output(session)
    dispatch(session, lex("s 0"))
    assert "n must be >= 1" in output(session)
    assert session.read_pseudo("pc") == [0]


def test_next_and_finish_run() -> None:
    session = make_session()
    dispatch(session, lex("n"))
    assert session.read_pseudo("pc") == [1]
    dispatch(session, lex("fin"))
    assert session.read_pseudo("pc") is None


def test_cont_runs_to_the_end() -> None:
    session = make_session()
    dispatch(session, lex("c"))
    assert session.read_pseudo("pc") is None


def test_blank_line_repeats_previous_command() -> None:
    session = make_session()
    dispatch(session, lex("s"))
    dispatch(session, lex(""))
    assert session.read_pseudo("pc") == [2]


def test_blank_line_without_history_is_harmless() -> None:
    session = make_session()
    dispatch(session, lex(""))
    assert "no previous command" in output(session)


def test_skip_requires_a_pending_panic() -> None:
    session = make_session()
    dispatch(session, lex("skip"))
    assert "no panic is pending" in output(session)


def test_skip_moves_past_the_failed_node() -> None:
    session = make_session(make_inter(crashing=True))
    session.write_pseudo("$exc", RuntimeError("planned"))
    dispatch(session, lex("skip"))
    assert session.read_pseudo("pc") == [1]


def test_step_warns_about_pending_panic() -> None:
    session = make_session()
    session.write_pseudo("$exc", RuntimeError("planned"))
    dispatch(session, lex("s"))
    assert "panic pending" in output(session)
    assert "will re-run that node" in output(session)


def test_until_stops_after_the_current_address() -> None:
    session = make_session()
    dispatch(session, lex("u"))
    assert session.read_pseudo("pc") == [1]


def test_until_accepts_an_explicit_address() -> None:
    session = make_session()
    dispatch(session, lex("u [2]"))
    assert session.read_pseudo("pc") == [2]


def test_until_reports_the_end_of_the_workflow() -> None:
    session = make_session()
    session.write_pseudo("$pc", [2])
    dispatch(session, lex("u [9]"))
    assert "workflow ended" in output(session)


def test_jump_validates_the_target() -> None:
    session = make_session()
    dispatch(session, lex("j [2]"))
    assert session.read_pseudo("pc") == [2]
    dispatch(session, lex("j [42]"))
    assert "does not exist" in output(session)
    assert session.read_pseudo("pc") == [2]


def test_jump_without_argument_errors() -> None:
    session = make_session()
    dispatch(session, lex("j"))
    assert "usage" in output(session)


def test_print_evaluates_restricted_expressions() -> None:
    session = make_session()
    dispatch(session, lex("p $pc"))
    assert "[0]" in output(session)
    dispatch(session, lex("p len(inter._pointer.base_addr)"))
    assert "1" in output(session)
    dispatch(session, lex("p 1 / 0"))
    assert "ZeroDivisionError" in output(session)


def test_set_writes_registers() -> None:
    session = make_session()
    dispatch(session, lex("set $pc = [1]"))
    assert session.read_pseudo("pc") == [1]
    dispatch(session, lex("set $flags = 4"))
    assert session.read_pseudo("flags") == 4


def test_set_requires_an_assignment() -> None:
    session = make_session()
    dispatch(session, lex("set $pc"))
    assert "usage" in output(session)


def test_info_topics() -> None:
    session = make_session()
    for topic in ("r", "b", "f", "l", "w"):
        dispatch(session, lex(f"i {topic}"))
    dispatch(session, lex("i nope"))
    assert "unknown info topic" in output(session)


def test_examine_renders_the_graph() -> None:
    session = make_session()
    dispatch(session, lex("x 2"))
    text = output(session)
    assert "segment [root]" in text
    assert "alpha" in text


def test_backtrace_prints_a_chain() -> None:
    session = make_session()
    dispatch(session, lex("bt"))
    assert "Interpreter" in output(session)


def test_breakpoints_set_list_and_clear() -> None:
    session = make_session()
    dispatch(session, lex("b tag:beta"))
    dispatch(session, lex("bl"))
    assert "beta" in output(session)

    dispatch(session, lex("b *[1]"))
    dispatch(session, lex("d *[1]"))
    dispatch(session, lex("d tag:beta"))
    dispatch(session, lex("bl"))
    assert "(no breakpoints)" in output(session)


def test_delete_all_clears_everything() -> None:
    session = make_session()
    dispatch(session, lex("b tag:alpha"))
    dispatch(session, lex("b tag:beta"))
    dispatch(session, lex("d all"))
    dispatch(session, lex("bl"))
    assert "(no breakpoints)" in output(session)


def test_break_without_argument_errors() -> None:
    session = make_session()
    dispatch(session, lex("b"))
    assert "usage" in output(session)


def test_undo_restores_the_opening_snapshot() -> None:
    session = make_session()
    dispatch(session, lex("s"))
    dispatch(session, lex("s"))
    assert session.read_pseudo("pc") == [2]
    dispatch(session, lex("undo"))
    assert session.read_pseudo("pc") == [0]


def test_reset_clears_the_interpreter() -> None:
    session = make_session()
    dispatch(session, lex("s"))
    dispatch(session, lex("rs"))
    assert session.read_pseudo("pc") is None
    assert "interpreter reset" in output(session)


def test_quit_and_kill_report_their_reason() -> None:
    session = make_session()
    assert dispatch(session, lex("q")) == "quit"
    assert dispatch(session, lex("q")) == "quit"
    assert dispatch(session, lex("k")) == "kill"


def test_help_lists_commands_and_details() -> None:
    session = make_session()
    dispatch(session, lex("help"))
    assert "step" in output(session)
    dispatch(session, lex("help s"))
    assert "usage" in output(session)
    dispatch(session, lex("help nope"))
    assert "unknown command" in output(session)


def test_unknown_command_is_reported() -> None:
    session = make_session()
    assert dispatch(session, lex("nope")) is None
    assert "unknown command" in output(session)


def test_dispatch_survives_a_handler_exception() -> None:
    session = make_session()

    class Hostile:
        def __repr__(self) -> str:
            raise ValueError("repr bomb")

    session.write_pseudo("$exc", RuntimeError("fine"))
    dispatch(session, lex("p inter._pointer"))
    assert output(session)


def test_driving_while_another_command_runs_is_refused() -> None:
    session = make_session()
    session.claim_driver()
    try:
        dispatch(session, lex("s"))
    finally:
        session.release_driver()
    assert "still running" in output(session)
    assert session.read_pseudo("pc") == [0]


def test_console_captures_edits_to_registers() -> None:
    session = make_session()
    console = RescueConsole(session)
    console.push("pc = [1]")
    applied = session.sync_from_namespace(console.locals)
    assert "pc" in applied
    assert session.read_pseudo("pc") == [1]


def test_py_single_line_applies_edits() -> None:
    session = make_session()
    dispatch(session, lex("py pc = [2]"))
    assert session.read_pseudo("pc") == [2]
    assert "applied" in output(session)


def test_py_keeps_its_own_namespace_clean() -> None:
    session = make_session()
    dispatch(session, lex("py scratch = 41"))
    dispatch(session, lex("py print(scratch + 1)"))
    assert "42" in output(session)
    assert "scratch" in session.py_locals


def test_py_exception_is_contained() -> None:
    session = make_session()
    dispatch(session, lex("py 1 / 0"))
    assert "ZeroDivisionError" in output(session)
    assert session.inter.get_exception() is None


def test_py_system_exit_is_not_fatal() -> None:
    session = make_session()
    dispatch(session, lex("py raise SystemExit(3)"))
    assert "exit ignored" in output(session)


def test_py_interactive_console_exits_back_to_sdb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = make_session()
    monkeypatch.setattr(sys, "stdin", io.StringIO("kept = 7\nexit()\n"))
    dispatch(session, lex("py"))
    assert "returned to (sdb)" in output(session)
    assert session.py_locals.get("kept") == 7
    assert not hasattr(sys, "ps1") or isinstance(sys.ps1, str)


def test_console_supports_top_level_await_in_a_loop() -> None:
    """`await` inside `py` must run on the interpreter's loop, not a new one."""

    async def scenario() -> None:
        session = make_session()
        session.loop = asyncio.get_running_loop()
        console = RescueConsole(session)

        def worker() -> None:
            console.push("await asyncio.sleep(0)")
            console.push("marker = 'awaited'")

        await asyncio.to_thread(worker)
        assert console.locals.get("marker") == "awaited"

    asyncio.run(scenario())


def test_report_captures_the_scene() -> None:
    inter = make_inter(crashing=True)
    exc = RuntimeError("planned")
    report = rescue.build_report(inter, exc)

    assert report.interpreter == str(inter.id)
    assert report.panic_type == "RuntimeError"
    assert report.pointer == [0]
    assert "alpha" in report.disassembly
    assert "Sense Runtime Traceback" in report.traceback
    assert "Failed at node" in report.traceback
    assert "SenseDBG panic report" in report.to_text()
    assert report.to_dict()["panic_type"] == "RuntimeError"


def test_attach_report_keeps_the_exception_type() -> None:
    exc = RuntimeError("planned")
    report = rescue.PanicReport(
        interpreter="i",
        panic_type="RuntimeError",
        panic_message="planned",
        pointer=[0],
        flags=0,
    )
    rescue.attach_report(exc, report)

    assert type(exc) is RuntimeError
    assert getattr(exc, "__sdb_report__", None) is report
    if hasattr(exc, "add_note"):
        notes = getattr(exc, "__notes__", [])
        assert any("SenseDBG" in note for note in notes)


def test_rescue_without_tty_returns_report() -> None:
    inter = make_inter(crashing=True)
    exc = RuntimeError("planned")
    assert (
        asyncio.run(rescue.rescue_on_panic(inter, exc, interactive=False)) == "report"
    )
    assert hasattr(exc, "__sdb_report__")


def test_rescue_with_repl_quit(monkeypatch: pytest.MonkeyPatch) -> None:
    inter = make_inter(crashing=True)
    exc = RuntimeError("planned")
    monkeypatch.setattr(rescue, "run_repl", _fake_repl("quit"))
    assert asyncio.run(rescue.rescue_on_panic(inter, exc, interactive=True)) == "quit"
    with pytest.raises(NoActiveRescue):
        rescue.get_rescue_intp()


def test_rescue_kill_closes_the_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    inter = make_inter(crashing=True)
    exc = RuntimeError("planned")
    calls: list[bool] = []

    async def fake_close() -> None:
        calls.append(True)

    monkeypatch.setattr(rescue, "run_repl", _fake_repl("kill"))
    monkeypatch.setattr(type(inter), "_close_workflow_scope", lambda self: fake_close())

    assert asyncio.run(rescue.rescue_on_panic(inter, exc, interactive=True)) == "kill"
    assert calls == [True]


def test_failed_rescue_still_pops_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inter = make_inter(crashing=True)
    exc = RuntimeError("planned")

    async def exploding_repl(session: RescueSession) -> str:
        raise RuntimeError("repl bug")

    monkeypatch.setattr(rescue, "run_repl", exploding_repl)
    with pytest.raises(RuntimeError, match="repl bug"):
        asyncio.run(rescue.rescue_on_panic(inter, exc, interactive=True))
    with pytest.raises(NoActiveRescue):
        rescue.get_rescue_session()


def _fake_repl(reason: str):
    async def repl(session: RescueSession) -> str:
        assert rescue.get_rescue_intp() is session.inter
        return reason

    return repl


def test_tty_probe_honours_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDB_REPL_FORCE", "1")
    assert rescue.stdin_is_tty() is True
    monkeypatch.setenv("SDB_REPL_FORCE", "0")
    monkeypatch.setenv("SDB_REPL_DISABLE", "1")
    assert rescue.stdin_is_tty() is False
    monkeypatch.delenv("SDB_REPL_DISABLE")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert rescue.stdin_is_tty() is False


def test_tty_probe_rejects_dumb_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return 0

    monkeypatch.delenv("SDB_REPL_FORCE", raising=False)
    monkeypatch.delenv("SDB_REPL_DISABLE", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setattr(sys, "stdin", FakeTTY(""))
    monkeypatch.setattr(rescue.os, "isatty", lambda fd: True)
    assert rescue.stdin_is_tty() is False


def _run_driver(script: str, monkeypatch: pytest.MonkeyPatch) -> RescueSession:
    session = make_session()
    monkeypatch.setattr(sys, "stdin", io.StringIO(script))
    asyncio.run(run_repl(session, capture_sigint=False))
    return session


def test_driver_runs_a_script_and_quits(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _run_driver("s\ns\nq\n", monkeypatch)
    text = output(session)
    assert "SenseDBG rescue" in text
    assert "(sdb)" in text
    assert "leaving rescue" in text
    assert session.read_pseudo("pc") == [2]


def test_driver_treats_eof_as_quit(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _run_driver("", monkeypatch)
    assert "SenseDBG rescue" in output(session)
    assert session.exit_reason is None  # EOF does not go through `q`


def test_driver_reports_a_soft_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Ctrl-C landing while the line is being typed is reported, not carried
    into the next command."""

    session = make_session()

    class InterruptingInput(io.StringIO):
        def readline(self, size: int = -1) -> str:
            session.on_sigint(2, None)
            return super().readline(size)

    monkeypatch.setattr(sys, "stdin", InterruptingInput("q\n"))
    asyncio.run(run_repl(session, capture_sigint=False))
    assert "[interrupted]" in output(session)
    assert session.interrupted.is_set() is False


def test_driver_shows_the_pending_panic_in_the_banner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = make_session(make_inter(crashing=True))
    session.write_pseudo("$exc", RuntimeError("planned"))
    monkeypatch.setattr(sys, "stdin", io.StringIO("q\n"))
    asyncio.run(run_repl(session, capture_sigint=False))
    assert "panic: RuntimeError: planned" in output(session)


def test_prompt_names_the_current_node(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _run_driver("s\nq\n", monkeypatch)
    assert "[1] beta>" in output(session)


def test_run_reraises_original_panic_with_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run()` opens the REPL, then re-raises the very same exception."""
    inter = make_inter(crashing=True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    async def scenario() -> None:
        monkeypatch.setattr(rescue, "stdin_is_tty", lambda: True)
        with pytest.raises(RuntimeError, match="planned") as info:
            await inter.run()
        assert type(info.value) is RuntimeError

    previous = __flags__.RESCUE_ON_PANIC
    __flags__.RESCUE_ON_PANIC = True
    try:
        asyncio.run(scenario())
    finally:
        __flags__.RESCUE_ON_PANIC = previous


def test_run_with_rescue_disabled_does_not_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inter = make_inter(crashing=True)
    monkeypatch.setattr(rescue, "stdin_is_tty", lambda: True)
    previous = __flags__.RESCUE_ON_PANIC
    __flags__.RESCUE_ON_PANIC = False
    try:

        async def scenario() -> None:
            with pytest.raises(RuntimeError, match="planned") as info:
                await inter.run()
            assert not hasattr(info.value, "__sdb_report__")

        asyncio.run(scenario())
    finally:
        __flags__.RESCUE_ON_PANIC = previous


def test_run_coroutine_cancels_on_soft_interrupt() -> None:
    """The Ctrl-C path: cancel the pending command instead of hanging on it.

    The test is synchronous on purpose — the project's pytest setup does not
    enable an async plugin, so it spins its own loop like the REPL does.
    """
    import threading

    session = make_session()
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    session.loop = loop
    started = threading.Event()
    result: list[str] = []

    async def slow() -> None:
        started.set()
        await asyncio.sleep(30)

    def worker() -> None:
        try:
            session.run_coroutine(slow())
        except KeyboardInterrupt:
            result.append("interrupted")
        else:
            result.append("finished")

    worker_thread = threading.Thread(target=worker, daemon=True)
    try:
        worker_thread.start()
        assert started.wait(5)
        session.on_sigint(2, None)
        worker_thread.join(5)
        assert result == ["interrupted"]
    finally:
        # Let the cancelled task finish before tearing the loop down.
        async def drain() -> None:
            await asyncio.sleep(0)

        with contextlib.suppress(Exception):
            asyncio.run_coroutine_threadsafe(drain(), loop).result(2)
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(2)
        loop.close()


def test_namespace_sync_rejects_an_unresolvable_pointer() -> None:
    session = make_session()
    namespace = session.py_namespace()
    namespace["pc"] = [99, 99]
    applied = session.sync_from_namespace(namespace)
    assert applied == []
    assert "does not exist" in output(session)
    assert session.read_pseudo("pc") == [0]


def test_rescue_flag_can_be_toggled_at_runtime() -> None:
    previous = __flags__.RESCUE_ON_PANIC
    try:
        __flags__.RESCUE_ON_PANIC = True
        assert __flags__.RESCUE_ON_PANIC is True
        __flags__.RESCUE_ON_PANIC = False
        assert __flags__.RESCUE_ON_PANIC is False
    finally:
        __flags__.RESCUE_ON_PANIC = previous


def test_repeat_echoes_the_command() -> None:
    session = make_session()
    dispatch(session, lex("s 1"))
    dispatch(session, lex(""))
    assert "repeat: s 1" in output(session)


def test_tty_probe_accepts_a_foreground_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return 0

    monkeypatch.delenv("SDB_REPL_FORCE", raising=False)
    monkeypatch.delenv("SDB_REPL_DISABLE", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(sys, "stdin", FakeTTY(""))
    monkeypatch.setattr(rescue.os, "isatty", lambda fd: True)
    monkeypatch.setattr(rescue.os, "tcgetpgrp", lambda fd: 4242)
    monkeypatch.setattr(rescue.os, "getpgrp", lambda: 4242)
    assert rescue.stdin_is_tty() is True


def test_delete_without_argument_lists_breakpoints() -> None:
    session = make_session()
    dispatch(session, lex("b tag:alpha"))
    dispatch(session, lex("d"))
    text = output(session)
    assert "alpha" in text
    assert "usage" in text


def test_print_without_argument_errors() -> None:
    session = make_session()
    dispatch(session, lex("p"))
    assert "usage" in output(session)


def test_tty_probe_rejects_a_background_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return 0

    monkeypatch.delenv("SDB_REPL_FORCE", raising=False)
    monkeypatch.delenv("SDB_REPL_DISABLE", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(sys, "stdin", FakeTTY(""))
    monkeypatch.setattr(rescue.os, "isatty", lambda fd: True)
    monkeypatch.setattr(rescue.os, "tcgetpgrp", lambda fd: 1)
    monkeypatch.setattr(rescue.os, "getpgrp", lambda: 2)
    assert rescue.stdin_is_tty() is False


def test_tty_probe_survives_isatty_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(fd: int) -> bool:
        raise OSError("not a tty")

    monkeypatch.delenv("SDB_REPL_FORCE", raising=False)
    monkeypatch.delenv("SDB_REPL_DISABLE", raising=False)

    class FakeTTY(io.StringIO):
        def fileno(self) -> int:
            return 0

    monkeypatch.setattr(sys, "stdin", FakeTTY(""))
    monkeypatch.setattr(rescue.os, "isatty", broken)
    assert rescue.stdin_is_tty() is False


def test_tty_probe_without_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDB_REPL_FORCE", raising=False)
    monkeypatch.delenv("SDB_REPL_DISABLE", raising=False)
    monkeypatch.setattr(sys, "stdin", None)
    assert rescue.stdin_is_tty() is False


def test_tty_probe_rejects_a_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePipe(io.StringIO):
        def fileno(self) -> int:
            return 0

    monkeypatch.delenv("SDB_REPL_FORCE", raising=False)
    monkeypatch.delenv("SDB_REPL_DISABLE", raising=False)
    monkeypatch.setattr(sys, "stdin", FakePipe(""))
    monkeypatch.setattr(rescue.os, "isatty", lambda fd: False)
    assert rescue.stdin_is_tty() is False


def test_render_block_keeps_colour_for_a_coloured_session() -> None:
    from amrita_sense.debugger.code_disp import dis
    from amrita_sense.debugger.repl.theme import Theme

    session = make_session()
    session.color = True
    session.theme = Theme(True)
    text = session.render_block(lambda: dis(session.inter, around=2))
    assert "\x1b[" in text  # disassembly kept its colours


def test_render_block_can_be_forced_colourless() -> None:
    from amrita_sense.debugger.code_disp import dis
    from amrita_sense.debugger.repl.theme import Theme

    session = make_session()
    session.color = True
    session.theme = Theme(True)
    text = session.render_block(lambda: dis(session.inter, around=2), color=False)
    assert "\x1b[" not in text


def test_theme_honours_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    from amrita_sense.debugger.repl.theme import Theme, color_enabled

    monkeypatch.setenv("NO_COLOR", "1")
    assert color_enabled(sys.stdout) is False
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert color_enabled(io.StringIO()) is True
    assert "\x1b[" in Theme(True).paint("x", "31")
    assert "\x1b[" not in Theme(False).paint("x", "31")


def test_suppress_command_ends_the_session() -> None:
    session = make_session()
    assert dispatch(session, lex("suppress")) == "suppress"
    text = output(session)
    assert "run() will return normally" in text
    assert "skip" in text  # points at the non-destructive alternative


def test_suppress_closes_the_scope_and_marks_the_panic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inter = make_inter(crashing=True)
    exc = RuntimeError("planned")
    closed: list[bool] = []

    async def fake_close() -> None:
        closed.append(True)

    monkeypatch.setattr(rescue, "run_repl", _fake_repl("suppress"))
    monkeypatch.setattr(type(inter), "_close_workflow_scope", lambda self: fake_close())

    reason = asyncio.run(rescue.rescue_on_panic(inter, exc, interactive=True))
    assert reason == "suppress"
    assert closed == [True]
    assert inter.panic_suppressed is True


def test_run_returns_normally_when_the_panic_is_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inter = make_inter(crashing=True)
    assert inter.panic_suppressed is False

    async def scenario() -> None:
        monkeypatch.setattr(rescue, "stdin_is_tty", lambda: True)
        monkeypatch.setattr(rescue, "run_repl", _fake_repl("suppress"))
        assert await inter.run() is None

    messages: list[str] = []
    from amrita_sense.runtime import workflow as workflow_module

    monkeypatch.setattr(
        workflow_module.logger, "warning", lambda msg, *a, **k: messages.append(msg)
    )

    previous = __flags__.RESCUE_ON_PANIC
    __flags__.RESCUE_ON_PANIC = True
    try:
        asyncio.run(scenario())
    finally:
        __flags__.RESCUE_ON_PANIC = previous

    # Silence is recorded, not forgotten.
    assert inter.panic_suppressed is True
    assert isinstance(inter.get_exception(), RuntimeError)
    assert any("suppressed by operator" in m for m in messages)
    assert all("%s" not in m for m in messages)  # loguru uses {}, not %-style


def test_reset_clears_the_suppressed_flag() -> None:
    inter = make_inter()
    inter._panic_suppressed = True
    inter.reset()
    assert inter.panic_suppressed is False


def test_suppress_continue_finishes_the_remaining_workflow() -> None:
    inter = make_inter(crashing=True)  # alpha -> boom -> gamma
    session = RescueSession(inter, echo=io.StringIO())
    session.write_pseudo("$pc", [1])
    session.write_pseudo("$exc", RuntimeError("planned"))

    assert dispatch(session, lex("suppress continue")) == "suppress"
    assert session.read_pseudo("pc") is None
    assert inter.panic_suppressed is True
    assert "ran to completion" in output(session)


def test_suppress_continue_does_not_swallow_a_second_panic() -> None:
    inter = make_inter(crashing=True)
    session = RescueSession(inter, echo=io.StringIO())
    session.write_pseudo("$pc", [0])
    session.write_pseudo("$exc", RuntimeError("planned"))

    # Advancing from [0] lands on the failing node again, which panics once more.
    assert dispatch(session, lex("suppress continue")) is None
    assert inter.panic_suppressed is False
    assert "another panic surfaced" in output(session)


def test_suppress_continue_stops_early_without_marking_done() -> None:
    """A breakpoint stops `cont_async` early; that is not a completed run."""
    inter = make_inter(crashing=True)
    session = RescueSession(inter, echo=io.StringIO())
    session.write_pseudo("$pc", [1])
    session.write_pseudo("$exc", RuntimeError("planned"))
    dispatch(session, lex("b tag:gamma"))

    assert dispatch(session, lex("suppress continue")) is None
    assert inter.panic_suppressed is False
    assert "stopped early" in output(session)


def test_suppress_rejects_unknown_mode() -> None:
    session = make_session()
    dispatch(session, lex("suppress contin"))
    text = output(session)
    assert "unknown suppress mode" in text


def test_suppress_keeps_the_original_panic_for_audit() -> None:
    inter = make_inter(crashing=True)
    original = RuntimeError("planned")
    inter._panic_exc = original
    session = RescueSession(inter, echo=io.StringIO())
    session.write_pseudo("$pc", [1])
    dispatch(session, lex("s"))  # recover + re-run, clears _panic_exc
    dispatch(session, lex("suppress"))
    assert inter.get_exception() is original
    assert inter.panic_suppressed is True


def test_new_run_clears_the_suppressed_status() -> None:
    inter = make_inter()
    inter._panic_suppressed = True
    asyncio.run(inter.run())
    assert inter.panic_suppressed is False


def test_skip_on_the_last_node_does_not_restart() -> None:
    inter = make_inter(crashing=True)
    session = RescueSession(inter, echo=io.StringIO())
    session.write_pseudo("$pc", [2])
    session.write_pseudo("$exc", RuntimeError("planned"))

    dispatch(session, lex("skip"))
    assert "last one" in output(session)
    dispatch(session, lex("s"))
    assert "already ended" in output(session)
    assert session.read_pseudo("pc") is None


def test_addresses_reject_fractional_negative_and_bool() -> None:
    session = make_session()
    for bad in ([1.5], [-1], [True], ["1"]):
        with pytest.raises(SessionError):
            session.write_pseudo("$pc", bad)
    assert session.read_pseudo("pc") == [0]

    dispatch(session, lex("j [1.5]"))
    assert "must be ints" in output(session)
    dispatch(session, lex("j [-1]"))
    assert "non-negative" in output(session)


def test_nested_rescue_refreshes_instead_of_stacking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inter = make_inter(crashing=True)
    exc = RuntimeError("planned")
    session = make_session(inter)
    rescue.push_session(session)
    try:
        reason = asyncio.run(rescue.rescue_on_panic(inter, exc, interactive=True))
    finally:
        rescue.pop_session(session)
    assert reason == "nested"
    assert hasattr(exc, "__sdb_report__")


def test_attach_report_keeps_the_innermost_scene() -> None:
    exc = RuntimeError("planned")
    inner = rescue.PanicReport(
        interpreter="child",
        panic_type="RuntimeError",
        panic_message="p",
        pointer=[9],
        flags=0,
    )
    outer = rescue.PanicReport(
        interpreter="parent",
        panic_type="RuntimeError",
        panic_message="p",
        pointer=[0],
        flags=0,
    )
    assert rescue.attach_report(exc, inner) is inner
    assert rescue.attach_report(exc, outer) is inner
    assert getattr(exc, "__sdb_report__", None) is inner


def test_disable_guard_beats_force(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDB_REPL_FORCE", "1")
    monkeypatch.setenv("SDB_REPL_DISABLE", "1")
    assert rescue.stdin_is_tty() is False


def test_windows_without_tcgetpgrp_is_treated_as_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return 0

    monkeypatch.delenv("SDB_REPL_FORCE", raising=False)
    monkeypatch.delenv("SDB_REPL_DISABLE", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(sys, "stdin", FakeTTY(""))
    monkeypatch.setattr(rescue.os, "isatty", lambda fd: True)
    monkeypatch.setattr(rescue.os, "tcgetpgrp", None, raising=False)
    assert rescue.stdin_is_tty() is True


def test_failed_foreground_probe_is_not_interactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return 0

    def broken(fd: int) -> int:
        raise OSError("not a controlling terminal")

    monkeypatch.delenv("SDB_REPL_FORCE", raising=False)
    monkeypatch.delenv("SDB_REPL_DISABLE", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(sys, "stdin", FakeTTY(""))
    monkeypatch.setattr(rescue.os, "isatty", lambda fd: True)
    monkeypatch.setattr(rescue.os, "tcgetpgrp", broken)
    assert rescue.stdin_is_tty() is False


def test_stale_pseudo_register_snapshot_is_not_written_back() -> None:
    """A step inside `py` moves the pointer; the old snapshot must not rewind it."""
    session = make_session()
    namespace = session.py_namespace()
    session.inter.advance_pointer()  # as if `await step_async` ran

    applied = session.sync_from_namespace(namespace)
    assert applied == []
    assert session.read_pseudo("pc") == [1]


def test_handler_errors_are_contained_by_dispatch() -> None:
    from amrita_sense.debugger.repl import commands

    @commands.command("boomcmd")
    def _boom(session: RescueSession, args: list[str]) -> None:
        raise RuntimeError("handler exploded")

    session = make_session()
    try:
        assert dispatch(session, lex("boomcmd")) is None
        assert "handler exploded" in output(session)
    finally:
        commands.REGISTRY.pop("boomcmd", None)


def test_prompt_strips_control_characters_from_tags() -> None:
    from amrita_sense.debugger.repl.driver import _prompt

    @Node(tag="evil\x1b[31mred\x07")
    def evil() -> None:
        return None

    inter = WorkflowInterpreter(evil.as_compose().render())
    session = RescueSession(inter, echo=io.StringIO())
    prompt = _prompt(session)
    assert "\x1b" not in prompt
    assert "\x07" not in prompt


def test_undo_is_not_a_business_rollback() -> None:
    """`undo` puts the debugger back; side effects of executed nodes stay."""
    seen: list[str] = []

    @Node(tag="effect")
    def effect() -> None:
        seen.append("ran")

    inter = WorkflowInterpreter(effect.as_compose().render())
    session = RescueSession(inter, echo=io.StringIO())

    dispatch(session, lex("s"))
    assert seen == ["ran"]
    dispatch(session, lex("undo"))
    assert seen == ["ran"]  # not rewound
    assert session.read_pseudo("pc") == [0]
    assert "debugger state only" in output(session)


def test_undo_leaves_the_context_stack_alone() -> None:
    from amrita_sense.runtime.types import InterpreterContext
    from amrita_sense.types import PointerVector

    inter = make_inter()
    session = RescueSession(inter, echo=io.StringIO())
    context = InterpreterContext(ptr=PointerVector([0]), exception_ignored=())
    inter._context_stack.stack.append(context)

    dispatch(session, lex("s"))
    dispatch(session, lex("undo"))
    assert context in inter._context_stack.stack


def test_undo_after_reset_cannot_restore_the_context_stack() -> None:
    from amrita_sense.runtime.types import InterpreterContext
    from amrita_sense.types import PointerVector

    inter = make_inter()
    session = RescueSession(inter, echo=io.StringIO())
    context = InterpreterContext(ptr=PointerVector([0]), exception_ignored=())
    inter._context_stack.stack.append(context)

    dispatch(session, lex("rs"))
    assert context not in inter._context_stack.stack
    dispatch(session, lex("undo"))
    # Documented behaviour: `undo` restores debugger state only.
    assert context not in inter._context_stack.stack
