from amrita_sense.exceptions import IllegalState
from amrita_sense.node import NodeType
from amrita_sense.node.wrapper import Node
from amrita_sense.runtime.types import InterpreterContext
from amrita_sense.runtime.workflow import WorkflowInterpreter


def PUSH_CONTEXT(
    exclude_deps: bool = True, exclude_stack: bool = True
) -> NodeType[None]:
    """Create a workflow node that saves the current interpreter state onto the context stack.

    This is used to snapshot the execution context (pointer, exception ignore list,
    dependency args, return address stack, etc.) before a sub-flow, so it can be
    restored later via :func:`POP_CONTEXT`.  By default the heavy dependency args
    and the full return-address stack are excluded from the snapshot; pass
    ``exclude_deps=False`` and/or ``exclude_stack=False`` to include them.

    Args:
        exclude_deps: If True (default), dependency args/kwargs are excluded from the snapshot.
        exclude_stack: If True (default), the return-address stack is excluded from the snapshot.

    Returns:
        A workflow node that pushes an :class:`~amrita_sense.runtime.types.InterpreterContext`
        onto the interpreter's context stack.
    """

    @Node("__PUSH_CONTEXT__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        pc.context_stack.push(
            pc.dump_interpreter(exclude_deps=exclude_deps, exclude_stack=exclude_stack)
        )

    return call


def POP_CONTEXT() -> NodeType[InterpreterContext]:
    """Create a workflow node that restores the most recently saved interpreter state.

    Pops the top :class:`~amrita_sense.runtime.types.InterpreterContext` from the
    context stack and returns it as the node result.  The caller is responsible for
    passing the context to :meth:`WorkflowInterpreter.rebase_context` if it should
    actually take effect — or it can inspect/serialize the context for other purposes.

    Returns:
        A workflow node that returns the popped :class:`~amrita_sense.runtime.types.InterpreterContext`.
    """

    @Node("__POP_CONTEXT__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> InterpreterContext:
        return pc.context_stack.pop()

    return call


def INTERRUPT_INTO(
    alias_or_idata: str | list[int], if_state: bool = False
) -> NodeType[None]:
    """Create a workflow node that performs an interrupt-style jump to a target address.

    Unlike a normal ``jump_to``, this instruction **snapshots the current interpreter
    state** (via :func:`PUSH_CONTEXT`) before jumping, so the original execution
    context can be restored later with :func:`INTERRUPT_RET`.  It also sets the
    interpreter's ``if_flag``, which controls whether the resumed flow runs in
    interrupt mode.

    The target can be specified as an alias string (resolved at runtime) or a raw
    address vector (resolved at graph-build time).

    Args:
        alias_or_idata: Target node alias (str) or absolute address vector (list[int]).
        if_state: Value to set for the interpreter's ``if_flag`` after the jump.
            Defaults to False.

    Returns:
        A workflow node that snapshots context and jumps to the given address.

    Raises:
        IllegalState: If the interpreter is currently inside an IF branch
            (``pc.if_flag`` is True), because interrupt-into is not allowed there.
    """
    addr: list[int] | None = None

    @Node("__INTERRUPT_INTO__", wrap_to_async=False)
    def call(pc: WorkflowInterpreter) -> None:
        nonlocal addr
        if pc.if_flag:
            raise IllegalState("Interrupt into is not allowed in IF statement")
        pc.if_flag = if_state
        if isinstance(alias_or_idata, str):
            addr = pc.find_addr_alias(alias_or_idata)
        else:
            addr = alias_or_idata
        pc.context_stack.push(pc.dump_interpreter())
        pc.jump_to(addr)

    return call


def INTERRUPT_RET() -> NodeType[None]:
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
        pc.if_flag = False

    return call
