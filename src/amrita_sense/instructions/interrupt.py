from amrita_sense.exceptions import IllegalState
from amrita_sense.node import NodeType
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.types import InterpreterContext
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


def PUSH_CONTEXT(
    alias_or_idata: str | list[int],
    *,
    exclude_deps: bool = True,
    exclude_stack: bool = True,
) -> NodeType[None]:
    """Create a workflow node that saves the current interpreter state and jumps.

    This instruction snapshots the interpreter context (pointer, exception ignore
    list, and optionally dependency args and return-address stack) onto the
    context stack, then **jumps** to the given target address.  This is the
    low-level primitive — unlike :func:`INTERRUPT_INTO`, it does **not** set
    ``if_flag`` and does **not** guard against being called inside an IF branch.

    To restore the saved context and return, pair this with :func:`INTERRUPT_RET`
    (auto-restore) or pop manually and call
    :meth:`~amrita_sense.runtime.workflow.WorkflowInterpreter.rebase_context`.

    Args:
        alias_or_idata: Target alias (str, resolved at runtime) or absolute
            address vector (list[int]) to jump to after saving context.
        exclude_deps: If True (default), dependency args/kwargs are excluded
            from the snapshot.
        exclude_stack: If True (default), the return-address stack is excluded
            from the snapshot.

    Returns:
        A workflow node that pushes an
        :class:`~amrita_sense.runtime.types.InterpreterContext` onto the
        context stack and then jumps to the target address.
    """
    addr: list[int] | None = None

    @Node("__PUSH_CONTEXT__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        nonlocal addr
        if isinstance(alias_or_idata, str):
            addr = pc.find_addr_alias(alias_or_idata)
        else:
            addr = alias_or_idata
        pc.context_stack.push(
            pc.dump_interpreter(exclude_deps=exclude_deps, exclude_stack=exclude_stack)
        )
        pc.jump_to(addr)

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

    @Node("__POP_CONTEXT__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> InterpreterContext:
        return pc.context_stack.pop()

    return call


def INTERRUPT_INTO(
    jump_to: str | list[int],
    ret_to: str | list[int],
    if_state: bool = False,
) -> NodeType[None]:
    """Create a workflow node that performs an interrupt-style jump.

    Saves the current interpreter state (pointer, exception-ignore list,
    dependency args, return-address stack) and jumps to ``jump_to``, but
    **overwrites the saved pointer with ``ret_to``** so that when
    :func:`INTERRUPT_RET` restores the context, execution resumes at
    ``ret_to`` — not at the original pre-jump position.

    This mirrors real CPU interrupt semantics: the return address is
    explicitly the instruction *after* the interrupted one, not the
    interrupted instruction itself.

    Additionally sets ``pc.if_flag = if_state``. While ``if_flag`` is
    ``True``, nested ``INTERRUPT_INTO`` is forbidden (raises
    :class:`IllegalState`).

    Args:
        jump_to: Alias or absolute address to jump to **now** (the handler).
        ret_to: Alias or absolute address saved as the return destination
            inside the context snapshot (:func:`INTERRUPT_RET` will resume here).
        if_state: Value for ``pc.if_flag`` after the jump (default ``False``).

    Returns:
        A workflow node that snapshots context (with overridden return
        pointer), sets ``if_flag``, and jumps.

    Raises:
        IllegalState: If ``pc.if_flag`` is already ``True``.
    """
    jmp_addr: list[int] | None = None
    ret_addr: list[int] | None = None

    @Node("__INTERRUPT_INTO__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        nonlocal jmp_addr, ret_addr
        if pc.if_flag:
            raise IllegalState("Interrupt into is not allowed in IF statement")
        pc.if_flag = if_state

        # Resolve lazily, cache once
        if jmp_addr is None:
            jmp_addr = (
                pc.find_addr_alias(jump_to) if isinstance(jump_to, str) else jump_to
            )
        if ret_addr is None:
            ret_addr = pc.find_addr_alias(ret_to) if isinstance(ret_to, str) else ret_to

        ctx = pc.dump_interpreter()
        ctx.ptr = PointerVector(ret_addr)  # override: return here after IRET
        pc.context_stack.push(ctx)
        pc.jump_to(jmp_addr)

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

    @Node("__INTERRUPT_RET__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        pc.rebase_context(pc.context_stack.pop())
        if reset_mark:
            pc.if_flag = False

    return call
