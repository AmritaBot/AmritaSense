"""REPL inspection helpers ― read-only state introspection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from amrita_sense.node.core import BaseNode, NodeComposeRendered

if TYPE_CHECKING:
    from amrita_sense.runtime.workflow import WorkflowInterpreter


# Helpers


def _current_node(inter: WorkflowInterpreter) -> BaseNode | None:
    """Return the node at the current pointer, or *None*."""
    graph = inter.get_graph()
    node = graph.calc.find_addr_safe(inter._pointer.base_addr)
    return node if isinstance(node, BaseNode) else None


def _fmt_ptr(inter: WorkflowInterpreter) -> str:
    return str(inter._pointer.base_addr)


def _walk_graph(
    graph: NodeComposeRendered, prefix: list[int] | None = None
) -> list[tuple[list[int], BaseNode]]:
    """Flatten the graph into (address, BaseNode) pairs (DFS)."""
    result: list[tuple[list[int], BaseNode]] = []
    if prefix is None:
        prefix = []
    for idx, item in enumerate(graph._graph):
        addr = [*prefix, idx]
        if isinstance(item, BaseNode):
            result.append((addr, item))
        elif isinstance(item, NodeComposeRendered):
            result.extend(_walk_graph(item, addr))
    return result


# Public API


def where(inter: WorkflowInterpreter) -> None:
    """Print a one-line summary of the interpreter's current location.

    Example output::

        📍 [0, 1]  NodeSuspend::always_fail  stack_depth=3
    """
    node = _current_node(inter)
    node_str = node.tag if node else "<INVALID>"
    depth = len(inter._ret_addr_stack)
    print(
        f"📍 [{', '.join(map(str, inter._pointer.base_addr))}]  {node_str}  stack_depth={depth}"
    )


def inspect(inter: WorkflowInterpreter) -> None:
    """Pretty-print the full interpreter state.

    Shows the current pointer, node, stacks, panic exception, and
    position in the interpreter tree.
    """
    node = _current_node(inter)
    exc = inter.get_exception()

    print("═" * 58)
    print(f"🆔  Interpreter: {inter.id[:12]}…")
    if inter.parent is not None:
        print(f"👆 Parent:       {inter.parent.id[:12]}…")
    if inter.top_interpreter is not inter:
        print(f"🌳 Root:         {inter.top_interpreter.id[:12]}…")

    print(f"📍 Pointer:      {_fmt_ptr(inter)}")
    if node is not None:
        print(f"🔍 Node:         {node.tag}")
        print(f"   Function:     {node.func.__name__}")
    else:
        print("🔍 Node:         <INVALID>")

    print(f"🏃 Running:      {'yes' if inter.is_running else 'no'}")
    print(f"🚩 Pending stop: {'yes' if inter.pending_stop else 'no'}")

    # Return address stack
    rs = inter._ret_addr_stack
    print(f"📚 Return stack: depth={len(rs)}")
    if rs:
        for i, ptr in enumerate(reversed(rs.stack)):
            print(f"   [{len(rs) - 1 - i}] {ptr}")

    # Context stack
    cs = inter._context_stack
    print(f"📦 Context stack: depth={len(cs)}")
    if cs:
        for i, ctx in enumerate(reversed(cs.stack)):
            print(
                f"   [{len(cs) - 1 - i}] ptr={ctx.ptr}  exc={type(ctx.exception).__name__ if ctx.exception else None}"
            )

    # Panic
    if exc is not None:
        print(f"⚠️  Panic:        {type(exc).__name__}: {exc}")
    else:
        print("⚠️  Panic:        (none)")

    # Sub interpreters
    subs = inter.sub_interpreters
    print(f"👶 Sub-interpreters: {len(subs)}")
    for sid, sub in subs.items():
        marker = "🟢" if sub.is_running else "⏸️"
        print(f"   {marker} {sid[:12]}…  ptr={_fmt_ptr(sub)}")

    print("═" * 58)


def backtrace(inter: WorkflowInterpreter) -> None:
    """Print the full call chain of the interpreter tree.

    Shows the interpreter chain (root → … → current), the return
    address stack, and the context stack.
    """
    # Build interpreter chain
    chain: list[tuple[str, int]] = []
    cur: WorkflowInterpreter | None = inter
    while cur is not None:
        label = cur.id
        if cur is inter:
            label += " [Current]"
        if cur.top_interpreter is cur:
            label += " [Root]"
        chain.append((label, id(cur)))
        cur = cur.parent

    for intp_id, ident in reversed(chain):
        print(f"Interpreter → {intp_id} at 0x{ident:x}")
    print()

    # Return stack
    print("Returning Stack:")
    rs = inter._ret_addr_stack.copy()
    for i in range(len(rs.stack)):
        print(f"    {i}. {rs.stack[i]}")
    print(f"    {len(rs.stack)}. {inter._pointer} (Current)")
    print()

    # Context stack
    print("Context Stack:")
    if inter._context_stack:
        for i, ctx in enumerate(inter._context_stack.stack):
            print(f"    {i}. {ctx.ptr}")
    else:
        print("    (EMPTY_STACK)")
    print()

    # Node
    node = _current_node(inter)
    if node is not None:
        print(f"Current node: {node.tag} -> {node.func.__name__}")
    else:
        print("Current node: <INVALID>")


def list_nodes(inter: WorkflowInterpreter) -> None:
    """Print every node in the workflow graph with its address and tag.

    Like ``dis.dis()`` for AmritaSense workflows.
    """
    graph = inter.get_graph()
    nodes = _walk_graph(graph)
    if not nodes:
        print("(empty graph)")
        return
    for addr, node in nodes:
        addr_str = "[" + ", ".join(map(str, addr)) + "]"
        print(f"  {addr_str:>12s}  {node.tag:<40s}  {node.func.__name__}")


def list_sub_intp(inter: WorkflowInterpreter, indent: int = 0) -> None:
    """Print the sub-interpreter tree rooted at *inter*.

    Each line shows the interpreter id, running status, current pointer,
    and panic exception (if any).
    """

    def _show(ip: WorkflowInterpreter, depth: int) -> None:
        prefix = "  " * depth
        marker = "🟢" if ip.is_running else "⏸️"
        exc = ip.get_exception()
        parts = [
            f"{prefix}{marker} {ip.id[:12]}…",
            f"ptr={_fmt_ptr(ip)}",
        ]
        if exc is not None:
            parts.append(f"exc={type(exc).__name__}")
        print("  ".join(parts))
        for child in ip.sub_interpreters.values():
            _show(child, depth + 1)

    _show(inter, indent)
