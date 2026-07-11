# Exception System

AmritaSense defines a small set of runtime exceptions used by the interpreter, dependency injection, and control flow primitives.

## InterruptNotice

`InterruptNotice` is a `BaseException` subclass used to terminate workflow execution immediately. It bypasses normal `Exception` handlers and is caught by the interpreter at the top level.

Use cases:

- external stop requests
- emergency termination points in the workflow

## InterruptKeepContext (v0.4.x+)

`InterruptKeepContext` is a subclass of `InterruptNotice` that terminates workflow execution while **preserving interpreter state**. Unlike `InterruptNotice`, which triggers a full `reset()`, this exception leaves the pointer, call stack, and dependency injection parameters intact.

Use cases:

- Pause-inspect-resume debugging
- Checkpoint-restart workflows
- Triggered by the `INTERRUPT_KEEP_CTX` instruction node

## NullPointerException

Raised when a node cannot be found at a specified address or when an alias does not exist.

## BreakLoop

Used internally by loop constructs to implement break semantics. Raising `BreakLoop` exits the current loop body and continues execution after the loop.

`BreakLoop` is automatically added to `_exc_ignored` on interpreter init, so it penetrates through all `CATCH` blocks. **v0.3.0+**: This auto-inclusion can be disabled via `__flags__.DISABLE_EXC_IGNORED = True` from `amrita_sense._unsafe`.

## DependsException

Base exception for all dependency injection failures.

## AliasNotFoundError (v0.4.x+)

Raised when a GOTO or CALL instruction references an alias that does not exist in the workflow graph's alias registry. This is detected at compile time during `_post_compile`. Replaces the generic `RuntimeError` / `ValueError` that were previously used for alias resolution failures.

## DependsResolveFailed

Raised when dependency resolution fails for a node or callback. This can happen when a required dependency is missing or cannot be matched.

Inherits from: `DependsException`

## IllegalState (v0.3.0+)

Raised when an operation is attempted in an invalid state. Common triggers:

- Calling `terminate_all()` or `wait_all()` on a non-top-level interpreter
- Starting `run()` on an interpreter that is already running
- Accessing `wait` on an interpreter that is not running
- Violating TRY/CATCH syntax constraints (e.g., adding CATCH after FINALLY, duplicate THEN)

See [Subgraph Isolation](../../guide/practice/subgraph-isolation.md) for correct usage patterns.

## DependsInjectFailed

Raised when dependencies are resolved successfully but cannot be injected into the target function due to mismatched parameters or runtime resolution failures.

Inherits from: `DependsException`

## GraphBuildError (v0.4.x+)

Raised when workflow graph building or rendering fails. Common triggers:

- Duplicate alias names in the same composition
- Attempting to build an already-built `NodeComposeRendered`
- Missing original graph during rendering

## StreamStateError (v0.4.x+)

Raised when a `SuspendObjectStream` operation is attempted in an invalid state. Common triggers:

- Pushing to a closed queue
- Calling `wait_to_suspend()` when already waiting
- Setting a callback function twice
- Calling `get_response_generator()` when already being consumed

## `search_exceptions()` (v0.3.0+)

```python
from amrita_sense.utils import search_exceptions

def search_exceptions(
    seq: Sequence[BaseException | list | None],
) -> list[BaseException]
```

Recursively searches a sequence (potentially containing nested lists of exceptions) and returns a flat list of all `BaseException` instances. Used internally by `FUN_BLOCK` to collect exceptions from sub-interpreter trees.
