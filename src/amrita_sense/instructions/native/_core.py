"""Native control-flow core nodes — lightweight jump-based branching.

These nodes replace ``call_sub`` for branch bodies with the
``PUSH / JMP / CONTINUE / BREAK_LOOP`` pattern, avoiding lock acquisition,
middleware invocation, and DI resolution on every branch entry.

Loop bodies always end with ``CONTINUE()`` (factory), and ``BREAK_LOOP()``
targets are configured at compile-time via ``_configure_loop_control_nodes()``.
Single-node bodies are auto‑wrapped into ``NodeCompose(body, CONTINUE())``.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from types import FrameType
from typing import Any, Literal, overload

from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.instructions.enum import BuiltinTags
from amrita_sense.node.core import BaseNode, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector

#  _LoopControlNode (shared by CONTINUE & BREAK_LOOP)


class _LoopControlNode(BaseNode):
    """Abstract base: pop ``_ret_addr_stack`` and ``jump_far_ptr``.

    Subclasses are configured at compile-time by the enclosing native
    loop's ``extract()`` via ``_configure_loop_control_nodes()``.

    At runtime the popped ``PointerVector`` provides the parent address;
    ``_target_pos`` (set by the scanner) gives the offset within that
    parent.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    _configured: bool
    _target_pos: int

    __slots__ = (
        "_configured",
        "_target_pos",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self) -> None:
        self._configured = False
        self._target_pos = -1

    def __call__(self, pc: WorkflowInterpreter) -> None:
        if not self._configured:
            raise RuntimeError(
                f"{self.tag}: not configured — must be inside a native loop body"
            )
        ptr = pc._ret_addr_stack.pop()
        parent = list(ptr.base_addr[:-1])
        pc.jump_far_ptr([*parent, self._target_pos])


#  DFS scanner


def _configure_loop_control_nodes(
    compose: NodeCompose,
    continue_pos: int,
    break_pos: int,
) -> None:
    """DFS-scan *compose*, configuring unconfigured loop-control nodes.

    Stops recursing at native-loop boundaries (``NativeWhileNode`` or
    ``NativeBubbleEnterNode`` as the first child of a ``NodeCompose``).
    This ensures each loop only configures control nodes at its own
    nesting level.
    """
    for child in compose._graph:
        if isinstance(child, _LoopControlNode) and not child._configured:
            child._target_pos = (
                continue_pos if child.tag == BuiltinTags.CONTINUE else break_pos
            )
            child._configured = True
        elif isinstance(child, NodeCompose):
            first = child._graph[0] if child._graph else None
            if isinstance(first, (NativeWhileNode, NativeBubbleEnterNode)):
                continue  # inner native loop boundary — stop here
            _configure_loop_control_nodes(child, continue_pos, break_pos)


@overload
def _classify_body(
    payload: BaseNode,
) -> tuple[BaseNode, Literal[True]]: ...
@overload
def _classify_body(
    payload: NodeCompose | SelfCompileInstruction,
) -> tuple[NodeCompose, Literal[False]]: ...
def _classify_body(
    payload: BaseNode | NodeCompose | SelfCompileInstruction,
) -> tuple[BaseNode | NodeCompose, bool]:
    """Classify *payload* as single-node or compose.

    Returns
    -------
    (body, is_single)
        ``is_single`` is ``True`` when *payload* is a ``BaseNode``
        (call_offset path).  ``SelfCompileInstruction`` is extracted
        to ``NodeCompose`` first.  The compose itself is returned
        as-is — ``render()`` will recursively expand nested layers.
    """
    if isinstance(payload, BaseNode):
        return payload, True

    if isinstance(payload, SelfCompileInstruction):
        payload = payload.extract()

    if isinstance(payload, NodeCompose):
        return payload, False

    raise TypeError(f"Unsupported payload type: {type(payload).__name__}")


#  NativeIfJumpNode


