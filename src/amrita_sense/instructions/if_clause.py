import inspect
from abc import ABC
from collections.abc import Callable
from types import FrameType
from typing import Any, TypeAlias

from typing_extensions import Self

from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.workflow import WorkflowPC


class Condition(ABC):
    condition: Node[bool]
    do: BaseNode


class IFClause(SelfCompileInstruction, Condition):
    """IF Clause
    Usage:
        ```python
        IF(CONDITION,PAYLOAD)
        IF(CONDITION,PAYLOAD).ELSE(ELSE_PAYLOAD)
        IF(CONDITION,PAYLOAD).ELIF(ELIF_CONDITION,ELIF_PAYLOAD).ELSE(ELSE_PAYLOAD)
        ```
    """

    def __init__(self, condition: Node[bool], do: BaseNode):
        self.condition = condition
        self.do = do

    def extract(self) -> NodeCompose:
        return NodeCompose(
            ConditionJumpNode(
                condition_offset=1,
                do_offset=2,
                false_offset=3,
                then_addr=3,
            ),
            self.condition,
            self.do,
            NOP,
        )

    @property
    def ELIF(self) -> Callable[[Node, Node], "ELIFClause"]:
        return lambda condition, node: ELIFClause(self, condition, node)

    @property
    def ELSE(self) -> Callable[[Node], "ELSEClause"]:
        return lambda node: ELSEClause(self, node)


class NestedELIFClause(Condition):
    parent: "ELIFClause"

    def __init__(self, if_clause: "ELIFClause", condition: Node[bool], do: Node):
        self.condition = condition
        self.do = do
        self.parent = if_clause


class ELIFClause(Condition):
    parent: IFClause
    _elif_compose: list[NestedELIFClause]

    def __init__(self, if_clause: IFClause, condition: Node[bool], do: Node):
        self.condition = condition
        self.do = do
        self.parent = if_clause
        self._elif_compose = []

    @property
    def ELIF(self) -> Callable[[Node, Node], Self]:
        def _elif(condition, do):
            self._elif_compose.append(NestedELIFClause(self, condition, do))
            return self

        return _elif

    @property
    def ELSE(self) -> Callable[[Node | None], "ELSEClause"]:
        return lambda node=None: ELSEClause(self, node or NOP)


