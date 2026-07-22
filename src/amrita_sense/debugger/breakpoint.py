"""Breakpoint management for AmritaSense debugger.

Breakpoints are checked inside a composite middleware that wraps the
user's original middleware.  When a breakpoint matches the current node,
a :class:`BreakpointHit` exception is raised, which propagates out of
``run_step_by()`` and is caught by :func:`cont`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from amrita_sense.node.core import BaseNode

if TYPE_CHECKING:
    from amrita_sense.runtime.workflow import WorkflowInterpreter

#  module‑level state
# Keyed by interpreter id.  Each value is a dict:
#   breakpoints : list[Breakpoint]
#   saved_user_mw : callable | None   (the original _middleware)
#   stepping : bool                   (True → skip breakpoint checks)
#   debug_active : bool               (True after _ensure_debug_mw)
_debug_state: dict[str, dict] = {}


def _get_state(inter: WorkflowInterpreter) -> dict:
    if inter.id not in _debug_state:
        _debug_state[inter.id] = {
            "breakpoints": [],
            "saved_user_mw": None,
            "stepping": False,
            "debug_active": False,
        }
    return _debug_state[inter.id]


#  data types


class BreakpointHit(BaseException):
    """Raised when a breakpoint is hit inside the composite middleware."""

    def __init__(self, bp: Breakpoint) -> None:
        self.bp = bp

    def __str__(self) -> str:
        return str(self.bp)


@dataclass
class Breakpoint:
    """A breakpoint attached to an interpreter.

    Attributes:
        target: The tag string or address list to match against.
        kind: ``"tag"`` matches ``BaseNode.tag``; ``"addr"`` matches the
              pointer's ``base_addr``.
        condition: Optional callable ``(WorkflowInterpreter) -> bool``.
        hit_count: How many times this breakpoint has been triggered.
        enabled: Whether this breakpoint is currently active.
    """

    target: str | list[int]
    kind: Literal["tag", "addr"]
    condition: Callable[[WorkflowInterpreter], bool] | None = None
    hit_count: int = 0
    enabled: bool = True

    def __str__(self) -> str:
        cond = " cond" if self.condition else ""
        if self.kind == "tag":
            return f"tag='{self.target}' hits={self.hit_count}{cond}"
        return f"addr={self.target} hits={self.hit_count}{cond}"


#  middleware composition


def _create_debug_middleware(
    inter: WorkflowInterpreter,
    user_mw: Callable | None,
) -> Callable:
    """Build the composite middleware: breakpoint check → user_mw → _call."""

    async def debug_mw(pc: WorkflowInterpreter) -> object:
        state = _debug_state.get(pc.id, {})
        if not state.get("stepping", False):
            #  check breakpoints
            node = pc.get_graph().calc.find_addr_safe(pc._pointer.base_addr)
            if not isinstance(node, BaseNode):
                raise RuntimeError(
                    f"{pc.id}: node not found at {pc._pointer.base_addr}"
                )
            for bp in list(state.get("breakpoints", [])):
                if not bp.enabled:
                    continue
                if _bp_match(bp, node, pc):
                    bp.hit_count += 1
                    raise BreakpointHit(bp)

        #  call user middleware or direct
        if user_mw is not None:
            return await user_mw(pc)
        return await pc._call(no_cache=True)

    return debug_mw


def _ensure_debug_middleware(inter: WorkflowInterpreter) -> None:
    """Install composite middleware on *inter* if not already active.

    Preserves the user's original middleware so it is still invoked
    after the breakpoint check.
    """
    state = _get_state(inter)
    if state["debug_active"]:
        return

    # Save original user middleware
    user_mw = inter._middleware
    state["saved_user_mw"] = user_mw

    # Install composite
    inter._middleware = _create_debug_middleware(inter, user_mw)
    state["debug_active"] = True


#  breakpoint matching


def _resolve_addr(inter: WorkflowInterpreter, addr: str | list[int]) -> list[int]:
    """Normalise *addr*: resolve alias strings, pass lists through."""
    if isinstance(addr, str):
        return inter.get_graph().calc.resolve_alias(addr)
    return addr


def _bp_match(
    bp: Breakpoint,
    node: BaseNode | None,
    pc: WorkflowInterpreter,
) -> bool:
    """Return *True* if *bp* is triggered at the current position."""
    if bp.kind == "tag":
        if node is None or not isinstance(bp.target, str) or node.tag != bp.target:
            return False
    elif bp.kind == "addr":
        target = (
            bp.target if isinstance(bp.target, list) else _resolve_addr(pc, bp.target)
        )
        if pc._pointer.base_addr != target:
            return False

    if bp.condition is not None:
        try:
            return bool(bp.condition(pc))
        except Exception:
            return False
    return True


#  public API


def break_at_tag(
    inter: WorkflowInterpreter,
    tag: str,
    *,
    condition: Callable[[WorkflowInterpreter], bool] | None = None,
) -> Breakpoint:
    """Set a breakpoint on every node whose ``tag`` matches *tag*.

    Returns the :class:`Breakpoint` instance so callers can inspect
    ``hit_count`` or toggle ``enabled`` later.
    """
    _ensure_debug_middleware(inter)
    bp = Breakpoint(target=tag, kind="tag", condition=condition)
    _get_state(inter)["breakpoints"].append(bp)
    print(f"🔴 Breakpoint: {bp}")
    return bp


def break_at_addr(
    inter: WorkflowInterpreter,
    addr: list[int] | str,
    *,
    condition: Callable[[WorkflowInterpreter], bool] | None = None,
) -> Breakpoint:
    """Set a breakpoint at *addr*.

    *addr* can be:

    * ``list[int]`` – raw address vector, e.g. ``[0, 1]``
    * ``str``      – alias resolved via ``AddressCalculator.resolve_alias()``
    """
    _ensure_debug_middleware(inter)
    resolved = _resolve_addr(inter, addr)
    bp = Breakpoint(target=resolved, kind="addr", condition=condition)
    _get_state(inter)["breakpoints"].append(bp)
    print(f"🔴 Breakpoint: {bp}")
    return bp


def clear_break_tag(inter: WorkflowInterpreter, tag: str) -> None:
    """Remove all breakpoints matching *tag*."""
    state = _get_state(inter)
    removed = [
        bp for bp in state["breakpoints"] if bp.kind == "tag" and bp.target == tag
    ]
    for bp in removed:
        state["breakpoints"].remove(bp)
    for bp in removed:
        print(f"✖  Removed: {bp}")


def clear_break_addr(inter: WorkflowInterpreter, addr: list[int] | str) -> None:
    """Remove the breakpoint at *addr* (raw address or alias)."""
    state = _get_state(inter)
    resolved = _resolve_addr(inter, addr)
    removed = [
        bp for bp in state["breakpoints"] if bp.kind == "addr" and bp.target == resolved
    ]
    for bp in removed:
        state["breakpoints"].remove(bp)
    for bp in removed:
        print(f"✖  Removed: {bp}")


def list_breaks(inter: WorkflowInterpreter) -> None:
    """Print all breakpoints registered on *inter*."""
    state = _get_state(inter)
    bps = state["breakpoints"]
    if not bps:
        print("(no breakpoints)")
        return
    for i, bp in enumerate(bps, 1):
        kind = bp.kind.upper()
        cond = (
            f" cond={bp.condition.__name__ if hasattr(bp.condition, '__name__') else '<lambda>'}"
            if bp.condition
            else ""
        )
        status = "" if bp.enabled else " [DISABLED]"
        print(f"  {i}. {kind}  {bp.target!r}  hits={bp.hit_count}{cond}{status}")
