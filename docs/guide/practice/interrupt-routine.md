# Interrupt Routine &amp; Return

AmritaSense v0.4.x+ introduces a new capability for **interrupt-style control transfer within a workflow**: save the full interpreter state, jump to a handler routine, then restore and return. This is analogous to how a CPU saves context before vectoring to an interrupt service routine (ISR) and restores it on return.

> **Comparison with PUSH_STACK / RET_FAR**
> `PUSH_STACK` / `RET_FAR` manage only the **return address stack** — like a CPU saving just the program counter. `PUSH_CONTEXT` / `POP_CONTEXT` save the **complete interpreter state** — like a full CPU context switch including all registers. See [Manual Stack Management](/guide/practice/manual-stack-management) for the return-address-only approach.

---

## Core Concepts

### The Context Stack

Each `WorkflowInterpreter` now maintains a **context stack** (`pc.context_stack`), a LIFO stack of `InterpreterContext` snapshots. Each snapshot captures:

| Field                 | Description                                |
| --------------------- | ------------------------------------------ |
| `ptr`                 | Current `PointerVector` (program counter)  |
| `exception_ignored`   | Exception types that bypass TRY/CATCH      |
| `s_args` / `s_kwargs` | Dependency injection parameters (optional) |
| `stack`               | Return-address stack (optional)            |
| `exception`           | Panic exception if any                     |

### The `if_flag`

`pc.if_flag` is a boolean that marks whether the interpreter is currently in an **interrupt context**. It is automatically set by `INTERRUPT_INTO` and cleared by `INTERRUPT_RET`. While `if_flag` is `True`, `INTERRUPT_INTO` cannot be called again — this prevents nested interrupt-into from inside IF branches.

---

## Pattern 1: INTERRUPT_INTO + INTERRUPT_RET (Simplest)

The most concise pattern — best for most interrupt scenarios.

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()  async def main_logic() -> None: ...
@Node()  async def error_handler() -> None:
    print("Handling error, will restore context on return")
@Node()  async def after_handler() -> None: ...

# Step 1: Define the handler inside ARCHIVED_NODES
handler_block = ARCHIVED_NODES(
    ALIAS(error_handler, "on_error"),
    INTERRUPT_RET(),  # <-- restores context and returns
)

