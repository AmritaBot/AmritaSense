# Context Snapshot &amp; Interrupt Transfer Instructions (PUSH_CONTEXT/POP_CONTEXT/INTERRUPT_INTO/INTERRUPT_RET)

`PUSH_CONTEXT`, `POP_CONTEXT`, `INTERRUPT_INTO` and `INTERRUPT_RET` are four instructions introduced in v0.4.x+ that work together to provide **full interpreter state save/restore** — analogous to a CPU's context-switch mechanism.

> **Key distinction**
> `PUSH_STACK` / `RET_FAR` save and restore **only the return address** (`_ret_addr_stack`). `PUSH_CONTEXT` / `POP_CONTEXT` save and restore the **entire interpreter state**: pointer, exception-ignore list, dependency injection parameters, return-address stack, and panic exception. `INTERRUPT_INTO` / `INTERRUPT_RET` wrap the former pair into a convenient "interrupt ➔ handler ➔ return" pattern.

## Non-self-compiled direct nodes

All four instructions are **not** `SelfCompileInstruction`. They do not expand into `NodeCompose` at compile time; instead, they exist as single nodes in the workflow array and modify interpreter state at runtime.

They are exported from `amrita_sense.instructions`:

```python
from amrita_sense.instructions import (
    PUSH_CONTEXT,
    POP_CONTEXT,
    INTERRUPT_INTO,
    INTERRUPT_RET,
)
```

## PUSH_CONTEXT

```python
def PUSH_CONTEXT(
    exclude_deps: bool = True,
    exclude_stack: bool = True,
) -> NodeType[None]
```

Saves a complete snapshot of the current interpreter state onto the **context stack** (`pc.context_stack`). The snapshot is stored as an `InterpreterContext` dataclass.

### Parameters

| Parameter       | Type   | Default | Description                                                       |
| --------------- | ------ | ------- | ----------------------------------------------------------------- |
| `exclude_deps`  | `bool` | `True`  | If `True`, dependency args/kwargs are excluded from the snapshot  |
| `exclude_stack` | `bool` | `True`  | If `True`, the return-address stack is excluded from the snapshot |

### What is saved

| Field                 | Condition                          |
| --------------------- | ---------------------------------- |
| `ptr` (PointerVector) | Always                             |
| `exception_ignored`   | Always                             |
| `s_args` / `s_kwargs` | Only when `exclude_deps=False`     |
| `stack` (ret-addr)    | Only when `exclude_stack=False`    |
| `extra`               | Always (empty dict)                |
| `exception`           | Always (panic exception or `None`) |

### Execution flow

1. Calls `pc.dump_interpreter(exclude_deps, exclude_stack)` to build an `InterpreterContext`.
2. Pushes the context onto `pc.context_stack`.
3. Returns `None` — execution continues to the next node in the `>>` chain.

---

## POP_CONTEXT

```python
def POP_CONTEXT() -> NodeType[InterpreterContext]
```

Pops the top `InterpreterContext` from the context stack and **returns it as the node's result**. The caller is responsible for deciding what to do with the context — it may inspect it, serialize it, or pass it to `pc.rebase_context(ctx)` to actually restore the saved state.

### Execution flow

1. Pops top of `pc.context_stack`.
2. Returns the `InterpreterContext` as the node output.
3. The **next node in the chain** receives this `InterpreterContext` as its input argument.

### Important

`POP_CONTEXT` does **not** automatically restore state. If you want to restore, the receiving node must call `pc.rebase_context(ctx)`:

```python
@Node()
async def restore(ctx: InterpreterContext, pc: WorkflowInterpreter) -> None:
    pc.rebase_context(ctx)
```

Or use `INTERRUPT_RET()` which performs the restore automatically.

---

## INTERRUPT_INTO

```python
def INTERRUPT_INTO(
    alias_or_idata: str | list[int],
    if_state: bool = False,
) -> NodeType[None]
```

A convenience instruction that combines `PUSH_CONTEXT` + `jump_to` in a single node. It saves the current interpreter state and then jumps to the target address — exactly like a CPU interrupt that saves context before vectoring to the ISR.

### Parameters

| Parameter        | Type               | Default | Description                                                          |
| ---------------- | ------------------ | ------- | -------------------------------------------------------------------- |
| `alias_or_idata` | `str \| list[int]` | —       | Target alias string (resolved at runtime) or absolute address vector |
| `if_state`       | `bool`             | `False` | Value to set for the interpreter's `if_flag` after the jump          |

