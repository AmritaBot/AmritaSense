from amrita_sense.instructions.enum import BuiltinTags
from amrita_sense.node import NodeType
from amrita_sense.node.core import NodeComposeRendered
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


def RET_FAR() -> NodeType[None]:
    """Pop the return-address stack and resume execution at the saved address.

    This instruction pops the top of the return-address stack (typically pushed
    by :func:`PUSH_AND_GOTO` or :func:`PUSH_STACK`) and restores the
    interpreter's pointer via :meth:`~amrita_sense.runtime.workflow.WorkflowInterpreter.rebase_ptr`.
    The return-address stack is usually used for returning from subprograms
    (node compositions).

    .. note::

       This instruction uses ``rebase_ptr`` rather than ``jump_to`` — it does
       **not** set the jump flag.  Therefore, after the return, the interpreter
       will naturally advance to the next instruction (return-address + 1).

       Callers should push ``target - 1`` so that ``advance_pointer`` lands on
       the actual target node.

    Returns:
        A workflow node that pops the return-address stack and resumes execution.
    """

    @Node(BuiltinTags.RET_FAR, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        ptr = pc._ret_addr_stack.pop()
        pc.rebase_ptr(ptr.base_addr)

    return call


def PUSH_STACK(alias_or_idata: str | list[int]) -> NodeType[None]:
    """Push an address to the return address stack.

    This instruction push an address to the return address stack. The address can be an alias or an idata.

    Args:
        alias_or_idata (str | list[int]): The alias or idata to push.

    Returns:
        NodeType[None]: A node representing the PUSH_STACK instruction.
    """
    addr: list[int] | None = None

    @Node(BuiltinTags.PUSH_STACK, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        assert addr is not None
        pc._ret_addr_stack.push(PointerVector(addr))

    def _post_compile(compose: NodeComposeRendered):
        nonlocal addr
        if isinstance(alias_or_idata, str):
            addr = compose.calc.resolve_alias(alias_or_idata)
        else:
            addr = alias_or_idata

    call._post_compile = _post_compile

    return call


def PUSH_AND_GOTO(
    from_adr: str | list[int] | None, to_adr: str | list[int]
) -> NodeType[None]:
    """Push a return address and jump to another address.

    This instruction pushes a return address onto the return-address stack and
    then jumps to ``to_adr``.  When the target routine later executes
    :func:`RET_FAR`, it will pop this return address and resume execution there.

    Args:
        from_adr: The **return address** (alias or absolute address vector) to
            push onto the return-address stack.  This is where execution should
            resume after :func:`RET_FAR`.  If ``None``, defaults to the top of
            the **return-address stack** (i.e. the current instruction's return
            address).
        to_adr: The alias or absolute address to **jump to** now.

    Returns:
        A workflow node that pushes the return address and jumps.
    """
    frm_addr: list[int] | None = None
    to_addr: list[int] | None = None

    @Node(BuiltinTags.PUSH_AND_GOTO, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        nonlocal frm_addr, to_addr
        assert to_addr is not None
        if frm_addr is None and pc.outer_interpreting:
            frm_addr = pc._ret_addr_stack.stack[-1].base_addr.copy()
        else:
            frm_addr = pc._pointer.base_addr.copy()
        pc._ret_addr_stack.push(PointerVector(frm_addr))
        pc.jump_to(to_addr)

    def _post_compile(compose: NodeComposeRendered):
        nonlocal frm_addr, to_addr
        if isinstance(from_adr, str):
            frm_addr = compose.calc.resolve_alias(from_adr)
        else:
            frm_addr = from_adr
        if isinstance(to_adr, str):
            to_addr = compose.calc.resolve_alias(to_adr)
        else:
            to_addr = to_adr

    call._post_compile = _post_compile

    return call
