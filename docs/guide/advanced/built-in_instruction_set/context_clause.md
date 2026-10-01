# Context Snapshot &amp; Interrupt Transfer Instructions (PUSH_CONTEXT/POP_CONTEXT/INT/IRET)

`PUSH_CONTEXT`, `POP_CONTEXT`, `INT` and `IRET` are four instructions that work together to provide **full interpreter state save/restore** — analogous to a CPU's context-switch mechanism.

> **Key distinction**
> `PUSH_RET` / `RET` save and restore **only the return address** (`_ret_addr_stack`). `PUSH_CONTEXT` / `POP_CONTEXT` save and restore the **entire interpreter state**: pointer, exception-ignore list, dependency injection parameters, return-address stack, and panic exception. `INT` / `IRET` wrap the former pair into a convenient "interrupt ➔ handler ➔ return" pattern.

## Non-self-compiled direct nodes

All four instructions are **not** `SelfCompileInstruction`. They do not expand into `NodeCompose` at compile time; instead, they exist as single nodes in the workflow array and modify interpreter state at runtime.

They are exported from `amrita_sense.instructions`:

```python
from amrita_sense.instructions import (
    PUSH_CONTEXT,
    POP_CONTEXT,
    INT,
    IRET,
)
```

## PUSH_CONTEXT

```python
def PUSH_CONTEXT(
    alias_or_idata: str | list[int] | None = None,
    *,
    exclude_deps: bool = True,
    exclude_stack: bool = True,
) -> NodeType[None]
```

Saves a complete snapshot of the current interpreter state onto the **context stack** (`pc.context_stack`). It does **not** jump — the snapshot's pointer is set to the resolved `alias_or_idata` address so that when the context is later restored, execution resumes there (it serves as the **return address**, not a jump target). If you need to move to the sub-flow, follow it with an explicit `JMP` / `INT`.

This is the low-level primitive — unlike `INT`, it does **not** set `if_flag` and does **not** guard against being called inside an IF branch. Pair with `IRET` to restore; or pop manually and call `pc.rebase_context()`.

### Parameters

| Parameter        | Type                       | Default | Description                                                                                         |
| ---------------- | -------------------------- | ------- | --------------------------------------------------------------------------------------------------- |
| `alias_or_idata` | `str \| list[int] \| None` | `None`  | Alias or address saved as the **return address** in the snapshot. `None` = top of `_ret_addr_stack` |
| `exclude_deps`   | `bool`                     | `True`  | If `True`, dependency args/kwargs are excluded from the snapshot                                    |
| `exclude_stack`  | `bool`                     | `True`  | If `True`, the return-address stack is excluded from the snapshot                                   |

### What is saved

| Field                 | Condition                            |
| --------------------- | ------------------------------------ |
| `ptr` (PointerVector) | Always (the resolved return address) |
| `exception_ignored`   | Always                               |
| `s_args` / `s_kwargs` | Only when `exclude_deps=False`       |
| `stack` (ret-addr)    | Only when `exclude_stack=False`      |
| `extra`               | Always (empty dict)                  |
| `exception`           | Always (panic exception or `None`)   |
| `flags`               | Always (`HLT` stripped)              |

### Execution flow

1. Resolves `alias_or_idata` (or the top of `_ret_addr_stack` when `None`) to an absolute address.
2. Calls `pc.dump_interpreter(exclude_deps, exclude_stack)` to build an `InterpreterContext`.
3. Overwrites `ctx.ptr` with the resolved return address.
4. Pushes the context onto `pc.context_stack` — **no jump is performed**.

> Since `IRET` restores via `rebase_context` (no jump flag), execution resumes at the node **after** the saved address. Save the predecessor of your real resume point (e.g. a `NOP` before it), or rely on `INT(..., ret_to=None)` which handles this automatically.

---

## POP_CONTEXT

```python
def POP_CONTEXT() -> NodeType[InterpreterContext]
```

Pops the top `InterpreterContext` from the context stack and **returns it as the node's result**. The return value goes to the interpreter's step-by-step generator — it does **not** automatically flow into the next `>>` node's arguments.

To actually restore state, either use `IRET()` which pops and auto-restores, or pop manually via `pc.context_stack.pop()` inside a `@Node` function.

### Execution flow

1. Pops top of `pc.context_stack`.
2. Returns the `InterpreterContext` as the node output.

---

## INT

```python
def INT(
    jump_to: str | list[int],
    ret_to: str | list[int] | None = None,
    if_state: bool = False,
) -> NodeType[None]
```

A convenience instruction for interrupt-style control transfer. It saves the current interpreter state and jumps to `jump_to`, but **overwrites the saved pointer with `ret_to`** so that `IRET` resumes at `ret_to` — not at the original position.

