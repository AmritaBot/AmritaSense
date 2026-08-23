from amrita_sense.exceptions import IllegalState
from amrita_sense.instructions.enum import BuiltinTags
from amrita_sense.node import NodeType
from amrita_sense.node.core import NodeComposeRendered
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.types import InterpreterContext
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


def PUSH_CONTEXT(
    alias_or_idata: str | list[int] | None,
    *,
    exclude_deps: bool = True,
    exclude_stack: bool = True,
) -> NodeType[None]:
    """Create a workflow node that saves the current interpreter state.

    This instruction snapshots the interpreter context (pointer, exception ignore
    list, and optionally dependency args and return-address stack) onto the
    context stack.  The saved context's pointer is set to the given
    ``alias_or_idata`` address so that when the context is later restored (via
    :func:`INTERRUPT_RET` or :meth:`~amrita_sense.runtime.workflow.WorkflowInterpreter.rebase_context`),
    execution resumes at that address — i.e. it serves as the **return address**,
    not a jump target.

    This is the low-level primitive — unlike :func:`INTERRUPT_INTO`, it does
    **not** perform any jump, does **not** set ``if_flag``, and does **not**
    guard against being called inside an IF branch.

    To restore the saved context and return, pair this with :func:`INTERRUPT_RET`
    (auto-restore) or pop manually and call
    :meth:`~amrita_sense.runtime.workflow.WorkflowInterpreter.rebase_context`.

    Args:
        alias_or_idata: Alias (str, resolved at runtime) or absolute
            address vector (list[int]) to save as the **return address** in the
            context snapshot.  When the context is later restored, execution will
            resume at this address.  If ``None``, defaults to the top of the
            **return-address stack** (i.e. the current instruction's return
            address).  Since :func:`INTERRUPT_RET` does **not** set the jump flag
            when restoring, the interpreter will naturally advance to the next
            instruction (return-address + 1) after the restore.
        exclude_deps: If True (default), dependency args/kwargs are excluded
            from the snapshot.
        exclude_stack: If True (default), the return-address stack is excluded
            from the snapshot.

    Returns:
        A workflow node that pushes an
        :class:`~amrita_sense.runtime.types.InterpreterContext` onto the
        context stack (without performing any jump).
    """
    addr: list[int] | None = None

    @Node(BuiltinTags.PUSH_CONTEXT, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        nonlocal addr

        dump = pc.dump_interpreter(
            exclude_deps=exclude_deps, exclude_stack=exclude_stack
        )
        if addr is None:
            addr = pc._ret_addr_stack.stack[-1].base_addr.copy()
        dump.ptr = PointerVector(addr)
        pc._context_stack.push(dump)

    def _post_compile(compose: NodeComposeRendered):
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

    call._post_compile = _post_compile

    return call


def POP_CONTEXT() -> NodeType[InterpreterContext]:
    """Create a workflow node that pops the most recently saved interpreter state.

    Pops the top :class:`~amrita_sense.runtime.types.InterpreterContext` from the
    context stack and returns it as the node result.

    .. warning::

       In the ``>>`` chain, a node's return value is sent to the
       interpreter's step-by-step generator — it does **not** automatically
       flow into the next node's arguments.  To inspect or rebase the popped
       context, either:

       * Use :func:`INTERRUPT_RET` which pops and auto-restores.
       * Use a ``CALL`` / ``pc.call_sub`` to invoke a subroutine that receives
         the value via dependency injection.
       * Pop manually via ``pc.context_stack.pop()`` inside a ``@Node`` function.

    Returns:
        A workflow node that returns the popped
        :class:`~amrita_sense.runtime.types.InterpreterContext`.
    """

    @Node(BuiltinTags.POP_CONTEXT, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> InterpreterContext:
        return pc.context_stack.pop()

    return call


def INTERRUPT_INTO(
    jump_to: str | list[int],
    ret_to: str | list[int] | None = None,
    if_state: bool = False,
) -> NodeType[None]:
    """Create a workflow node that performs an interrupt-style jump.

    Saves the current interpreter state (pointer, exception-ignore list,
    dependency args, return-address stack) and jumps to ``jump_to``, but
    **overwrites the saved pointer with ``ret_to``** so that when
    :func:`INTERRUPT_RET` restores the context, execution resumes at
    ``ret_to`` — not at the original pre-jump position.

    This mirrors real CPU interrupt semantics: the return address is
    the instruction where execution should resume after the handler
    returns, not the interrupted instruction itself.

    Since :func:`INTERRUPT_RET` uses
    :meth:`~amrita_sense.runtime.workflow.WorkflowInterpreter.rebase_context`
    which does **not** set the jump flag, after restoring the context the
    interpreter will naturally advance to the next instruction
    (return-address + 1).

    Additionally sets ``pc.if_flag = if_state``. While ``if_flag`` is
    ``True``, nested ``INTERRUPT_INTO`` is forbidden (raises
    :class:`IllegalState`).

    Args:
        jump_to: Alias or absolute address to jump to **now** (the handler).
        ret_to: Alias or absolute address saved as the **return address** in
            the context snapshot.  When :func:`INTERRUPT_RET` restores the
            context, execution resumes here (and then advances to the next
            instruction, since no jump flag is set).  If ``None``, defaults to
            the top of the **return-address stack** (i.e. the current
            instruction's return address).
        if_state: Value for ``pc.if_flag`` after the jump (default ``False``).

    Returns:
        A workflow node that snapshots context (with overridden return
        pointer), sets ``if_flag``, and jumps.

    Raises:
        IllegalState: If ``pc.if_flag`` is already ``True``.
    """
    jmp_addr: list[int] | None = None
    ret_addr: list[int] | None = None

    @Node(BuiltinTags.INTERRUPT_INTO, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        nonlocal jmp_addr, ret_addr
        if pc.if_flag:
            raise IllegalState("Interrupt into is not allowed in IF statement")
        pc.if_flag = if_state

        # Resolve lazily, cache once
        assert jmp_addr is not None
        if ret_addr is None:
            # None default: reuse parent's return addr (inside call_sub) or current pointer.
            if pc.outer_interpreting:
                ret_addr = pc._ret_addr_stack.stack[-1].base_addr.copy()
            else:
                ret_addr = pc._pointer.base_addr.copy()

        ctx: InterpreterContext = pc.dump_interpreter()
        ctx.ptr = PointerVector(ret_addr)  # override: return here after IRET
        pc.context_stack.push(ctx)
        pc.jump_to(jmp_addr)

    def _post_compile(compose: NodeComposeRendered):
        nonlocal jmp_addr, ret_addr
        if jmp_addr is not None:
            raise RuntimeError(
                f"{call.tag} node has already been compiled; "
                "a compose-bound node can only be compiled once"
            )
        jmp_addr = (
            compose.calc.resolve_alias(jump_to) if isinstance(jump_to, str) else jump_to
        )
        if ret_to is not None:
            ret_addr = (
                compose.calc.resolve_alias(ret_to)
                if isinstance(ret_to, str)
                else ret_to
            )

    call._post_compile = _post_compile

    return call


def INTERRUPT_RET(reset_mark: bool = True) -> NodeType[None]:
    """Create a workflow node that returns from a previous interrupt-into jump.

    Pops the top interpreter context from the context stack (which was saved by
    :func:`INTERRUPT_INTO` or :func:`PUSH_CONTEXT`) and **reapplies** it via
    :meth:`WorkflowInterpreter.rebase_context`.  This restores the pointer,
    exception ignore list, dependency args, and return-address stack to their
    pre-interrupt state.  The ``if_flag`` is also reset to ``False``.

    Returns:
        A workflow node that restores the interpreter state and clears the ``if_flag``.
    """

    @Node(BuiltinTags.INTERRUPT_RET, wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        pc.rebase_context(pc.context_stack.pop())
        if reset_mark:
            pc.if_flag = False

    return call