# Step 2: Use INTERRUPT_INTO in the main composition
comp = (
    main_logic
    >> INTERRUPT_INTO("on_error")    # save state + jump
    >> after_handler                  # resumed here after INTERRUPT_RET
    >> GOTO("done")
    >> handler_block
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

**What happens:**

1. `INTERRUPT_INTO("on_error")` saves the full interpreter state and jumps to `error_handler`.
2. `error_handler` runs. Then `INTERRUPT_RET` restores the saved state (pointer, exception-ignore list, etc.) and jumps back.
3. The interpreter continues at `after_handler`.

---

## Pattern 2: Manual PUSH_CONTEXT + GOTO + rebase_context (Fine-Grained)

When you need to inspect or modify the saved context before restoring, use manual context management.

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, POP_CONTEXT, PUSH_CONTEXT

@Node()  async def start() -> None:
    print("Saving context...")

@Node()  async def sub_routine() -> None:
    print("  [sub] Working in sub-routine")
    # Could modify pc state here — changes will be visible after restore

@Node()
async def examine_and_restore(ctx: InterpreterContext, pc: WorkflowInterpreter) -> None:
    """Receives the popped context, inspects it, then restores."""
    print(f"  Saved ptr was: {ctx.ptr}")
    print(f"  Ignored exceptions: {ctx.exception_ignored}")
    # Optionally modify ctx before restoring
    pc.rebase_context(ctx)

@Node()  async def finish() -> None:
    print("Back in original flow")

comp = (
    start
    >> PUSH_CONTEXT()
    >> GOTO("sub")
    >> ALIAS(sub_routine, "sub")
    >> POP_CONTEXT()
    >> examine_and_restore
    >> finish
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

**When to use:**

- You need to inspect the saved state before restoring.
- You want to conditionally restore or modify the context.
- You need to serialize the context for debugging/auditing.

---

## Pattern 3: Interrupt Handler Library with ARCHIVED_NODES

Build a library of named interrupt handlers that normal execution skips.

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()  async def main_flow() -> None: ...

# --- Handler library ---
@Node()  async def handle_timeout() -> None:
    print("[timeout handler] Cleaning up...")

@Node()  async def handle_auth_failure() -> None:
    print("[auth handler] Refreshing credentials...")

@Node()  async def health_check() -> None:
    print("[health] All systems nominal")

handler_library = ARCHIVED_NODES(
    ALIAS(handle_timeout, "timeout"),
    ALIAS(handle_auth_failure, "auth"),
    ALIAS(health_check, "health"),
    INTERRUPT_RET(),  # shared return for all handlers
)

# --- Main composition ---
comp = (
    main_flow
    >> INTERRUPT_INTO("timeout")      # choose which handler to invoke
    >> GOTO("done")
    >> handler_library
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

**Note:** When multiple handlers share one `INTERRUPT_RET()`, make sure each handler logically ends by reaching that node. For handlers that need their own return paths, place `INTERRUPT_RET()` inside each handler block.

---

## Pattern 4: Nested Interrupts

The context stack supports **nested** save/restore — like a CPU handling nested interrupts. Each `INTERRUPT_INTO` pushes a new context; each `INTERRUPT_RET` pops the most recent one.

```python
# Outer handler enters via INTERRUPT_INTO
# Inner handler is triggered by another INTERRUPT_INTO inside the outer handler
# Returns unwind in LIFO order: inner RET first, then outer RET

@Node()
async def outer_handler() -> None:
    print("  [outer] Starting...")
    # INTERRUPT_INTO("inner") — nested interrupt
    print("  [outer] Back from inner interrupt")

@Node()
async def inner_handler() -> None:
    print("    [inner] Deep handler")

handlers = ARCHIVED_NODES(
    ALIAS(outer_handler, "outer_handler"),
    INTERRUPT_INTO("inner_handler"),  # nested interrupt call
    INTERRUPT_RET(),                   # outer return
    ALIAS(inner_handler, "inner_handler"),
    INTERRUPT_RET(),                   # inner return
)

comp = (
    main_start
    >> INTERRUPT_INTO("outer_handler")
    >> after_all
    >> GOTO("done")
    >> handlers
    >> ALIAS(NOP, "done")
)
```

**Execution order:**

1. `main_start` → `INTERRUPT_INTO("outer_handler")` saves context A, jumps to `outer_handler`.
2. `outer_handler` runs, hits `INTERRUPT_INTO("inner_handler")` — saves context B, jumps to `inner_handler`.
3. `inner_handler` runs, hits `INTERRUPT_RET()` — restores context B, returns to `outer_handler`.
4. `outer_handler` continues, hits `INTERRUPT_RET()` — restores context A, returns to `after_all`.

---

## Relationship with External Interrupts

| Mechanism                          | Source       | How it works                                                     |
| ---------------------------------- | ------------ | ---------------------------------------------------------------- |
| `call_sub(interrupt=True)`         | **External** | Outside code injects a subroutine at node boundaries             |
| `INTERRUPT_INTO` / `INTERRUPT_RET` | **Internal** | Instructions in the `>>` chain perform context save/jump/restore |

These mechanisms are **complementary**:

- External `call_sub` can invoke a handler that was entered via `INTERRUPT_INTO`.
- An `INTERRUPT_INTO` handler can be stored in `ARCHIVED_NODES` and called externally via `call_sub(interrupt=True)`.
- Use `INTERRUPT_INTO` for **workflow-internal** interrupt patterns; use `call_sub(interrupt=True)` for **debugger/external-agent** injection.

See [External Interrupt Calls](/guide/advanced/external_interrupt) for the external mechanism.

---

## Caveats

1. **No INTERRUPT_INTO inside IF branches**: Attempting `INTERRUPT_INTO` while `pc.if_flag == True` raises `IllegalState`. This protects conditional flow integrity.
2. **Context stack integrity**: `INTERRUPT_RET` pops unconditionally. Ensure every `INTERRUPT_INTO` has a corresponding `INTERRUPT_RET` (or manual `POP_CONTEXT` + `rebase_context`).
3. **if_flag is cleared on return**: After `INTERRUPT_RET`, `pc.if_flag` is always reset to `False`, regardless of the `if_state` set at entry.
4. **`INTERRUPT_RET` performs `jump_to`**: Like other jump instructions, it sets `_jump_marked = True`. The interpreter will not advance the pointer — execution resumes at the restored address.
5. **Dependency injection is preserved**: When `INTERRUPT_INTO` saves context, it always includes `s_args` and `s_kwargs`. Nodes after `INTERRUPT_RET` will see the same dependency injection parameters as before the interrupt.
