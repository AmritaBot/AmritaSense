"""Command grammar for the SenseDBG rescue REPL.

The grammar is small on purpose: a word, a few operands, no expressions.  The
escape hatch to arbitrary Python is ``py``, not a cleverer parser.

Every handler receives the live :class:`RescueSession`; async handlers are
awaited on the interpreter's loop by :func:`dispatch`.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import inspect as py_inspect
import sys
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from amrita_sense.debugger.breakpoint import (
    _get_state,
    break_at_addr,
    break_at_tag,
    clear_break_addr,
    clear_break_tag,
    list_breaks,
)
from amrita_sense.debugger.code_disp import DEFAULT_WINDOW, dis
from amrita_sense.debugger.inspect import backtrace, list_nodes, list_sub_intp, where
from amrita_sense.debugger.inspect import inspect as inspect_view
from amrita_sense.debugger.repl.console import RescueConsole, render_banner
from amrita_sense.debugger.repl.session import RescueSession, SessionError
from amrita_sense.debugger.repl.theme import PROMPT, sanitize
from amrita_sense.debugger.step import (
    cont_async,
    step_async,
    step_out_async,
    step_over_async,
)

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class Command:
    """One REPL command, its operands and its documentation."""

    name: str
    usage: str
    summary: str
    handler: Any
    aliases: tuple[str, ...] = ()


REGISTRY: dict[str, Command] = {}


def command(*names: str, usage: str = "", summary: str = "") -> Any:
    """Register a handler under *names* (the first one is canonical)."""

    def decorator(func: Any) -> Any:
        entry = Command(
            name=names[0],
            usage=usage or names[0],
            summary=summary,
            handler=func,
            aliases=tuple(names[1:]),
        )
        for name in names:
            REGISTRY[name] = entry
        return func

    return decorator


def _join(args: list[str]) -> str:
    return " ".join(args).strip()


def _int_arg(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw, 0)
    except ValueError as exc:
        raise SessionError(f"expected an integer, got {raw!r}") from exc


def _as_addr(value: Any) -> list[int]:
    if isinstance(value, str):
        with contextlib.suppress(Exception):
            value = ast.literal_eval(value)
    if isinstance(value, (list, tuple)) and value:
        addr: list[int] = []
        for item in value:
            # Rejecting here keeps `jump`/`set $pc` from truncating 1.7 into 1.
            if isinstance(item, bool) or not isinstance(item, int):
                raise SessionError(f"address coordinates must be ints, got {value!r}")
            if item < 0:
                raise SessionError(
                    f"address coordinates must be non-negative, got {value!r}"
                )
            addr.append(item)
        return addr
    raise SessionError(f"expected an address like [1, 0], got {value!r}")


def _eval_globals(session: RescueSession) -> dict[str, Any]:
    """Restricted globals for ``p`` / ``set``.

    This is not a sandbox and does not pretend to be one — ``inter`` alone is
    a process handle.  It exists so ``$pc`` reads like a register instead of a
    private attribute lookup.
    """
    from amrita_sense import debugger as sdb_module

    return {
        "__builtins__": builtins,
        "inter": session.inter,
        "sdb": sdb_module,
        "pc": session.read_pseudo("pc"),
        "rp": session.read_pseudo("rp"),
        "flags": session.read_pseudo("flags"),
        "exc": session.read_pseudo("exc"),
    }


def _eval(session: RescueSession, expression: str) -> Any:
    source = expression.replace("$", "")
    try:
        return eval(source, _eval_globals(session))
    except Exception as exc:
        raise SessionError(f"{type(exc).__name__}: {exc}") from exc


def _fmt(value: Any, limit: int = 2000) -> str:
    text = repr(value)
    return (
        text if len(text) <= limit else text[:limit] + f"… (+{len(text) - limit} chars)"
    )


def _pending_panic(session: RescueSession) -> bool:
    exc = session.inter.get_exception()
    if exc is None:
        return False
    pc = session.read_pseudo("pc")
    session.warn(f"[panic pending] {type(exc).__name__}: {sanitize(str(exc))} @ {pc}")
    session.note("  `s`/`c` will re-run that node; `skip` advances past it")
    return True


@command("s", "step", usage="s [n]", summary="execute n nodes (default 1)")
async def _cmd_step(session: RescueSession, args: list[str]) -> None:
    _guard_live(session)
    count = _int_arg(args[0] if args else None, 1)
    if count < 1:
        raise SessionError("n must be >= 1")
    _pending_panic(session)
    session.claim_driver()
    try:
        for _ in range(count):
            await step_async(session.inter)
    finally:
        session.release_driver()


@command("n", "next", usage="n", summary="step over one node")
async def _cmd_next(session: RescueSession, args: list[str]) -> None:
    _guard_live(session)
    _pending_panic(session)
    session.claim_driver()
    try:
        await step_over_async(session.inter)
    finally:
        session.release_driver()


@command("fin", "finish", usage="fin", summary="run to the end of this frame")
async def _cmd_finish(session: RescueSession, args: list[str]) -> None:
    _guard_live(session)
    _pending_panic(session)
    session.claim_driver()
    try:
        await step_out_async(session.inter)
    finally:
        session.release_driver()


@command("c", "cont", "continue", usage="c", summary="continue to breakpoint or end")
async def _cmd_cont(session: RescueSession, args: list[str]) -> None:
    _guard_live(session)
    _pending_panic(session)
    session.claim_driver()
    try:
        await cont_async(session.inter)
    finally:
        session.release_driver()


@command("skip", usage="skip", summary="advance past the node that panicked")
def _cmd_skip(session: RescueSession, args: list[str]) -> None:
    if session.inter.get_exception() is None:
        raise SessionError("no panic is pending")
    moved = session.inter.advance_pointer()
    if not moved:
        session.at_end = True
        session.warn("the failed node was the last one — the workflow is over")
        session.note("use `suppress` to return normally, or `q` to re-raise")
        return
    session.ok(f"pc -> {session.read_pseudo('pc')}")
    session.note("`s` or `c` will now resume after the failed node")


@command("u", "until", usage="u [addr]", summary="step until past the current address")
async def _cmd_until(session: RescueSession, args: list[str]) -> None:
    _guard_live(session)
    start = session.read_pseudo("pc")
    target = _as_addr(_join(args)) if args else None
    session.claim_driver()
    try:
        for _ in range(10000):
            await step_async(session.inter)
            current = session.read_pseudo("pc")
            if current is None:
                session.note("[until] workflow ended")
                return
            if target is not None and list(current) == target:
                return
            if target is None and start is not None and list(current) > list(start):
                return
    finally:
        session.release_driver()
    session.error("until gave up after 10000 steps")


@command("j", "jump", usage="j [1, 0]", summary="move the program counter")
def _cmd_jump(session: RescueSession, args: list[str]) -> None:
    if not args:
        raise SessionError("usage: j [1, 0]")
    addr = _as_addr(_join(args))
    session.write_pseudo("$pc", addr)
    session.ok(f"pc = {addr}")


@command("bt", "backtrace", usage="bt", summary="print the interpreter call chain")
def _cmd_backtrace(session: RescueSession, args: list[str]) -> None:
    session.write(session.render_block(lambda: backtrace(session.inter)))


@command(
    "i", "info", usage="i r|b|f|l", summary="inspect registers/breakpoints/frames/nodes"
)
def _cmd_info(session: RescueSession, args: list[str]) -> None:
    what = (args[0] if args else "r").lower()
    inter = session.inter
    if what in ("r", "reg", "regs", "registers"):
        session.write(session.render_block(lambda: inspect_view(inter)))
    elif what in ("b", "break", "breakpoints"):
        session.write(session.render_block(lambda: list_breaks(inter)))
    elif what in ("f", "frames", "tree"):
        session.write(session.render_block(lambda: list_sub_intp(inter)))
    elif what in ("l", "locals", "nodes"):
        session.write(session.render_block(lambda: list_nodes(inter)))
    elif what in ("w", "where"):
        session.write(session.render_block(lambda: where(inter)))
    else:
        raise SessionError(f"unknown info topic: {what}")


@command("x", "examine", usage="x [n]", summary="disassemble n nodes around pc")
def _cmd_examine(session: RescueSession, args: list[str]) -> None:
    around = _int_arg(args[0] if args else None, DEFAULT_WINDOW)
    session.write(
        session.render_block(lambda: dis(session.inter, around=around)),
    )


@command("p", "print", usage="p $pc", summary="evaluate a restricted expression")
def _cmd_print(session: RescueSession, args: list[str]) -> None:
    expression = _join(args)
    if not expression:
        raise SessionError("usage: p $pc | p len(inter._pointer.base_addr)")
    session.write(_fmt(_eval(session, expression)))


@command("set", usage="set $pc = [1, 0]", summary="write a pseudo-register")
def _cmd_set(session: RescueSession, args: list[str]) -> None:
    raw = _join(args)
    name, separator, value = raw.partition("=")
    if not separator:
        raise SessionError("usage: set $pc = [1, 0]")
    session.write_pseudo(name.strip(), _eval(session, value.strip()))
    session.ok(f"{name.strip()} = {_fmt(session.read_pseudo(name.strip()))}")


@command("b", "break", usage="b tag:name | b *[1, 0]", summary="set a breakpoint")
def _cmd_break(session: RescueSession, args: list[str]) -> None:
    if not args:
        raise SessionError("usage: b tag:name | b *[1, 0]")
    spec = _join(args)
    inter = session.inter
    if spec.startswith("*"):
        addr = _as_addr(spec[1:])
        break_at_addr(inter, addr)
        session.ok(f"break at {addr}")
        return
    tag = spec[4:] if spec.startswith("tag:") else spec
    tag = tag.strip("\"'")
    break_at_tag(inter, tag)
    session.ok(f"break at tag {tag!r}")


@command(
    "d", "delete", usage="d tag:name | d *[1, 0] | d all", summary="delete breakpoints"
)
def _cmd_delete(session: RescueSession, args: list[str]) -> None:
    if not args:
        session.write(session.render_block(lambda: list_breaks(session.inter)))
        session.note("usage: d tag:name | d *[1, 0] | d all")
        return
    spec = _join(args)
    if spec == "all":
        _get_state(session.inter)["breakpoints"].clear()
        session.ok("all breakpoints cleared")
        return
    if spec.startswith("*"):
        addr = _as_addr(spec[1:])
        clear_break_addr(session.inter, addr)
        session.ok(f"cleared {addr}")
        return
    tag = spec[4:] if spec.startswith("tag:") else spec
    tag = tag.strip("\"'")
    clear_break_tag(session.inter, tag)
    session.ok(f"cleared tag {tag!r}")


@command("bl", "breaks", usage="bl", summary="list breakpoints")
def _cmd_breaks(session: RescueSession, args: list[str]) -> None:
    session.write(session.render_block(lambda: list_breaks(session.inter)))


@command("rs", "reset", usage="rs", summary="reset the interpreter (not undoable)")
def _cmd_reset(session: RescueSession, args: list[str]) -> None:
    session.inter.reset()
    session.warn("interpreter reset — pc, stacks and context stack cleared")
    session.note(
        "`undo` only restores pc / return stack / flags / panic; the context stack does not come back"
    )


@command(
    "undo",
    usage="undo",
    summary="restore debugger state (pc/stack/flags) — not a rollback",
)
def _cmd_undo(session: RescueSession, args: list[str]) -> None:
    """Restore the debugger view, not the business state.

    Nodes that already ran stay ran: their side effects, the context stack and
    the workflow-scoped dependencies are untouched.  This is a convenience for
    putting the program counter and registers back, not a transaction log.
    """
    session.undo()
    session.ok(
        f"restored: pc={session.read_pseudo('pc')} flags={session.read_pseudo('flags')}"
    )
    session.note(
        "debugger state only: node side effects, context stack and DI scope stay as they are"
    )


@command("py", "python", usage="py [code]", summary="Python console (see `py` banner)")
def _cmd_py(session: RescueSession, args: list[str]) -> None:
    console = RescueConsole(session)
    if args:
        stream = session.echo if session.echo is not None else sys.stdout
        with (
            contextlib.redirect_stdout(stream),
            contextlib.redirect_stderr(stream),
        ):
            console.push(_join(args))
        applied = session.sync_from_namespace(console.locals)
        if applied:
            session.ok(f"[py] applied: {', '.join(applied)}")
        return
    console.enter(banner=render_banner())
    session.note("[py] returned to (sdb) — session still open")


@command(
    "q", "quit", "exit", usage="q", summary="leave and re-raise the original panic"
)
def _cmd_quit(session: RescueSession, args: list[str]) -> str:
    session.exit_reason = "quit"
    session.warn("leaving rescue; the original panic will be re-raised")
    return "quit"


@command("k", "kill", usage="k", summary="abandon the state and close the scope")
def _cmd_kill(session: RescueSession, args: list[str]) -> str:
    session.exit_reason = "kill"
    session.warn("rescue abandoned; workflow scope will be closed")
    return "kill"


# Accepted operands for suppress.
_RESUME_WORDS = {"continue", "cont", "c", "resume"}


def _finish_suppress(session: RescueSession) -> None:
    """Mark the panic as suppressed, keeping the original error for the audit."""
    inter = session.inter
    if session.original_panic is not None:
        # s/c clear `_panic_exc`; put the original back so `get_exception()` still answers.
        inter._panic_exc = session.original_panic
    inter._panic_suppressed = True
    session.at_end = True
    session.exit_reason = "suppress"


def _guard_live(session: RescueSession) -> None:
    """Refuse to drive a workflow that already ended inside this rescue.

    An empty pointer means both "not started" and "finished"; after `skip` on
    the last node we know it is the latter, and re-driving would restart at
    `[0]` and re-run earlier nodes.
    """
    if session.at_end:
        raise SessionError("the workflow already ended here; use `suppress` or `q`")


@command(
    "suppress",
    "pass",
    usage="suppress [continue]",
    summary="swallow this panic; `continue` finishes the run first",
)
async def _cmd_suppress(session: RescueSession, args: list[str]) -> str | None:
    """End the rescue without re-raising.

    Two modes:

    * ``suppress`` — give up here; ``run()`` returns normally.
    * ``suppress continue`` — advance past the failing node, run the rest, then
      return normally.  A second panic is *not* swallowed silently: the command
      reports it and leaves the session open.

    Either way the failure stays discoverable: ``inter.get_exception()`` keeps
    it, ``inter.panic_suppressed`` is set, and a warning is logged.  A silent
    failure that looks like success is worse than an exception.
    """
    if len(args) > 1:
        raise SessionError("usage: suppress [continue]")
    resume = bool(args)
    if resume and args[0].lower() not in _RESUME_WORDS:
        # A typo in `suppress continue` must not silently become plain `suppress`.
        raise SessionError(
            f"unknown suppress mode: {args[0]!r} (usage: suppress [continue])"
        )

    if not resume:
        _finish_suppress(session)
        session.warn(
            "suppressing the panic — run() will return normally, no exception propagates"
        )
        session.note(
            "still recorded: inter.get_exception() keeps the error and the log gets a warning"
        )
        session.note("to recover instead of swallowing, use `skip` then `c`")
        return "suppress"

    if session.inter.get_exception() is None:
        raise SessionError("no panic is pending")
    if session.at_end or not session.inter._pointer:
        _finish_suppress(session)
        session.ok("panic suppressed; there was nothing left to run")
        return "suppress"

    session.inter.advance_pointer()
    session.claim_driver()
    try:
        try:
            await cont_async(session.inter)
        except Exception as exc:
            session.error(
                f"another panic surfaced during the suppressed run: {type(exc).__name__}: {exc}"
            )
            session.note("deal with it, or use plain `suppress` to end here")
            return None
    finally:
        session.release_driver()
    if session.inter.get_exception() is not None:
        session.error("the run did not finish cleanly — not swallowing this one")
        return None
    if session.inter._pointer:
        # A breakpoint or interrupt makes `cont_async` return without finishing.
        session.warn("the run stopped early (breakpoint or interrupt), not at the end")
        session.note("continue again, or use plain `suppress` to end here")
        return None
    _finish_suppress(session)
    session.ok("panic suppressed; the remaining workflow ran to completion")
    return "suppress"


@command("help", "h", "?", usage="help [command]", summary="list commands")
def _cmd_help(session: RescueSession, args: list[str]) -> None:
    if args:
        entry = REGISTRY.get(args[0])
        if entry is None:
            raise SessionError(f"unknown command: {args[0]}")
        names = ", ".join((entry.name, *entry.aliases))
        session.write(f"{session.theme.paint(names, PROMPT)}  —  {entry.summary}")
        session.write(f"usage: {entry.usage}")
        return
    seen: set[str] = set()
    for entry in REGISTRY.values():
        if entry.name in seen:
            continue
        seen.add(entry.name)
        names = "/".join((entry.name, *entry.aliases))
        pad = " " * max(0, 22 - len(names))
        session.write(f"  {session.theme.paint(names, PROMPT)}{pad}{entry.summary}")
    session.write("  (blank line repeats the previous command; # starts a comment)")


def dispatch(session: RescueSession, tokens: list[str]) -> str | None:
    """Run one parsed line.

    Returns ``"quit"`` / ``"kill"`` when the session should end, otherwise
    ``None``.  Handler failures are printed and swallowed: a typo must never
    become a second panic.
    """
    if not tokens:
        if not session.last_tokens:
            session.error("no previous command")
            return None
        tokens = list(session.last_tokens)
        session.note(f"repeat: {' '.join(tokens)}")
    else:
        session.last_tokens = list(tokens)

    entry = REGISTRY.get(tokens[0])
    if entry is None:
        session.error(f"unknown command: {tokens[0]} (try `help`)")
        return None

    try:
        result = entry.handler(session, tokens[1:])
        if py_inspect.isawaitable(result):
            result = session.run_coroutine(cast("Coroutine[Any, Any, Any]", result))
    except KeyboardInterrupt:
        session.warn("[interrupted]")
        return None
    except SystemExit:
        session.warn("[exit ignored in (sdb); use `q` to leave]")
        return None
    except SessionError as exc:
        session.error(str(exc))
        return None
    except Exception as exc:
        session.error(f"{type(exc).__name__}: {exc}")
        return None
    return result if result in {"quit", "kill", "suppress"} else None


__all__ = ["REGISTRY", "Command", "command", "dispatch"]