### Execution flow

1. **Guard check**: if `pc.if_flag` is already `True`, raises `IllegalState("Interrupt into is not allowed in IF statement")`. You cannot nest interrupt-into calls inside an IF branch.
2. Sets `pc.if_flag = if_state`.
3. Resolves the alias (if a string) to an absolute address via `pc.find_addr_alias()`.
4. Saves interpreter state via `pc.dump_interpreter()` and pushes onto `pc.context_stack`.
5. Jumps to the target address via `pc.jump_to(addr)`.

### Restrictions

- **Cannot be used inside IF branches** (`pc.if_flag == True`). This prevents interrupt-style jumps from breaking conditional flow integrity.

---

## INTERRUPT_RET

```python
def INTERRUPT_RET() -> NodeType[None]
```

The counterpart to `INTERRUPT_INTO`. Pops the top `InterpreterContext` from the context stack and restores the interpreter to its pre-interrupt state via `pc.rebase_context(ctx)`. Also clears `pc.if_flag`.

### Execution flow

1. Pops the top `InterpreterContext` from `pc.context_stack`.
2. Calls `pc.rebase_context(ctx)` — restores pointer, exception-ignore list, dependency args, return-address stack.
3. Sets `pc.if_flag = False`.

This is the recommended way to return from a handler entered via `INTERRUPT_INTO`.

---

## Comparison: Three Save/Restore Mechanisms

| Feature                  | PUSH_STACK + RET_FAR       | PUSH_CONTEXT + POP_CONTEXT                 | INTERRUPT_INTO + INTERRUPT_RET     |
| ------------------------ | -------------------------- | ------------------------------------------ | ---------------------------------- |
| **Saves**                | Return address only        | Full interpreter state                     | Full interpreter state             |
| **Dependency args**      | Not saved                  | Optional (`exclude_deps=False`)            | Always saved                       |
| **Return-address stack** | Manually managed by caller | Optional (`exclude_stack=False`)           | Always saved                       |
| **if_flag management**   | Not involved               | Not involved                               | Auto set on entry, cleared on exit |
| **Restore method**       | `RET_FAR` pops & jumps     | Caller calls `rebase_context(ctx)`         | `INTERRUPT_RET` auto-restores      |
| **Use case**             | Custom call/return schemes | Fine-grained state inspection/manipulation | Interrupt-style handler entry/exit |
| **Complexity**           | Low                        | Medium (manual rebase)                     | Low (one-click save/restore)       |

---

## Examples

### Basic context save/restore

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, POP_CONTEXT, PUSH_CONTEXT

@Node()
async def start() -> None:
    print("Start — saving context")

@Node()
async def sub_work() -> None:
    print("  [sub] Doing work in isolated context")

@Node()
async def inspect_context(ctx) -> None:
    # ctx is the InterpreterContext popped by POP_CONTEXT
    print(f"  Context snapshot — ptr was: {ctx.ptr}")

@Node()
async def finish() -> None:
    print("Finish")

comp = (
    start
    >> PUSH_CONTEXT()
    >> GOTO("sub")
    >> ALIAS(sub_work, "sub")
    >> POP_CONTEXT()
    >> inspect_context
    >> finish
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

### Interrupt-style handler with ARCHIVED_NODES

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()
async def main_start() -> None:
    print("[main] Triggering interrupt...")

@Node()
async def handler() -> None:
    print("  [handler] Processing interrupt")

@Node()
async def back() -> None:
    print("[main] Back from interrupt")

# Archived handler — skipped during normal execution
handler_block = ARCHIVED_NODES(
    ALIAS(handler, "int_handler"),
    INTERRUPT_RET(),
)

comp = (
    main_start
    >> INTERRUPT_INTO("int_handler")
    >> back
    >> GOTO("done")
    >> handler_block
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

### Including dependency args in the snapshot

```python
# Save everything including dependency injection state
comp = (
    start
    >> PUSH_CONTEXT(exclude_deps=False, exclude_stack=False)
    >> GOTO("sub")
    >> ALIAS(sub_work, "sub")
    >> POP_CONTEXT()
    >> restore_and_continue  # receives full InterpreterContext
)
```

> **See also**: [Interrupt Routine &amp; Return](/guide/practice/interrupt-routine) for advanced patterns including nested interrupts, manual rebase, and integration with external interrupt calls.
