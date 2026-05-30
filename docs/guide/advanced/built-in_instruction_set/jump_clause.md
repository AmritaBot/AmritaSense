# GOTO & CALL Jump Instructions

`GOTO` and `CALL` are two core control flow jump instructions in AmritaSense. They share the same alias-based addressing infrastructure, but serve very different scenarios: `GOTO` is an unconditional one-way jump, while `CALL` is a subroutine invocation with a return.

> **Common foundation**
> Both rely on the same alias registry (`ALIAS`), perform address resolution during `_pre_check`, and use the `@markup` decorator to manage jump markers. Understanding these common mechanisms helps clarify the difference between them.

## Non-self-compiled direct nodes

`GOTO` and `CALL` are **not** `SelfCompileInstruction`. They do not expand into `NodeCompose` at compile time; instead, they exist as single jump nodes in the workflow array.

That means:

- they are compiled as a single `JumpNode` or `CallNode` element
- runtime behavior is expressed entirely through address resolution and pointer rewriting
- they do not create new Bubbles or nesting scopes

## GOTO

`GOTO` is a factory wrapper for `JumpNode`. At runtime, it calls the interpreter’s `jump_to` method and performs a **one-way, non-returning** pointer rewrite.

### Execution flow

1. **Address resolution** (`_pre_check`): resolve alias names through the alias table, or validate raw addresses.
2. **Jump marker**: call `pc.jump_to(addr)`, which is guarded by `@markup` and sets `_jump_marked=True`.
3. **Pointer replacement**: replace `_pointer` completely with the target address vector.
4. **Interpreter response**: the main loop sees `_jump_marked` and skips normal `_advance_pointer()`, continuing from the jump target.

### Key characteristics

- **Does not manage the call stack**: `GOTO` does not push anything onto `_ret_addr_stack`. Once jumped, there is no return.
- **Can jump across any nesting level**: because `far_to(addr)` replaces the entire pointer vector, `GOTO` can cross Bubble boundaries.
- **Supports both alias and raw address**: `GOTO("target")` uses a symbol, while `GOTO([1, 2, 3])` uses an absolute address.

### Typical use cases

- **Error handling jumps**: jump directly to a centralized error handler when a failure is detected.
- **Branch merging**: multiple conditional branches converge on the same `NOP` point.
- **State machine transitions**: jump to different next states based on runtime conditions.

## CALL

`CALL` is a factory wrapper for `CallNode`. At runtime, it calls the interpreter’s `call_sub` method and performs a **push → jump → execute → pop** subroutine call.

### Execution flow

1. **Address resolution** (`_pre_check`): resolve alias names and cache the absolute address.
2. **Push return address**: `call_sub` saves the current pointer vector on `_ret_addr_stack`.
3. **Pointer replacement**: set the execution pointer to the subroutine’s entry address.
4. **Execute subroutine**: the interpreter advances through the subroutine nodes.
5. **Pop return address**: when the subroutine completes, the `finally` block pops the saved pointer and restores it.
6. **Continue execution**: the interpreter continues from the node after the `CALL` instruction.

### Key characteristics

- **Manages call stack**: pushes the return address and pops it later, supporting nested calls.
- **Subroutine source**: the target can be any addressable node sequence, not necessarily stored in `ARCHIVED_NODES`.
- **No direct parameter passing**: `CALL` itself does not pass arguments. If the subroutine needs parameters, use `Depends` inside the subroutine node or call `call_sub` directly within a node.

### Typical use cases

- **Code reuse**: encapsulate reusable node sequences as subroutines and call them multiple times.
- **Modular decomposition**: split complex workflows into independent subprocedures and keep the main flow simple.
- **Interrupt handling**: external systems can invoke predefined interrupt handlers via `call_sub(interrupt=True)`.

## GOTO vs CALL: comparison

| Feature           | GOTO                                       | CALL                                       |
| ----------------- | ------------------------------------------ | ------------------------------------------ |
| Saves return addr | No                                         | Yes (`_ret_addr_stack`)                    |
| After execution   | continues from target onward               | returns to caller afterward                |
| Call stack effect | none                                       | push once, pop once                        |
| Use cases         | one-way jump, branch merge, error handling | subroutine reuse, modular flow, interrupts |
| Underlying API    | `pc.jump_to(addr)`                         | `pc.call_sub(addr)`                        |

## Usage notes

- **GOTO is not a substitute for loops**: `GOTO` does not provide return semantics. Jumping out of a loop with `GOTO` will not correctly manage the loop state. Use `BreakLoop` for loop exit and `CALL` for reusable subroutines.
- **CALL targets must be addressable**: the target node or entry node must have `address_able=True`, which is required by `ALIAS`.
- **GOTO and CALL share alias space**: both look up aliases in `alias2vector_map`. Avoid alias name conflicts.
- **CALL return depends on stack integrity**: a `GOTO` inside a subroutine sets `_jump_marked`, which can cause `call_sub` to skip stack restoration. Understand that `GOTO` inside a subroutine can override normal return behavior.

## Example

```python
from amrita_sense.instructions import GOTO, CALL, ALIAS, ARCHIVED_NODES
from amrita_sense.node import Node

@Node()
def error_handler():
    print("Handling error")

@Node()
def reusable_step():
    print("Executing reusable logic")

# GOTO: jump to error cleanup
workflow = (
    start
    >> do_something
    >> GOTO("error_cleanup")
    >> ALIAS(error_handler, "error_cleanup")
)

# CALL: reuse a subroutine
subprogram = ARCHIVED_NODES(
    ALIAS(reusable_step, "reusable"),
)

main = (
    init
    >> CALL("reusable")
    >> process
    >> CALL("reusable")
    >> end
    >> subprogram
)
```

> **Manual stack management**: For scenarios requiring explicit control over the return address stack — such as early exit from nested scopes or custom stack unwinding — see the `RET_FAR` instruction documented in [Advanced Topic: Manual Stack Space Management](/guide/practice/manual-stack-management).
