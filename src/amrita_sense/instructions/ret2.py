from amrita_sense.node import NodeType
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


def RET_FAR() -> NodeType[None]:
    """Return from the current address.

    This instruction jump out the current bubble. This instruction will use the last jump address in the return address stack, which is usually used for returning from subprograms (always is node compose).

    Returns:
        NodeType[None]: A node representing the RET_FAR instruction.
    """

    @Node("__RET_FAR__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        ptr = pc._ret_addr_stack.pop()
        pc.jump_far_ptr(ptr.base_addr)

    return call


def PUSH_STACK(alias_or_idata: str | list[int]) -> NodeType[None]:
    """Push an address to the return address stack.

    This instruction push an address to the return address stack. The address can be an alias or an idata.

    Args:
        alias_or_idata (str | list[int]): The alias or idata to push.

    Returns:
        NodeType[None]: A node representing the PUSH_STACK instruction.
    """

    @Node("__PUSH_STACK__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        pc._ret_addr_stack.push(
            PointerVector(pc.find_addr_alias(alias_or_idata))
            if isinstance(alias_or_idata, str)
            else PointerVector(alias_or_idata)
        )

    return call


def PUSH_AND_GOTO(from_adr: str | list[int], to_adr: str | list[int]) -> NodeType[None]:
    """Push an address to the return address stack and jump to another address.

    This instruction push an address to the return address stack and jump to another address. The addresses can be aliases or idata.

    Args:
        from_adr (str | list[int]): The alias or idata to push.
        to_adr (str | list[int]): The alias or idata to jump to.

    Returns:
        NodeType[None]: A node representing the PUSH_AND_GOTO instruction.
    """

    @Node("__PUSH_AND_GOTO__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        pc._ret_addr_stack.push(
            PointerVector(pc.find_addr_alias(from_adr))
            if isinstance(from_adr, str)
            else PointerVector(from_adr)
        )
        pc.jump_to(pc.find_addr_alias(to_adr) if isinstance(to_adr, str) else to_adr)

    return call
