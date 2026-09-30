from amrita_sense.instructions.enum import BuiltinTags
from amrita_sense.node import NodeType
from amrita_sense.node.abc_base import AbstractCompose
from amrita_sense.node.addressing import AddressCalculator
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


def RET() -> NodeType[None]:
    """Pop the return-address stack and resume execution at the saved address.

    This instruction pops the top of the return-address stack (typically pushed
    by :func:`CALL` or :func:`PUSH_RET`) and restores the
    interpreter's pointer via :meth:`~amrita_sense.runtime.workflow.WorkflowInterpreter.rebase_ptr`.
    The return-address stack is usually used for returning from subprograms
    (node compositions).

    .. note::

       This instruction uses `rebase_ptr` rather than `jump_to` — it does
       **not** set the jump flag.  Therefore, after the return, the interpreter
       will naturally advance to the next instruction (return-address + 1).

       Callers should push `target - 1` so that `advance_pointer` lands on
       the actual target node.

    Returns:
        A workflow node that pops the return-address stack and resumes execution.
    """

    @Node(BuiltinTags.RET, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        ptr = pc._ret_addr_stack.pop()
        pc.rebase_ptr(ptr.base_addr)

    call.__sdb_dis__ = "RET"
    call.__sdb_cmt__ = "return from subroutine"

    return call


def PUSH_RET(alias_or_idata: str | list[int]) -> NodeType[None]:
    """Push an address to the return address stack.

    This instruction push an address to the return address stack. The address can be an alias or an idata.

    Args:
        alias_or_idata (str | list[int]): The alias or idata to push.

    Returns:
        NodeType[None]: A node representing the PUSH_RET instruction.
    """
    addr: list[int] | None = None

    @Node(BuiltinTags.PUSH_RET, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        assert addr is not None
        pc._ret_addr_stack.push(PointerVector(addr))

    def _post_compile(compose: AbstractCompose[AddressCalculator]):
        nonlocal addr
        if addr is not None:
            raise RuntimeError(
                f"{call.tag} node has already been compiled; "
                "a compose-bound node can only be compiled once"
            )
        if isinstance(alias_or_idata, str):
            addr = compose.calc.resolve_alias(alias_or_idata)
        else:
            addr = alias_or_idata

        call.__sdb_dis__ = f"PUSH {addr}"
        call.__sdb_cmt__ = "push return address"

    call._post_compile = _post_compile

    return call


def CALL(
    to_adr: str | list[int], *, from_adr: str | list[int] | None = None
) -> NodeType[None]:
    """Push a return address and jump to another address.

    This instruction pushes a return address onto the return-address stack and
    then jumps to `to_adr`.  When the target routine later executes
    :func:`RET`, it will pop this return address and resume execution there.

    Args:
        to_adr: The alias or absolute address to **jump to** now.
        from_adr: The **return address** (alias or absolute address vector) to
            push onto the return-address stack.  This is where execution should
            resume after :func:`RET`.  If `None`, defaults to the top of
            the **return-address stack** (i.e. the current instruction's return
            address).

    Returns:
        A workflow node that pushes the return address and jumps.
    """
    frm_addr: list[int] | None = None
    to_addr: list[int] | None = None

    @Node(BuiltinTags.CALL, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        nonlocal frm_addr, to_addr
        assert to_addr is not None
        if frm_addr is None:
            #  None default: reuse parent's return addr (inside call_sub) or current pointer.
            if pc.outer_interpreting:
                frm_addr = pc._ret_addr_stack.stack[-1].base_addr.copy()
            else:
                frm_addr = pc._pointer.base_addr.copy()
        pc._ret_addr_stack.push(PointerVector(frm_addr))
        pc.jump_to(to_addr)

    def _post_compile(compose: AbstractCompose[AddressCalculator]):
        nonlocal frm_addr, to_addr
        if frm_addr is not None or to_addr is not None:
            raise RuntimeError(
                f"{call.tag} node has already been compiled; "
                "a compose-bound node can only be compiled once"
            )
        if isinstance(from_adr, str):
            frm_addr = compose.calc.resolve_alias(from_adr)
        else:
            frm_addr = from_adr
        if isinstance(to_adr, str):
            to_addr = compose.calc.resolve_alias(to_adr)
        else:
            to_addr = to_adr

        call.__sdb_dis__ = (
            f"CALL {to_addr}, ret={frm_addr if frm_addr is not None else '?'}"
        )
        call.__sdb_cmt__ = "push return address and jump"

    call._post_compile = _post_compile

    return call


# Deprecated names (renamed in 1.0.0): plain aliases so deep import paths keep working.  The static `@deprecated` markers live in `_deprecated`.
RET_FAR = RET
PUSH_STACK = PUSH_RET


def PUSH_AND_GOTO(
    from_adr: str | list[int] | None, to_adr: str | list[int]
) -> NodeType[None]:
    """Deprecated alias of :func:`CALL` — the argument order changed in 1.0.0."""
    return CALL(to_adr, from_adr=from_adr)
