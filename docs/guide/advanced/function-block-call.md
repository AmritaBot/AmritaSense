# Function Block Call

AmritaSense provides `FN` / `INTER_FN` — helpers that look like **function definitions** in high-level languages. Before using them, one critical fact must be clear:

> **A function block is a control-flow transfer, not a real function call.** It is a jump into a node region followed by a jump back. There is **no function context**: no stack frame, no local variables, no closure capture, no automatic argument passing, and no return-value convention. The word "function" is only a convenient metaphor.

## What a Function Block Is (and Is Not)

| Aspect            | High-level language function                     | AmritaSense `FN` / `INTER_FN`                      |
| ----------------- | ------------------------------------------------ | --------------------------------------------------- |
| Entry             | Caller evaluates arguments, pushes a frame       | `PUSH_AND_GOTO` / `INTERRUPT_INTO` jump to an alias |
| Local variables   | Fresh frame with locals                          | ❌ none — the interpreter has a single shared state |
| Arguments         | Passed by value/reference                        | ❌ none — data flows via **dependency injection** from the interpreter's arg pool |
| Return value      | `return expr`                                    | ❌ none — `RET_FAR` / `INTERRUPT_RET` only restore the pointer/context |
| Stack             | Dedicated call stack per function                | Shared `_ret_addr_stack` (a single jump target)     |
| Recursion         | Supported                                        | ❌ meaningless — there is no frame to re-enter      |
| Closures / scope  | Lexical scoping, captures                        | ❌ none — the whole workflow shares one pointer space |

Think of a function block as a **named, archived jump target**: entering it changes the pointer; ending it changes the pointer back. Everything else you might expect from a function simply does not exist.

## `FN(entrypoint, block)` — Regular Function Block

```python
from amrita_sense.instructions import FN

fn_block = FN(
    "fn_entry",          # required entrypoint alias
    fn_body,             # NodeCompose or SelfCompileInstruction
)
```

`FN` expands at compile time to:

```text
[_fn_escape, ALIAS(NOP, "fn_entry"), <block>, RET_FAR()]
```

- `_fn_escape` — a hidden node (`rebase_ptr(pointer.copy().offset(3))`). When the normal sequential flow reaches the block, it rebases the pointer **past** the block (`offset(3)` lands exactly on the trailing `RET_FAR`), so the whole block is skipped.
- `ALIAS(NOP, "fn_entry")` — the named entry point. Jumps target this alias.
- `<block>` — your body (a nested container; entered via the pointer).
- `RET_FAR()` — appended automatically. Pops `_ret_addr_stack`, `rebase_ptr`s to the caller's saved address, and the interpreter advances onto the node after the call site.

### Calling an FN Block

```python
from amrita_sense.instructions import PUSH_AND_GOTO

comp = (
    start
    >> PUSH_AND_GOTO(None, "fn_entry")   # call: None = return after this node
    >> after_fn                           # resumed here after RET_FAR
    >> fn_block                           # skipped by normal flow via _fn_escape
)
```

`PUSH_AND_GOTO(None, entrypoint)` pushes the current pointer (main-flow semantics: `None` resolves to the current pointer when not inside a `call_sub`) and jumps to the entrypoint. `RET_FAR` restores the pointer there, and the interpreter advances onto the next node — `after_fn`.

## `INTER_FN(entrypoint, block)` — Interrupt Service Routine

```python
from amrita_sense.instructions import INTER_FN

isr = INTER_FN(
    "isr_entry",
    isr_body,
)
```

Identical shape, but the trailing instruction is `INTERRUPT_RET()` instead of `RET_FAR`:

```text
[_fn_escape, ALIAS(NOP, "isr_entry"), <block>, INTERRUPT_RET()]
```

`INTERRUPT_RET` pops a saved `InterpreterContext` and **restores the whole interpreter state** (pointer, exception-ignore list, dependency args, return-address stack) — not just the pointer.

### Calling an INTER_FN Block

```python
from amrita_sense.instructions import INTERRUPT_INTO

comp = (
    main_start
    >> INTERRUPT_INTO("isr_entry", None)  # dispatch: None = return after this node
    >> after_isr                          # resumed here after INTERRUPT_RET
    >> isr                                # skipped by normal flow via _fn_escape
)
```

`INTERRUPT_INTO(entrypoint, None)` snapshots the interpreter context (with the current pointer as the return address) and jumps to the handler. When the routine ends, `INTERRUPT_RET` restores the snapshot; since the restore uses `rebase_context` (no jump flag), execution advances onto the next node — `after_isr`.

## Relationship with `ARCHIVED_SEGMENT`

`FN` / `INTER_FN` already embed their own skip mechanism (`_fn_escape`), so the block can be placed **directly in the `>>` chain** without extra wrapping:

```python
comp = (
    start
    >> PUSH_AND_GOTO(None, "fn_entry")
    >> after_fn
    >> FN("fn_entry", fn_body)   # fine — no ARCHIVED_SEGMENT needed
)
```

`ARCHIVED_SEGMENT` is the lower-level building block (`[JMP 2, Payload, NOP]`) used when you want to archive an arbitrary compose without the function-call semantics — e.g. a plain section reachable only via `GOTO` that performs its own return (`RET_FAR` / `INTERRUPT_RET`) manually.

## Data Exchange without Function Context

Because there is no argument passing, share data through the workflow's **dependency injection**:

```python
@Node()
async def fn_body(ctx: WorkflowContext) -> None:
    ...  # DI resolves `ctx` from the interpreter's arg pool at the call site
```

The interpreter resolves the body's parameters from the same `_ava_args` / `_ava_kwargs` pool — the block executes in the caller's context, not a fresh one.

## Summary

- `FN` / `INTER_FN` are **named, archived jump targets** with an auto-appended return instruction.
- They change the control flow, **not** the execution context.
- Enter via `PUSH_AND_GOTO(None, entrypoint)` / `INTERRUPT_INTO(entrypoint, None)`; exit via the auto-appended `RET_FAR()` / `INTERRUPT_RET()`.
- No locals, no arguments, no return values, no recursion — design accordingly (use DI for data, use the pointer/context restore for "return").
