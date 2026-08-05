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

`pc.if_flag` is a boolean that marks whether the interpreter is in an **interrupt context**. `INTERRUPT_INTO` sets it to the `if_state` argument (default `False`), and `INTERRUPT_RET` resets it to `False` on return. When `if_state=True` is used, a subsequent `INTERRUPT_INTO` raises `IllegalState` — this guard prevents re-entry from inside an IF branch that was entered with the flag set. With the default `if_state=False`, **nested** interrupts are allowed (see Pattern 4).

---

## Pattern 1: PUSH_CONTEXT + INTERRUPT_RET (Simplest Context Save)

The simplest pattern — save full state, jump to a sub-routine, restore and return. Since v0.6.0, `PUSH_CONTEXT` no longer jumps, so the jump into the sub-routine must be explicit (`GOTO`). No trailing `GOTO("done")` / `ALIAS(NOP, "done")` is needed — the archived block skips itself and the interpreter finishes at the end of the workflow.

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
    >> ALIAS(sub_routine, "sub_entry")
    >> INTERRUPT_RET()              # pop & restore
)
await WorkflowInterpreter(comp.render()).run()
```

> `PUSH_CONTEXT` is the low-level primitive. For most use cases, prefer `INTER_FN` + `INTERRUPT_INTO` (Pattern 2) — it handles the return address automatically.

---

## Pattern 2: INTER_FN + INTERRUPT_INTO (Recommended)

The modern way: define the handler with **`INTER_FN(entrypoint, block)`** — it auto-appends `INTERRUPT_RET()` and embeds its own skip mechanism. Dispatch with `INTERRUPT_INTO(entrypoint, None)` — `None` means "return to the node right after the dispatch" (no manual `ret_to` / `restore_here` NOP needed).

```python
from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.instructions import INTER_FN, INTERRUPT_INTO

@Node()
async def main_logic() -> None: ...
@Node()
async def error_handler() -> None:
    print("Handling error")

handler_block = INTER_FN("on_error", error_handler)

comp = (
    main_logic
    >> INTERRUPT_INTO("on_error", None)   # jump to handler; return after this node
    >> after_handler                        # resumed here after INTERRUPT_RET
    >> handler_block                        # skipped by normal flow (_fn_escape)
)
await WorkflowInterpreter(comp.render()).run()
```

**What happens:**

1. `INTERRUPT_INTO("on_error", None)` saves interpreter state (return address = the instruction itself), sets `if_flag`, jumps to the handler entry.
2. `error_handler` runs, then the auto-appended `INTERRUPT_RET()` pops and restores the state — `rebase_context` puts the pointer at the dispatch instruction, and the interpreter advances onto the next node (`after_handler`).
3. `after_handler` executes; the `handler_block` is skipped by `_fn_escape` during normal flow.

---

## Pattern 3: Interrupt Handler Library with INTER_FN

Build a library of named interrupt handlers that normal execution skips — just concatenate `INTER_FN` blocks with `>>` (each has its own `_fn_escape` skip):

```python
from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.instructions import INTER_FN, INTERRUPT_INTO

@Node()
async def main_flow() -> None: ...

@Node()
async def handle_timeout() -> None:
    print("[timeout] Cleaning up...")

@Node()
async def handle_auth_failure() -> None:
    print("[auth] Refreshing credentials...")

handler_library = INTER_FN("timeout", handle_timeout) >> INTER_FN("auth", handle_auth_failure)

comp = (
    main_flow
    >> INTERRUPT_INTO("timeout", None)
    >> INTERRUPT_INTO("auth", None)
    >> handler_library
)
await WorkflowInterpreter(comp.render()).run()
```

---

## Pattern 4: Nested Interrupts

The context stack supports **nested** save/restore — like a CPU handling nested interrupts. With the default `if_state=False`, an `INTERRUPT_INTO` inside a handler is allowed; the inner `INTER_FN` restores back into the outer handler, which then completes and restores back to the main flow:

```python
from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.instructions import INTER_FN, INTERRUPT_INTO

@Node()
async def outer_func() -> None:
    print("  [outer] Starting...")

@Node()
async def inner_func() -> None:
    print("    [inner] Deep handler")

outer = INTER_FN(
    "outer_handler",
    outer_func >> INTERRUPT_INTO("inner_handler", None),  # nested dispatch
)
inner = INTER_FN("inner_handler", inner_func)

comp = (
    main_start
    >> INTERRUPT_INTO("outer_handler", None)
    >> after_all
    >> outer
    >> inner
)
await WorkflowInterpreter(comp.render()).run()
```

Execution: main → outer handler → nested `INTERRUPT_INTO` → inner handler → inner `INTERRUPT_RET` (auto) → back into outer handler → outer `INTERRUPT_RET` (auto) → `after_all`.

---

## Relationship with External Interrupts

| Mechanism                          | Source       | How it works                                                     |
| ---------------------------------- | ------------ | ---------------------------------------------------------------- |
| `call_sub(interrupt=True)`         | **External** | Outside code injects a subroutine at node boundaries             |
| `INTERRUPT_INTO` / `INTERRUPT_RET` | **Internal** | Instructions in the `>>` chain perform context save/jump/restore |

See [External Interrupt Calls](/guide/advanced/external_interrupt) for the external mechanism.

---

## Caveats

1. **INTERRUPT_INTO with `if_state=True` inside IF branches**: `pc.if_flag == True` raises `IllegalState`. With the default `if_state=False`, nesting is allowed (Pattern 4).
2. **ret_to is optional (v0.6.0+)**: `INTERRUPT_INTO(jump_to)` works without `ret_to` — `None` resolves to the top of `_ret_addr_stack` inside a `call_sub`, otherwise to the current pointer (advancing onto the next node after restore). Prefer `None` over a manual `restore_here` NOP.
3. **if_flag cleared on return**: After `INTERRUPT_RET`, `pc.if_flag` is always reset to `False`.
4. **INTERRUPT_RET does not set the jump flag**: it restores via `rebase_context` (i.e. `rebase_ptr`) — execution resumes at the node **after** the saved address. Save the predecessor of your real resume point when using `PUSH_CONTEXT` / explicit `ret_to`.
5. **Dependency injection preserved**: `INTERRUPT_INTO` always includes `s_args` and `s_kwargs`.
6. **Context stack integrity**: Ensure each `PUSH_CONTEXT`/`INTERRUPT_INTO` has a corresponding `INTERRUPT_RET`.
