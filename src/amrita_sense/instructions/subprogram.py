import difflib
from collections.abc import Callable
from types import FrameType
from typing import Any

from typing_extensions import override

from amrita_sense.exceptions import AliasNotFoundError, GraphBuildError
from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.instructions.enum import BuiltinTags
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, NodeCompose, NodeComposeRendered
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter


class SubprogramJumpNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _target_near: int
    __slots__ = (
        "_target_near",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, target_near: int):
        self._target_near = target_near
        self._init(
            func=self.__call__,
            tag=None,
            wrap_to_async=False,
            address_able=True,
        )

    def __call__(self, pc: WorkflowInterpreter):
        pc.jump_near(self._target_near)


class SubprogramStorage(SelfCompileInstruction):
    _nodes: tuple[BaseNode, ...]
    __slots__ = ("_nodes",)

    def __init__(self, *nodes: BaseNode):
        self._nodes = nodes

    def extract(self) -> NodeCompose:
        node_compose = [NOP, *self._nodes, NOP]
        addr: int = len(node_compose) - 1
        node_compose[0] = SubprogramJumpNode(addr)
        return NodeCompose(*node_compose)


class CallNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _alias: str
    _addr: list[int]

    __slots__ = (
        "_addr",
        "_alias",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, alias: str, tag: str | None = None):
        self._alias = alias
        self._init(self.__call__, tag, False, True)

    @override
    def _post_compile(self, compose: NodeComposeRendered) -> None:
        if (addr := compose.alias2vector_map.get(self._alias)) is None:
            str_keys = list(compose.alias2vector_map.keys())
            matches = difflib.get_close_matches(self._alias, str_keys, n=1, cutoff=0.6)
            if matches:
                suggestion = matches[0]
                hint = (
                    f"{self._alias} not found in namespace, did you mean {suggestion}"
                )
            else:
                hint = f"{self._alias} not found in namespace, please check your alias!"
            raise AliasNotFoundError(hint)
        nd = compose.calc.find_addr(addr)
        if isinstance(nd, NodeComposeRendered):
            raise GraphBuildError(
                "Cannot call a NodeComposeRendered directly! Please use PUSH_AND_GOTO with RET_FAR instead"
            )
        elif nd.address_able is False:
            raise GraphBuildError("Cannot call a non-addressable node!")
        self._addr = addr

    async def __call__(self, pc: WorkflowInterpreter) -> Any:
        return await pc.call_sub(self._addr)


def CALL(alias: str) -> CallNode:
    """Create a single-step subroutine call node.

    Performs a synchronous call to the subroutine at the given alias via
    :meth:`WorkflowInterpreter.call_sub`.  This is a **single-step** call —
    the interpreter enters the target and executes it inline before
    returning, unlike :func:`~amrita_sense.instructions.ret2.PUSH_AND_GOTO` /
    :func:`~amrita_sense.instructions.ret2.RET_FAR` which use the return-address
    stack for a far return.

    .. warning::

       The target **must not** be :func:`~amrita_sense.instructions.interrupt.INTERRUPT_INTO`
       or :func:`~amrita_sense.instructions.ret2.PUSH_AND_GOTO`.  Using those
       as a ``CALL`` target will cause undefined behavior because they
       manipulate the context stack and/or return-address stack in ways
       incompatible with single-step call semantics.

    Args:
        alias: The alias of the subroutine to call.

    Returns:
        A :class:`CallNode` that performs a single-step call to the target.
    """
    return CallNode(alias)


def ARCHIVED_NODES(*nodes: BaseNode) -> SubprogramStorage:
    """Archive nodes for single-step call via :func:`CALL`.

    Wraps the given nodes into a :class:`SubprogramStorage` which, when
    extracted, produces a node compose that **jumps over** the archived nodes
    at runtime.  The archived nodes are preserved in the compose graph but
    never executed inline — they are reachable only via
    :meth:`WorkflowInterpreter.call_sub` (i.e. :func:`CALL`).

    This is **not** meant for storing an entire program or function body.
    Typically you archive a **single node** (or a very short sequence) as a
    reusable subroutine target.  For defining full function bodies or
    interrupt service routines, use :func:`ARCHIVED_SEGMENT` instead.

    Args:
        *nodes: The instruction nodes to archive (usually a single node).

    Returns:
        A :class:`SubprogramStorage` that wraps the archived nodes.
    """
    return SubprogramStorage(*nodes)


def ARCHIVED_SEGMENT(seg: NodeCompose | SelfCompileInstruction) -> NodeCompose:
    """Define a segment of nodes that is **skipped** at runtime.

    Wraps ``seg`` between a jump and a :func:`~amrita_sense.instructions.workfl_ctrl.NOP`,
    so the interpreter skips over the entire segment during normal execution.
    The segment remains in the compose graph and is reachable only via
    explicit jumps — this is the standard way to define **Functions** (the
    target of :func:`~amrita_sense.instructions.ret2.PUSH_AND_GOTO`) or
    **interrupt service routines**.

    Args:
        seg: The node compose or self-compiling instruction to archive.

    Returns:
        A :class:`NodeCompose` that skips over ``seg`` at runtime.
    """
    if isinstance(seg, SelfCompileInstruction):
        seg = seg.extract()

    @Node(BuiltinTags.ARCHIVED_SEGMENT, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        pc.jump_offset(2)  # [JMP 2, Payload, NOP] JMP 2->NOP

    return call >> seg >> NOP
