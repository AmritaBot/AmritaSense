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
    alias_or_idata: str | list[int],
    *,
    exclude_deps: bool = True,
    exclude_stack: bool = True,
) -> NodeType[None]
```

Saves a complete snapshot of the current interpreter state onto the **context stack** (`pc.context_stack`) **and then jumps** to `alias_or_idata`. The snapshot is stored as an `InterpreterContext` dataclass.

This is the low-level primitive — unlike `INTERRUPT_INTO`, it does **not** set `if_flag`. Pair with `INTERRUPT_RET` to restore; or pop manually and call `pc.rebase_context()`.

### Parameters

| Parameter        | Type               | Default | Description                                                       |
| ---------------- | ------------------ | ------- | ----------------------------------------------------------------- |
| `alias_or_idata` | `str \| list[int]` | —       | Alias string (resolved at runtime) or absolute address to jump to |
| `exclude_deps`   | `bool`             | `True`  | If `True`, dependency args/kwargs are excluded from the snapshot  |
| `exclude_stack`  | `bool`             | `True`  | If `True`, the return-address stack is excluded from the snapshot |

### What is saved

| Field                 | Condition                              |
| --------------------- | -------------------------------------- |
| `ptr` (PointerVector) | Always (snapshot of pre-jump position) |
| `exception_ignored`   | Always                                 |
| `s_args` / `s_kwargs` | Only when `exclude_deps=False`         |
| `stack` (ret-addr)    | Only when `exclude_stack=False`        |
| `extra`               | Always (empty dict)                    |
| `exception`           | Always (panic exception or `None`)     |

### Execution flow

1. Resolves `alias_or_idata` to an absolute address.
2. Calls `pc.dump_interpreter(exclude_deps, exclude_stack)` to build an `InterpreterContext`.
3. Pushes the context onto `pc.context_stack`.
4. Calls `pc.jump_to(addr)` — execution resumes at the target.

---

## POP_CONTEXT

```python
def POP_CONTEXT() -> NodeType[InterpreterContext]
```

Pops the top `InterpreterContext` from the context stack and **returns it as the node's result**. The return value goes to the interpreter's step-by-step generator — it does **not** automatically flow into the next `>>` node's arguments.

To actually restore state, either use `INTERRUPT_RET()` which pops and auto-restores, or pop manually via `pc.context_stack.pop()` inside a `@Node` function.

### Execution flow

1. Pops top of `pc.context_stack`.
2. Returns the `InterpreterContext` as the node output.

---

## INTERRUPT_INTO

```python
def INTERRUPT_INTO(
    jump_to: str | list[int],
    ret_to: str | list[int],
    if_state: bool = False,
) -> NodeType[None]
```

A convenience instruction for interrupt-style control transfer. It saves the current interpreter state and jumps to `jump_to`, but **overwrites the saved pointer with `ret_to`** so that `INTERRUPT_RET` resumes at `ret_to` — not at the original position.

This mirrors real CPU interrupt semantics: the return address is explicitly the instruction **after** the interrupted one.

### Parameters

| Parameter  | Type               | Default | Description                                                      |
| ---------- | ------------------ | ------- | ---------------------------------------------------------------- |
| `jump_to`  | `str \| list[int]` | —       | Target alias or address to jump to **now** (the handler)         |
| `ret_to`   | `str \| list[int]` | —       | Alias or address saved as the return destination in the snapshot |
| `if_state` | `bool`             | `False` | Value to set for the interpreter's `if_flag` after the jump      |

### Execution flow

1. **Guard check**: if `pc.if_flag` is already `True`, raises `IllegalState("Interrupt into is not allowed in IF statement")`.
2. Sets `pc.if_flag = if_state`.
3. Resolves both `jump_to` and `ret_to` addresses (cached after first resolution).
4. Saves interpreter state via `pc.dump_interpreter()`.
5. **Overwrites** `ctx.ptr` with `PointerVector(ret_to)`.
6. Pushes the context onto `pc.context_stack`.
7. Jumps to `jump_to` via `pc.jump_to()`.

### Restrictions

- **Cannot be used inside IF branches** (`pc.if_flag == True`).

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

---

## Comparison: Three Save/Restore Mechanisms

| Feature                | PUSH_STACK + RET_FAR       | PUSH_CONTEXT + INTERRUPT_RET   | INTERRUPT_INTO + INTERRUPT_RET     |
| ---------------------- | -------------------------- | ------------------------------ | ---------------------------------- |
| **Saves**              | Return address only        | Full interpreter state         | Full interpreter state             |
| **Jumps on save**      | No (separate GOTO needed)  | Yes (to target)                | Yes (jump_to)                      |
| **Return address**     | PUSH_STACK target          | Restored from saved pointer    | Explicit ret_to param              |
| **Dependency args**    | Not saved                  | Optional (exclude_deps=False)  | Always saved                       |
| **if_flag management** | Not involved               | Not involved                   | Auto set on entry, cleared on exit |
| **Use case**           | Custom call/return schemes | Context save + jump primitives | Interrupt-style handler entry/exit |
| **Complexity**         | Low                        | Low                            | Low                                |

---

## Examples

### Basic context save/restore

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_RET, PUSH_CONTEXT

@Node()
async def start() -> None:
    print("Start — saving context")

@Node()
async def sub_work() -> None:
    print("  [sub] Doing work in isolated context")

@Node()
async def after_restore() -> None:
    print("Back — restored by INTERRUPT_RET")

comp = (
    start
    >> PUSH_CONTEXT("sub_entry")
    >> after_restore
    >> GOTO("done")
    >> ALIAS(sub_work, "sub_entry")
    >> INTERRUPT_RET()
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

### Interrupt-style handler with explicit return address

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

handler_block = ARCHIVED_NODES(
    ALIAS(handler, "int_handler"),
    INTERRUPT_RET(),
)

comp = (
    main_start
    >> INTERRUPT_INTO("int_handler", "restore_here")
    >> ALIAS(NOP, "restore_here")
    >> back
    >> GOTO("done")
    >> handler_block
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

> **See also**: [Interrupt Routine &amp; Return](/guide/practice/interrupt-routine) for advanced patterns.
