# Flow Control

After understanding the address space, pointer vectors, and node jumps, we can dive into AmritaSense’s **flow control** capabilities. This is the core competitive advantage of AmritaSense as a general-purpose workflow orchestration engine. It provides a complete, Turing-complete set of control flow primitives, so you can orchestrate arbitrarily complex asynchronous tasks with an intuition close to that of a programming language.

## 3.3.1 Conditional branching

AmritaSense is natively Turing-complete, and it includes a first-class conditional branching syntax. Unlike graph-based workflow engines that simulate branching with “routing functions + string maps,” AmritaSense makes conditional branches a built-in primitive.

### Basic usage

The `IF` primitive supports the following patterns:

```python
IF(condi, do)                        # basic IF, execute do when condition is true
IF(condi, do).ELSE(else_do)          # IF-ELSE branch
IF(condi, do).ELIF(condi2, do2)      # IF-ELIF chain
IF(condi, do).ELIF(condi2, do2).ELSE(else_do)  # full IF-ELIF-ELSE chain
```

It fully reproduces Python-style `elif` chain syntax. The number of `ELIF` entries in the syntax chain is unlimited and can expand arbitrarily. Each `ELIF` is automatically expanded into standard address-jump triplets at compile time, so runtime execution requires no string matching or dictionary lookup.

### Key features

- **The underlying type of each condition is `Node[bool]`**: the condition expression itself is also a node. That means the condition can be a simple function, an asynchronous function, or even a complex node with dependency injection. This design ensures the philosophy of “everything is a node” is consistent throughout.
- **Seamless sync/async mixing**: whether the condition returns `bool` synchronously or returns an awaitable `bool` asynchronously, the engine normalizes it to a unified execution interface automatically.
- **Static address calculation at compile time**: all branch jump offsets are computed during `render()`, so runtime execution only involves pointer vector arithmetic. There is no graph traversal or string hashing overhead.

## 3.3.2 Loops

AmritaSense natively includes node-level loop primitives and supports two standard loop paradigms: `WHILE` and `DO-WHILE`. Both align with classic programming language semantics and treat the loop condition itself as a composable node.

### WHILE statement

The semantic behavior is the same as Python’s `while ...:` conditional loop: first evaluate the condition, then execute the loop body if it is true, and repeat.

```python
WHILE(condition).ACTION(action_node)
```

Key point: **the loop condition itself is an independent composable node**. This is very different from frameworks that hardcode the condition into a routing function. Your condition can be arbitrary async logic, can accept dependency injection, and can be suspended before evaluation.

### DO-WHILE statement

Python does not have native `do-while` syntax, but its behavior is equivalent to C’s `do-while`. The core semantics are: **execute the `DO` block at least once, then evaluate the condition**.

```python
DO(do_node).WHILE(condition)
```

This is useful when you need to “execute first, then check” — for example, send an initial network request and decide whether to retry based on the response.

### Breaking out of a loop

If you need to terminate a loop early (equivalent to `break`), you can raise `BreakLoop` inside the `ACTION` or `DO` node. The outer `WHILE` or `DO-WHILE` will catch that signal and cleanly terminate the loop instance.

```python
@Node()
def early_exit():
    if some_condition:
        raise BreakLoop
    do_something()
```

### Equivalent of `continue`

Sense loops do not provide a native `continue` keyword, but they support a zero-cost equivalent: simply `return` early from the current node. The interpreter will naturally advance to the next loop condition check (or to the loop entry point), yielding behavior equivalent to `continue`.

## 3.3.3 Exception handling

AmritaSense natively provides a **node-domain TRY/CATCH exception handling system**. This is a capability that traditional workflow engines often lack. In AmritaSense, exception handling is a first-class citizen alongside conditionals and loops.

### Full usage

```python
TRY(do).CATCH(exc, handler)                              # catch a specific exception
TRY(do).FINALLY(cleanup)                                  # finally block only
TRY(do).CATCH(exc, handler).FINALLY(cleanup)              # catch + cleanup
TRY(do).THEN(success).CATCH(exc, handler).FINALLY(cleanup) # full four-part structure
TRY(do).CATCH(exc, handler).THEN(success)                 # catch + success branch
TRY(do).CATCH(exc1, handler1).CATCH(exc2, handler2).FINALLY(cleanup)  # multiple catches
```

The overall logic is highly aligned with Python’s `try-except-else-finally`. The differences are:

- Use `CATCH` to declare the exception type to catch and a corresponding handler node.
- Use `THEN` as the equivalent of Python’s `else` branch — it executes only if the `TRY` block completes without an exception.

### Syntax constraints

1. `TRY` must be followed by at least one `CATCH` or `FINALLY`.
2. A single `TRY` structure can define at most one `FINALLY` and one `THEN`.
3. `CATCH` may be defined multiple times. The engine uses a **top-to-bottom short-circuit** matching rule — the first matching `CATCH` is executed and later catches are ignored.

### Special exception penetration rules

Unlike general-purpose languages, AmritaSense introduces an **exception penetration mechanism**. If a type is marked in `WorkflowInterpreter`’s `exception_ignored` parameter, that exception will be skipped by the current layer of `CATCH` blocks and will **propagate upward to the global handler**.

```python
pc = WorkflowPC(nd, exception_ignored=(CriticalError,))
```

This design lets developers mark exceptions as “non-recoverable” or “globally handled,” ensuring they are not accidentally swallowed by intermediate `CATCH` logic. This is important for complex, multi-layered workflows — local fault tolerance should not intercept critical signals.

### Summary

From conditionals and loops to exception handling, AmritaSense’s flow control system covers all core structured programming paradigms. These capabilities are not “simulated” through an external DSL or graph topology; they are directly encoded as first-class primitives in the instruction set and interpreter. In the next chapter, we will explore execution and interrupt control at runtime.
