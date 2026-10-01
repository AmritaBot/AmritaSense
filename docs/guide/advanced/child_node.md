# Calling Subroutines

AmritaSense provides a complete subroutine call mechanism. Unlike `JMP`’s one-way jump, a subroutine call saves the current execution location, jumps to the target node sequence, executes it, and then automatically returns to the original caller. This mechanism serves both the composition-level `INVOKE` instruction and direct interpreter API calls inside node code.

This chapter starts from the interpreter’s low-level API and explains call stack management, argument passing, and how to invoke subroutines in node code.

## 4.3.1 `call_sub`: the interpreter’s low-level call primitive

`call_sub` is a low-level call primitive provided by `WorkflowInterpreter`. Both the composition-level `INVOKE` instruction and node-internal subroutine calls ultimately use it. Its core workflow is:

### Call stack management

1. **Save return address**: push the current execution pointer `_pointer` onto the return address stack `_ret_addr_stack`.
2. **Set new execution context**: replace the execution pointer with the target subroutine entry address.
3. **Execute the subroutine**: call `_call` to start the node execution loop at the target address.
4. **Restore execution context**: after the subroutine completes, the `finally` block pops the original pointer from the return stack and restores it so the interpreter continues from the next node after the call.

### Distinguishing lock and interrupt modes

`call_sub` provides an `interrupt` parameter that controls whether it acquires the interpreter lock:

- `interrupt=False` (default): **does not acquire the lock**. This is suitable for node-internal subroutine calls because the caller node already holds the interpreter lock. Reacquiring it would trigger a deadlock detection in `aiologic` and fail.
- `interrupt=True`: **acquires the interpreter lock**. This is suitable for “safe external calls” initiated by the outside world between iterations, when the lock is free.

This design lets the same call primitive serve both internal reuse and external injection scenarios. The lock acquisition policy defines the appropriate boundary.

### Jump mark priority

After the subroutine completes, `call_sub` checks the `JMP` bit. If the subroutine executed a jump operation such as `JMP`, that bit is set. In that case, the `finally` block **does not restore the original execution pointer** — the new jump target is preserved, and the interpreter continues from there. This ensures subroutine-internal jumps can correctly affect the main workflow control flow.

## 4.3.2 Passing arguments to subroutines

`call_sub` supports passing extra positional and keyword arguments directly. These arguments are merged into the available parameter pool for the subroutine’s entry node during dependency resolution.

### Using `call_sub` with operands inside node code

When developers write subroutine calls inside a custom node, they can pass operands directly:

```python
@Node()
async def caller_node(pc: WorkflowInterpreter):
    result = await pc.call_sub(
        pc.get_graph().calc.resolve_alias("target_sub"),
        "positional_arg",
        custom_kw="value",
    )
    # result is the return value of the subroutine’s final node
```

The called subroutine’s nodes can declare corresponding parameters in their function signatures. Parameter matching is handled by the interpreter’s internal dependency resolution system: positional arguments are matched by index, and keyword arguments are matched by name.

### Triggering a trap from outside

When `call_sub(interrupt=True)` is fired at a running interpreter, the target does not have to be the routine body — it can be a `CALL` node, and that `CALL` enters the routine for you:

```python
import asyncio

from amrita_sense import ALIAS, Node, WorkflowInterpreter
from amrita_sense.instructions import CALL, FN
from amrita_sense.instructions.subprogram import ARCHIVED_NODES
from amrita_sense.runtime.workflow import PC_CHECKPOINT


@Node()
async def trap_point() -> None: ...


@Node()
async def worker_a() -> None: ...


async def main() -> None:
    worker = FN("worker_entry", worker_a)
    traps = ARCHIVED_NODES(ALIAS(CALL("worker_entry"), "trap_entry"))

    comp = trap_point >> traps >> worker
    pc = WorkflowInterpreter(comp.render())

    task = asyncio.create_task(pc.run())
    await pc.object_io.wait_to_suspend(PC_CHECKPOINT)
    await pc.call_sub(
        pc.get_graph().calc.resolve_alias("trap_entry"), interrupt=True
    )
    pc.object_io.resume()
    await task


asyncio.run(main())
```

This is a **trap**: the parked node is consumed by the trap cycle and execution resumes at _parked address + 1_, because `RET` resumes at its saved address **plus one**. See [External Interrupt Calls](/guide/advanced/external_interrupt) for the full stack trace of the trap and a runnable version (`demos/10_call_trap.py`).

### Coordination with Depends

Subroutine nodes can use both operands passed via `call_sub` and dependencies declared via `Depends`. Both sources are unified during dependency resolution. If there is a name conflict between operands and dependencies, operands have higher priority.

::: tip
If a subroutine entry node declares a dependency via `Depends` and that provider returns `None`, the workflow raises an exception and terminates. This is different from an event system where a `None` return might be treated as a “skip.” Node execution is atomic, and failed dependency resolution means the node cannot run.
:::

## 4.3.3 Call stack and return address restoration

The call stack is the core data structure of AmritaSense’s subroutine mechanism, ensuring correct return behavior for nested calls.

### Call stack structure

The call stack is implemented as `Stack[PointerVector]`. Its key properties are:

- **LIFO**: the most recent address pushed is the first to pop, matching nested call return order.
- **Overflow protection**: the stack has a maximum capacity to prevent infinite recursion from exhausting memory.
- **Thread safety**: push and pop operations are protected by internal locking.

### Normal return and exception safety

After the subroutine finishes, `call_sub` restores the return address in its `finally` block. That means **even if the subroutine raises an exception, the return address stack is still cleaned up correctly**. The exception continues to propagate, but the call stack is not corrupted — later calls can still operate normally.

### Nested call stack behavior

In a multi-layer nested call scenario, the call stack evolves like this:

```text
Initial:    []
Call level1: [addr_0]
Call level2: [addr_0, addr_1]
Call level3: [addr_0, addr_1, addr_2]
Level3 return: [addr_0, addr_1]
Level2 return: [addr_0]
Level1 return: []
```

Every `call_sub` pushes the current address, and every return pops the top address. This strict LIFO order ensures that each nested subroutine returns to the correct caller.

### Jump override and return suppression

If the subroutine executes `JMP` or another jump operation, the `JMP` bit is set. In that case, `call_sub`'s `finally` block still pops the saved address, but **skips the pointer restore** — the jump target is preserved and the interpreter continues from there. This means the subroutine's internal jump can "override" normal return behavior: the address that `call_sub` pushed is discarded rather than resumed at. Developers should understand that `JMP` inside a subroutine cancels the automatic return for that call.

### Summary

`call_sub` and the call stack form the low-level foundation of AmritaSense’s subroutine system. The composition-level `INVOKE` instruction is a declarative wrapper around this primitive, while node-internal `call_sub` gives developers full freedom to construct dynamic call chains in code. In the next chapter, we’ll explore how to combine these features with external interruption to build subroutine libraries that can be safely injected from outside.
