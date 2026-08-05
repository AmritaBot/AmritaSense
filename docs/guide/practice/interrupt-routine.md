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

## Pattern 1: PUSH_CONTEXT + INTERRUPT_RET (Simplest Context Save)

The simplest pattern — save full state, jump to a sub-routine, restore and return. Since v0.6.0, `PUSH_CONTEXT` no longer jumps, so the jump into the sub-routine must be explicit (`GOTO`).

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_RET, PUSH_CONTEXT

@Node()
async def start() -> None: ...
@Node()
async def sub_routine() -> None: ...
@Node()
async def after_restore() -> None: ...

comp = (
    start
    >> PUSH_CONTEXT("resume")      # save state; return address = resume NOP
    >> GOTO("sub_entry")           # explicit jump to sub (v0.6.0+)
    >> ALIAS(NOP, "resume")        # INTERRUPT_RET rebases here -> advance onto after_restore
    >> after_restore                # resumed here after INTERRUPT_RET
    >> GOTO("done")
    >> ALIAS(sub_routine, "sub_entry")
    >> INTERRUPT_RET()              # pop & restore
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

---

## Pattern 2: INTERRUPT_INTO + INTERRUPT_RET (Interrupt with Return)

`INTERRUPT_INTO(jump_to, ret_to=None)` takes the target to jump to now, plus an optional return destination. This is the closest analog to CPU interrupt semantics. With `ret_to=None` in the main flow, the saved return address is the instruction itself — after `INTERRUPT_RET` restores, the interpreter advances onto the next node.

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()
async def main_logic() -> None: ...
@Node()
async def error_handler() -> None:
    print("Handling error")

handler_block = ARCHIVED_NODES(
    ALIAS(error_handler, "on_error"),
    INTERRUPT_RET(),
)

comp = (
    main_logic
    >> INTERRUPT_INTO("on_error", "restore_here")
    #     ^jump now            ^return address saved in context
    >> ALIAS(NOP, "restore_here")
    >> after_handler
    >> GOTO("done")
    >> handler_block
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

**What happens:**

1. `INTERRUPT_INTO("on_error", "restore_here")` saves interpreter state, **replaces** the saved ptr with `"restore_here"`, sets `if_flag`, jumps to `error_handler`.
2. `error_handler` runs. `INTERRUPT_RET` pops and restores the state — `rebase_context` puts the pointer at `"restore_here"`, then the interpreter advances onto the next node (`after_handler`).
3. `after_handler` executes, then `GOTO("done")`.

---

## Pattern 3: Interrupt Handler Library with ARCHIVED_NODES

Build a library of named interrupt handlers that normal execution skips.

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()
async def main_flow() -> None: ...

@Node()
async def handle_timeout() -> None:
    print("[timeout] Cleaning up...")

@Node()
async def handle_auth_failure() -> None:
    print("[auth] Refreshing credentials...")

handler_library = ARCHIVED_NODES(
    ALIAS(handle_timeout, "timeout"),
    INTERRUPT_RET(),
    ALIAS(handle_auth_failure, "auth"),
    INTERRUPT_RET(),
)

comp = (
    main_flow
    >> INTERRUPT_INTO("timeout", "after_timeout")
    >> ALIAS(NOP, "after_timeout")
    >> GOTO("done")
    >> handler_library
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

---

## Pattern 4: Nested Interrupts

The context stack supports **nested** save/restore — like a CPU handling nested interrupts.

```python
@Node()
async def outer_handler() -> None:
    print("  [outer] Starting...")
    # hits INTERRUPT_INTO inside the outer handler

@Node()
async def inner_handler() -> None:
    print("    [inner] Deep handler")

handlers = ARCHIVED_NODES(
    ALIAS(outer_handler, "outer_handler"),
    INTERRUPT_INTO("inner_handler", "after_inner"),
    ALIAS(NOP, "after_inner"),
    INTERRUPT_RET(),                   # outer return
    ALIAS(inner_handler, "inner_handler"),
    INTERRUPT_RET(),                   # inner return
)

comp = (
    main_start
    >> INTERRUPT_INTO("outer_handler", "after_outer")
    >> ALIAS(NOP, "after_outer")
    >> after_all
    >> GOTO("done")
    >> handlers
    >> ALIAS(NOP, "done")
)
```

---

## Relationship with External Interrupts

| Mechanism                          | Source       | How it works                                                     |
| ---------------------------------- | ------------ | ---------------------------------------------------------------- |
| `call_sub(interrupt=True)`         | **External** | Outside code injects a subroutine at node boundaries             |
| `INTERRUPT_INTO` / `INTERRUPT_RET` | **Internal** | Instructions in the `>>` chain perform context save/jump/restore |

See [External Interrupt Calls](/guide/advanced/external_interrupt) for the external mechanism.

---

## Caveats

1. **No INTERRUPT_INTO inside IF branches**: `pc.if_flag == True` raises `IllegalState`.
2. **ret_to is optional (v0.6.0+)**: `INTERRUPT_INTO(jump_to)` works without `ret_to` — `None` resolves to the top of `_ret_addr_stack` inside a `call_sub`, otherwise to the current pointer (advancing onto the next node after restore).
3. **if_flag cleared on return**: After `INTERRUPT_RET`, `pc.if_flag` is always reset to `False`.
4. **INTERRUPT_RET does not set the jump flag**: it restores via `rebase_context` (i.e. `rebase_ptr`) — execution resumes at the node **after** the saved address. Save the predecessor of your real resume point when using `PUSH_CONTEXT` / explicit `ret_to`.
5. **Dependency injection preserved**: `INTERRUPT_INTO` always includes `s_args` and `s_kwargs`.
6. **Context stack integrity**: Ensure each `PUSH_CONTEXT`/`INTERRUPT_INTO` has a corresponding `INTERRUPT_RET`.
