# 4.4 External Interrupt Calls

AmritaSense provides a safe external invocation mechanism that allows **external systems to inject subroutines at node boundaries**, enabling flexible debugging, monitoring, and dynamic control. The core of this mechanism is the interpreter lock and `call_sub(interrupt=True)`, which turns "interrupts" from hardware-level preemption into controllable, programmable "safe external calls."

> **Distinction: Flow Suspend vs. External Call**
> The flow suspension (Suspend) introduced in Section 3.4 pauses the execution flow via `SuspendObjectStream`, waiting for external `resume()` before continuing. This section discusses **actively injecting a complete subroutine from the outside** during the suspend window or at node boundaries, which automatically returns after execution. The two can be combined, but they belong to different capability dimensions.

## 4.4.1 Interpreter Lock and Safe External Call Principles

The core of external injection operations is `aiologic.Lock` (the interpreter lock), which ensures atomicity of the injection and avoids race conditions with the normal execution flow.

### Why is a lock needed?

The interpreter's main loop acquires the lock to execute a node on each iteration and releases it after the node completes. Between two iterations, the lock is idle, allowing external systems to safely call `call_sub(interrupt=True)` to inject a subroutine. This call re-acquires the lock, guaranteeing:

- The injected subroutine will not execute concurrently with normal nodes
- Workflow internal state will not be concurrently tampered with
- Multiple external injection requests are serialized

### Safe external call interface

External systems call directly through the interpreter object:

```python
# Assuming interpreter is a WorkflowInterpreter instance
await interpreter.call_sub(
    interpreter.get_graph().calc.resolve_alias("my_handler"),
    interrupt=True,
    some_arg="value"
)
```

The key is `interrupt=True`, which tells the interpreter to acquire the interpreter lock during the call, achieving safe injection.

### Inside workflow vs. outside workflow

- Calls to `call_sub` from **within a node** must use `interrupt=False` (default), otherwise `aiologic` will detect and raise an exception because the same coroutine tries to re-acquire the same non-reentrant lock.
- **External systems** (such as another coroutine, debugger, or HTTP interface) must use `interrupt=True` because they do not hold the lock.

This design allows the same `call_sub` API to serve both internal reuse and external injection, distinguished by a single boolean parameter.

## 4.4.2 Interrupt Program Storage Structure

To facilitate external calls, we need to pre-place dedicated node sequences in the workflow that respond to interrupts. These sequences are packaged as "interrupt programs" and stored in the workflow — normal flow skips them. AmritaSense provides `ARCHIVED_NODES` to construct such storage areas.

### `ARCHIVED_NODES` structure

`ARCHIVED_NODES` is a self-compiling instruction that takes a series of nodes (usually marked with `ALIAS` to support `CALL` addressing) and automatically generates the following structure:

```text
SubprogramJumpNode -> ALIAS(node1, "name1") -> ALIAS(node2, "name2") -> ... -> NOP
```

- `SubprogramJumpNode` unconditionally jumps to the trailing `NOP`, so the entire storage area is skipped during normal execution.
- Each node can be addressed by alias, allowing any one of them to be called on demand.

### Example

```python
from amrita_sense.instructions.subprogram import ARCHIVED_NODES
from amrita_sense.instructions.alias import ALIAS
from amrita_sense.node import Node

@Node()
def on_error(pc: WorkflowInterpreter):
    print("Handling error...")

@Node()
def cleanup(pc: WorkflowInterpreter):
    print("Cleaning up...")

interrupt_handlers = ARCHIVED_NODES(
    ALIAS(on_error, "on_error"),
    ALIAS(cleanup, "cleanup")
)
```

Place `interrupt_handlers` at the end or in a suitable position within the workflow composition.

## 4.4.3 SubprogramJumpNode Execution Logic

`SubprogramJumpNode` is a lightweight node specifically designed to skip the subsequent storage area. Its implementation is very simple:

- Holds a target jump address `_target_near`, typically pointing to the `NOP` at the end of the storage area.
- When executed, calls `pc.jump_near(self._target_near)`, making the interpreter jump directly to the target without executing the intermediate `ALIAS` nodes.

It has `address_able=True` and can be aliased (though usually not needed). This design makes the storage area completely transparent to the normal execution flow but fully open to address resolution (via alias lookup).

### Why not use GOTO?

`SubprogramJumpNode` is specifically designed for skipping storage areas, with clearer semantics. `GOTO` is a general-purpose jump instruction that could be misused. Using a dedicated jump node reduces the risk of developer confusion.

## 4.4.4 Building a Safe Injectable Node Library

Using the mechanisms described above, developers can build an "injectable node library" for debugging, health checks, error recovery, and more. These library nodes must follow certain safety constraints.

### Node design principles

1. **No shared state**: Nodes should be pure functions, or only depend on dependency-injected context, without modifying global state.
2. **Idempotency**: External calls may occur at any time; node logic should be as idempotent as possible, producing consistent results across multiple invocations.
3. **Fast execution**: Injected nodes are typically lightweight — avoid holding the interpreter lock for long periods, which would block the normal flow.
4. **Explicit exception handling**: Catch and handle possible exceptions within the node to prevent the injection operation itself from crashing the workflow. For fatal errors, terminate the workflow via `InterruptNotice`.

### Example: Health check node

```python
@Node()
async def health_check(pc: WorkflowInterpreter):
    # Read-only operation, inspect internal state
    graph = pc.get_graph()
    addr = pc._pointer.copy()
    print(f"Current pointer: {addr}, graph size: {len(graph._graph)}")
    # No state modified — safe
```

### External invocation pattern

An external system (such as a debugger) can inject like this:

```python
# First ensure the workflow is suspended at a checkpoint or node boundary
await pc.object_io.wait_to_suspend(PC_CHECKPOINT)
# Now the lock is free — safe to inject
await pc.call_sub(pc.get_graph().calc.resolve_alias("health_check"), interrupt=True)
# After injection completes, resume the workflow
pc.object_io.resume()
```

Or, while the workflow is running, call `call_sub(interrupt=True)` from another coroutine. As long as the lock is free (i.e., not during node execution), the call will wait for the lock, then execute the injection.

### Concurrency safety

`aiologic.Lock` ensures only one injection executes at a time. Multiple external callers will queue without nested injection. The interpreter's internal state remains stable under lock protection.

Through this mechanism, AmritaSense transforms external intervention from "disruptive interrupts" into "safe function calls," providing a solid foundation for building full-featured debuggers, monitoring systems, and dynamic flow control.

## 4.4.5 Interrupt Routines & Context Snapshots (v0.4.x+)

AmritaSense v0.4.x+ provides built-in instructions for interrupt-style control transfer **within** a workflow: `INTERRUPT_INTO` / `INTERRUPT_RET`. Unlike `call_sub(interrupt=True)` which injects code from **outside** the interpreter, these instructions are placed directly in the `>>` chain and perform:

1. Save complete interpreter state → `InterpreterContext`
2. Jump to a handler routine (e.g., stored in `ARCHIVED_NODES`)
3. Restore state and return

This is useful for:

- Error recovery subroutines that need full context
- Debugging breakpoints with state inspection
- Nested interrupt handling (LIFO context stack)

**External vs Internal**: `call_sub(interrupt=True)` is externally driven (debugger, HTTP endpoint); `INTERRUPT_INTO`/`INTERRUPT_RET` are internally orchestrated in the `>>` chain. Both mechanisms are complementary and can be composed.

For complete examples and patterns, see [Interrupt Routine & Return](/guide/practice/interrupt-routine).

::: tip REPL Debugger
Building on the external invocation mechanism and interrupt infrastructure, AmritaSense v0.5.0 provides a complete REPL debugger module `amrita_sense.debugger`, wrapping step execution, breakpoint management, and state inspection into synchronous functions — no manual `run_step_by()` loops required. See [REPL Debugging](/guide/practice/repl-debugging) for details.
:::
