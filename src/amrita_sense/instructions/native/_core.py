"""Native control-flow core nodes — lightweight jump+RET_FAR based branching.

These nodes replace ``call_sub`` for branch bodies with the
``PUSH / JMP / RET_FAR`` pattern, avoiding lock acquisition, middleware
invocation, and DI resolution on every branch entry.  Compile-time
``_is_single`` dispatch keeps single-node bodies on the fast ``call_offset``
path with zero additional overhead.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from types import FrameType
from typing import Any, Literal, overload

from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.node.core import BaseNode, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


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

    **Bubble path:** ``CALL condi`` → True: ``PUSH ret; jump_far_ptr([do_pos,0])`` | False: ``jmp false``.
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
                parent = list(pc._pointer.base_addr[:-1])
                pc._ret_addr_stack.push(PointerVector([*parent, self._ret_pos]))
                pc.jump_far_ptr([*parent, self._do_pos, 0])
        else:
            pc.jump_near(self._false_pos)


# NativeWhileNode


class NativeWhileNode(BaseNode):
    """WHILE-condition jump node for native fast-path loops.

    Layout: ``[pos]`` self, ``[pos+1]`` cond, ``[pos+2]`` body slot, ``[pos+3]`` NOP exit.

    The bubble variant pushes ``[pos]`` so that ``RET_FAR`` jumps back
    to **this node** rather than past it, re‑evaluating the condition.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    _condi_offset: int
    _body_offset: int
    _body_pos: int
    _self_pos: int
    _exit_pos: int
    _is_single: bool

    __slots__ = (
        "_body_offset",
        "_body_pos",
        "_condi_offset",
        "_exit_pos",
        "_is_single",
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
        body_offset: int,
        body_pos: int,
        self_pos: int,
        exit_pos: int,
        is_single: bool,
    ) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        self._init(
            self.__call__, tag=None, wrap_to_async=True, address_able=True, frame=frame
        )
        self._condi_offset = condi_offset
        self._body_offset = body_offset
        self._body_pos = body_pos
        self._self_pos = self_pos
        self._exit_pos = exit_pos
        self._is_single = is_single

    async def __call__(self, pc: WorkflowInterpreter) -> None:
        if await pc.call_offset(self._condi_offset):
            if self._is_single:
                await pc.call_offset(self._body_offset)
                pc.jump_near(self._self_pos)
            else:
                parent = list(pc._pointer.base_addr[:-1])
                pc._ret_addr_stack.push(PointerVector([*parent, self._self_pos]))
                pc.jump_far_ptr([*parent, self._body_pos, 0])
        else:
            pc.jump_near(self._exit_pos)


# NativeDoWhileNode


class NativeDoWhileNode(BaseNode):
    """DO‑WHILE back-edge node with unified PUSH+RET_FAR semantics.

    Single-node path: ``call_offset`` condition → True: ``jump_near(body_pos)``
    loop back; False: ``jump_near(exit_pos)``.

    Bubble path: condition true → ``jump_near(body_pos)`` which hits
    ``NativeBubbleEnterNode`` (PUSH+JMP into the body bubble).  The body
    bubble ends with ``RET_FAR``, returning here to re‑evaluate.
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

    Used when a native instruction's body is a ``NodeCompose`` that must be
    reached via a jump (DO-body, ELSE-body).  The single‑node path reaches
    the body naturally without this hop.

    When *ret_pos* is provided (DO loops), a return address is pushed onto
    ``_ret_addr_stack`` before entering the bubble so that ``RET_FAR`` (or
    ``BREAK_LOOP``) can return/break to the correct position.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta

    _body_pos: int
    _ret_pos: int | None

    __slots__ = (
        "_body_pos",
        "_ret_pos",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, body_pos: int, ret_pos: int | None = None) -> None:
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        self._init(
            self.__call__, tag=None, wrap_to_async=False, address_able=True, frame=frame
        )
        self._body_pos = body_pos
        self._ret_pos = ret_pos

    def __call__(self, pc: WorkflowInterpreter) -> None:
        parent = list(pc._pointer.base_addr[:-1])
        if self._ret_pos is not None:
            pc._ret_addr_stack.push(PointerVector([*parent, self._ret_pos]))
        pc.jump_far_ptr([*parent, self._body_pos, 0])