class NativeIfJumpNode(BaseNode):
    """IF-condition jump node for native fast-path branching.

    Layout (after ``extract()``):

    - ``[pos]`` NativeIfJumpNode
    - ``[pos+1]`` condition_node — ``call_offset(1)``
    - ``[pos+2]`` do_slot (single node or bubble)
    - ``[pos+3]`` NOP (merge / false target)

    **Single-node path:** ``CALL condi`` → True: ``CALL do; jmp_near ret`` | False: ``jmp false``.

    **Bubble path:** ``CALL condi`` → True: ``jump_far_ptr([do_pos,0])`` (the bubble is a
    nested container — it flows back to the merge point naturally) | False: ``jmp false``.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    _condi_offset: int
    _do_offset: int
    _do_pos: int
    _ret_pos: int
    _false_pos: int
    _is_single: bool

    __slots__ = (
        "_condi_offset",
        "_do_offset",
        "_do_pos",
        "_false_pos",
        "_is_single",
        "_ret_pos",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(
        self,
        condi_offset: int,
        do_offset: int,
        do_pos: int,
        ret_pos: int,
        false_pos: int,
        is_single: bool,
    ) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        self._init(
            self.__call__, tag=None, wrap_to_async=True, address_able=True, frame=frame
        )
        self._condi_offset = condi_offset
        self._do_offset = do_offset
        self._do_pos = do_pos
        self._ret_pos = ret_pos
        self._false_pos = false_pos
        self._is_single = is_single

    async def __call__(self, pc: WorkflowInterpreter) -> None:
        if await pc.call_offset(self._condi_offset):
            if self._is_single:
                await pc.call_offset(self._do_offset)
                pc.jump_near(self._ret_pos)
            else:
                # Bubble path: no PUSH/RET_FAR — nested container flows back via advance_pointer.
                parent = list(pc._pointer.base_addr[:-1])
                pc.jump_far_ptr([*parent, self._do_pos, 0])
        else:
            pc.jump_near(self._false_pos)


# NativeWhileNode


class NativeWhileNode(BaseNode):
    """WHILE-condition jump node for native fast-path loops.

    Layout: ``[pos]`` self, ``[pos+1]`` cond, ``[pos+2]`` body (+CONTINUE),
    ``[pos+3]`` NOP exit.

    Cond true → push ``[pos]`` onto ``_ret_addr_stack``, ``jump_far_ptr``
    into body.  The body's trailing ``CONTINUE()`` pops and jumps back to
    ``[pos]``, re‑evaluating the condition.

    Supports nesting: each loop level pushes its own head position.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    _condi_offset: int
    _body_pos: int
    _self_pos: int
    _exit_pos: int

    __slots__ = (
        "_body_pos",
        "_condi_offset",
        "_exit_pos",
        "_self_pos",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(
        self,
        condi_offset: int,
        body_pos: int,
        self_pos: int,
        exit_pos: int,
    ) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        self._init(
            self.__call__, tag=None, wrap_to_async=True, address_able=True, frame=frame
        )
        self._condi_offset = condi_offset
        self._body_pos = body_pos
        self._self_pos = self_pos
        self._exit_pos = exit_pos

    async def __call__(self, pc: WorkflowInterpreter) -> None:
        if await pc.call_offset(self._condi_offset):
            parent = list(pc._pointer.base_addr[:-1])
            pc._ret_addr_stack.push(PointerVector([*parent, self._self_pos]))
            pc.jump_far_ptr([*parent, self._body_pos, 0])
        else:
            pc.jump_near(self._exit_pos)


# NativeDoWhileNode


class NativeDoWhileNode(BaseNode):
    """DO‑WHILE back-edge node.

    Layout: ``[loop_pos]`` enter → body (+CONTINUE) → ``[pos]`` self,
    ``[pos+1]`` cond, ``[pos+2]`` NOP exit.

    Cond true → ``jump_near(loop_pos)`` re-enters body via enter.
    The body's trailing ``CONTINUE()`` pops and jumps back to ``[pos]``
    to re‑evaluate the condition.

    Supports nesting: each loop level pushes its own head position.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    _condi_offset: int
    _loop_pos: int
    _exit_pos: int

    __slots__ = (
        "_condi_offset",
        "_exit_pos",
        "_loop_pos",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, condi_offset: int, loop_pos: int, exit_pos: int) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        self._init(
            self.__call__, tag=None, wrap_to_async=True, address_able=True, frame=frame
        )
        self._condi_offset = condi_offset
        self._loop_pos = loop_pos
        self._exit_pos = exit_pos

    async def __call__(self, pc: WorkflowInterpreter) -> None:
        if await pc.call_offset(self._condi_offset):
            pc.jump_near(self._loop_pos)
        else:
            pc.jump_near(self._exit_pos)


# NativeBubbleEnterNode  (bubble entry helper for DO / ELSE)


class NativeBubbleEnterNode(BaseNode):
    """Helper node that enters a body bubble.

    Used when a native instruction's body is reached via a jump
    (DO body, ELSE body).  With ``push=True`` (DO), pushes a sentinel onto
    ``_ret_addr_stack`` so that ``CONTINUE()`` and ``BREAK_LOOP()`` can pop
    it and jump to their configured targets.  With ``push=False`` (ELSE,
    since v0.6.1), no push is performed — the bubble flows back to the
    merge point naturally via ``advance_pointer``, like a Python ``else``
    block (no early-return / RET_FAR semantics).
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    _body_pos: int
    _push: bool

    __slots__ = (
        "_body_pos",
        "_push",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, body_pos: int, push: bool = True) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        self._init(
            self.__call__, tag=None, wrap_to_async=False, address_able=True, frame=frame
        )
        self._body_pos = body_pos
        self._push = push

    def __call__(self, pc: WorkflowInterpreter) -> None:
        parent = list(pc._pointer.base_addr[:-1])
        if self._push:
            pc._ret_addr_stack.push(PointerVector([*parent, 0]))
        pc.jump_far_ptr([*parent, self._body_pos, 0])