class ConditionJumpNode(BaseNode):
    """IF/ELIF Condition Jump chain node
    IF >> CONDI(_condition_offset) >> DO(_do_offset) >> ... (length: 3)
    IF >> CONDI(_condition_offset) >> DO(_do_offset) >> IF(_false_offset2) >> CONDI(_condition_offset2) >> DO(_do_offset2) >> ... (length: 3*n); This is ELIF Chain

    Uses call_offset for intra-chunk relative addressing (e.g., CONDITION and DO),
    and call_near for cross-chunk absolute addressing within the same scope.
    """

    _condition_offset: int
    _do_offset: int
    _then_addr: int
    _false_offset: int
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature

    __slots__ = (
        "_condition_offset",
        "_do_offset",
        "_false_offset",
        "_then_addr",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(
        self, condition_offset: int, do_offset: int, false_offset: int, then_addr: int
    ):
        """Constructor

        Args:
            condition_offset (int): The relative offset of condition node within current chunk.
            do_offset (int): The relative offset of payload condition within current chunk.
            then_addr (int): The absolute address of then node (will jump to using call_near).
        """
        frame = inspect.currentframe()
        if not frame:
            raise RuntimeError("No frame found")
        super()._init(
            self._do, tag=None, wrap_to_async=True, address_able=True, frame=frame
        )

        self._condition_offset = condition_offset
        self._do_offset = do_offset
        self._then_addr = then_addr
        self._false_offset = false_offset

    async def _do(self, pc: WorkflowPC):
        if await pc.call_offset(
            self._condition_offset
        ):  # CALL CONDITION (intra-chunk relative)
            await pc.call_offset(self._do_offset)  # CALL DO (intra-chunk relative)
            pc.jump_near(
                self._then_addr
            )  # JMP THEN using absolute address within scope
        else:
            pc.jump_offset(self._false_offset)  # JMP OFFSET FALSE_FORK (relative)

    def __call__(self, pc: WorkflowPC):
        return self._do(pc)


class ELSENode(BaseNode):
    """ELSE node
    ELSE >> DO(_do_offset) >> NOP(_then_offset)

    Uses call_offset for intra-chunk relative addressing and jump_offset for direct jump to NOP.
    """

    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature
    _do_offset: int
    _then_offset: int

    __slots__ = (
        "_do_offset",
        "_then_offset",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(self, do_offset: int, then_offset: int):
        super()._init(
            self._else_worker, tag=None, wrap_to_async=True, address_able=True
        )
        self._do_offset = do_offset
        self._then_offset = then_offset

    async def _else_worker(self, pc: WorkflowPC):
        await pc.call_offset(self._do_offset)  # CALL DO (intra-chunk relative)
        pc.jump_offset(self._then_offset)  # JMP directly to NOP

    def __call__(self, pc: WorkflowPC):
        return self._else_worker(pc)


CONDITION_CHAIN: TypeAlias = tuple[ConditionJumpNode, Node, Node]
ELSE_TUPLE: TypeAlias = tuple[ELSENode, Node]


class ELSEClause(SelfCompileInstruction, Condition):
    top: IFClause
    parent: ELIFClause | IFClause

    def __init__(self, parent: ELIFClause | IFClause, do: Node):
        self.do = do
        self.parent = parent
        self.top = parent if isinstance(parent, IFClause) else parent.parent

    def extract(self) -> NodeCompose:
        top_if = self.top
        parent = self.parent

        # Base IF clause
        compose_chunk = [
            ConditionJumpNode(
                condition_offset=1, do_offset=2, false_offset=3, then_addr=0
            ),
            top_if.condition,
            top_if.do,
        ]

        if parent is top_if:
            # Simple IF-ELSE case
            then_addr = 5
            compose_chunk[0] = ConditionJumpNode(
                condition_offset=1, do_offset=2, false_offset=3, then_addr=then_addr
            )
            compose_chunk.extend(
                [
                    ELSENode(
                        do_offset=1, then_offset=2
                    ),  # then_addr=2 points to NOP within ELSE chunk
                    self.do,
                    NOP,
                ]
            )
        elif isinstance(parent, ELIFClause):
            # IF-ELIF-ELSE case
            base_addr = len(compose_chunk)  # 3

            # Calculate total length to determine then_addr for NOP
            total_length = (
                base_addr  # Basic IF clause (3)
                + 3  # Main ELIF clause (3)
                + len(parent._elif_compose) * 3  # Nested ELIF chains (each 3 elements)
                + 3  # ELSE chunk (3 elements)
            )
            then_addr = (
                total_length - 1
            )  # Absolute address of NOP within the entire scope

            # Update main IF clause
            compose_chunk[0] = ConditionJumpNode(
                condition_offset=1, do_offset=2, false_offset=3, then_addr=then_addr
            )

            # Main ELIF clause
            elif_clause_nodes = [
                ConditionJumpNode(
                    condition_offset=1, do_offset=2, false_offset=3, then_addr=then_addr
                ),
                parent.condition,
                parent.do,
            ]

            # ELIF chain
            elif_chains_nodes = []
            for i in parent._elif_compose:
                elif_chains_nodes.extend(
                    [
                        ConditionJumpNode(
                            condition_offset=1,
                            do_offset=2,
                            false_offset=3,
                            then_addr=then_addr,
                        ),
                        i.condition,
                        i.do,
                    ]
                )

            # ELSE chunk - then_addr=2 points to NOP within ELSE chunk (relative addressing)
            else_chunk = [
                ELSENode(do_offset=1, then_offset=2),
                self.do,
                NOP,
            ]

            compose_chunk.extend(elif_clause_nodes)
            compose_chunk.extend(elif_chains_nodes)
            compose_chunk.extend(else_chunk)

        return NodeCompose(*compose_chunk)


def IF(condition: Node[bool], do: BaseNode) -> IFClause:
    """If condition

    Args:
        condition (Node): Condition node
        do (Node): Payload

    Returns:
        IFClause: If Clause

    Examples:
        ```python
        IF(CONDITION,PAYLOAD)
        IF(CONDITION,PAYLOAD).ELSE(ELSE_PAYLOAD)
        IF(CONDITION,PAYLOAD).ELIF(ELIF_CONDITION,ELIF_PAYLOAD).ELSE(ELSE_PAYLOAD)
        ```
    """
    return IFClause(condition, do)