This mirrors real CPU interrupt semantics: the return address is the instruction where execution should resume after the handler returns.

### Parameters

| Parameter  | Type                       | Default | Description                                                                                                                       |
| ---------- | -------------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `jump_to`  | `str \| list[int]`         | —       | Target alias or address to jump to **now** (the handler)                                                                          |
| `ret_to`   | `str \| list[int] \| None` | `None`  | Alias or address saved as the return destination. `None` = top of `_ret_addr_stack` inside a `call_sub`, else the current pointer |
| `if_state` | `bool`                     | `False` | Value to set for the interpreter's `if_flag` after the jump                                                                       |

### Execution flow

1. **Guard check**: if `pc.if_flag` is already `True`, raises `IllegalState("Interrupt into is not allowed in IF statement")`.
2. Sets `pc.if_flag = if_state`.
3. Resolves `jump_to` and `ret_to` addresses (cached after first resolution). When `ret_to` is `None`: inside a `call_sub` (`pc.outer_interpreting` is `True`) it reuses the top of `_ret_addr_stack`; otherwise it uses the current pointer.
4. Saves interpreter state via `pc.dump_interpreter()`.
5. **Overwrites** `ctx.ptr` with `PointerVector(ret_addr)`.
6. Pushes the context onto `pc.context_stack`.
7. Jumps to `jump_to` via `pc.jump_to()`.

> `IRET` restores via `rebase_context` (no jump flag), so execution resumes at the node **after** the saved return address. With `ret_to=None` in the main flow, the saved address is the instruction itself — the interpreter advances onto the next node, which is exactly the "return here" point.

### Restrictions

- **Cannot be used inside IF branches** (`pc.if_flag == True`).

---

## IRET

```python
def IRET() -> NodeType[None]
```

The counterpart to `INT`. Pops the top `InterpreterContext` from the context stack and restores the interpreter to its pre-interrupt state via `pc.rebase_context(ctx)`. Also clears `pc.if_flag`.

### Execution flow

1. Pops the top `InterpreterContext` from `pc.context_stack`.
2. Calls `pc.rebase_context(ctx)` — restores pointer, exception-ignore list, dependency args, return-address stack, panic exception, and the status register.
3. Sets `pc.if_flag = False`.

---

## Comparison: Three Save/Restore Mechanisms

| Feature                | PUSH_RET + RET             | PUSH_CONTEXT + IRET            | INT + IRET                         |
| ---------------------- | -------------------------- | ------------------------------ | ---------------------------------- |
| **Saves**              | Return address only        | Full interpreter state         | Full interpreter state             |
| **Jumps on save**      | No (separate JMP needed)   | No (separate JMP needed)       | Yes (jump_to)                      |
| **Return address**     | PUSH_RET target            | Resolved alias / ret-stack top | `ret_to` param (or default)        |
| **Dependency args**    | Not saved                  | Optional (exclude_deps=False)  | Always saved                       |
| **if_flag management** | Not involved               | Not involved                   | Auto set on entry, cleared on exit |
| **Use case**           | Custom call/return schemes | Context save + jump primitives | Interrupt-style handler entry/exit |
| **Complexity**         | Low                        | Low                            | Low                                |

---

## Examples

### Basic context save/restore

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import JMP, IRET, PUSH_CONTEXT


@Node()
async def start() -> None:
    print("Start — saving context")


@Node()
async def sub_work() -> None:
    print("  [sub] Doing work in isolated context")


@Node()
async def after_restore() -> None:
    print("Back — restored by IRET")


comp = (
    start
    >> PUSH_CONTEXT("resume")  # snapshot; return address = the resume NOP
    >> JMP("sub_entry")  # explicit jump into the sub-flow
    >> ALIAS(NOP, "resume")  # IRET rebases here -> advance onto after_restore
    >> after_restore
    >> ALIAS(sub_work, "sub_entry")
    >> IRET()
)
await WorkflowInterpreter(comp.render()).run()
```

### Interrupt-style handler (INTER_FN + ret_to=None)

```python
from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.instructions import INTER_FN, INT


@Node()
async def main_start() -> None:
    print("[main] Triggering interrupt...")


@Node()
async def handler() -> None:
    print("  [handler] Processing interrupt")


@Node()
async def back() -> None:
    print("[main] Back from interrupt")


handler_block = INTER_FN("int_handler", handler)

comp = (
    main_start
    >> INT("int_handler")  # None = return after this node
    >> back
    >> handler_block  # skipped by normal flow
)
await WorkflowInterpreter(comp.render()).run()
```

> **See also**: [Interrupt Routine &amp; Return](/guide/practice/interrupt-routine) for advanced patterns.
