# Exception System

AmritaSense defines a lean, purpose-specific exception hierarchy for handling various errors and interruptions during workflow execution. Each exception type has clear semantic boundaries and usage constraints.

## InterruptNotice

```python
class InterruptNotice(BaseException):
    """Special exception for immediate workflow termination.

    Raised by the INTERRUPT node or external systems. As a BaseException
    subclass, it bypasses regular CATCH blocks and penetrates directly to
    the interpreter's top-level handler, ensuring clean and unconditional
    termination.
    """
```

**Why inherit from `BaseException`**

Python's `except Exception` does not catch `BaseException` subclasses. Therefore, no `TRY/CATCH` block in the workflow can intercept `InterruptNotice` by default. This is an intentional design choice — `INTERRUPT` must be an "uncatchable" emergency termination signal. The only exception is explicitly adding `InterruptNotice` to `exception_ignored`, at which point it becomes catchable as a regular exception.

**Trigger methods**

- **Composition level**: Automatically raised when execution reaches an `INTERRUPT` node.
- **External injection**: External systems can directly `raise InterruptNotice()`; the interpreter catches and terminates at the next node boundary.

**Interpreter response**

When the interpreter main loop catches `InterruptNotice`:

1. Logs the current pointer position and notification message
2. Clears `_ret_addr_stack` (the call stack)
3. Resets `_pointer` (the pointer vector)
4. Resets the `_jump_marked` flag
5. The workflow exits cleanly with no residual state

## InterruptKeepContext (v0.4.x+)

`InterruptKeepContext` is a subclass of `InterruptNotice` that terminates workflow execution while **preserving interpreter state**. Unlike `InterruptNotice`, which triggers a full `reset()`, this exception leaves the pointer, call stack, and dependency injection parameters intact.

Use cases:

- Pause-inspect-resume debugging
- Checkpoint-restart workflows
- Triggered by the `INTERRUPT_KEEP_CTX` instruction node

## NullPointerException

```python
class NullPointerException(Exception):
    """Raised when a node cannot be located at a given address.

    This occurs when jump operations reference non-existent nodes,
    invalid address vectors, or aliases that failed to resolve.
    """
```

**Trigger scenarios**

- A GOTO, CALL, or other jump instruction's target address does not exist in the `NodeComposeRendered`.
- An alias lookup fails in `alias2vector_map` (at which point `JumpNode` and `CallNode`'s `_post_compile` raises `AliasNotFoundError`).
- An out-of-bounds index is accessed at runtime via `find_addr`.

**Relationship with alias validation**

`NullPointerException` is the fallback exception for runtime address failures. In practice, when using `ALIAS` + `GOTO`/`CALL` for normal addressing, typos are caught at compile time during `_post_compile` with correction suggestions. Only raw `list[int]` addresses that are invalid at runtime will raise this exception.

## BreakLoop

```python
class BreakLoop(Exception):
    """Exception used to break out of WHILE or DO-WHILE loop constructs.

    When raised within a loop body, the loop terminates immediately and
    execution continues after the loop's NOP exit point.
    """
```

**Automatic penetration mechanism**

`BreakLoop` is automatically added to the `_exc_ignored` tuple during `WorkflowInterpreter` initialization. This means:

- Any `TRY/CATCH` block inside a loop body **cannot** catch `BreakLoop`.
- It penetrates all intermediate exception handling layers and reaches the innermost `WhileNode` or `DONode`.
- The loop node catches `BreakLoop` and executes `jump_near(NOP)`, exiting cleanly.

> **v0.3.0+**: This auto-inclusion can be disabled via `__flags__.DISABLE_EXC_IGNORED = True` from `amrita_sense._unsafe`. See [Unsafe Features](../../guide/advanced/unsafe.md) for details.

**Usage**

Simply raise it inside the `ACTION` or `DO` node of a loop body:

```python
@Node()
def process_item():
    if item is None:
        raise BreakLoop  # No more data; exit the loop
    if item.should_skip:
        return  # Equivalent to continue
    handle(item)
```

**Note**: Developers should **not** manually add `BreakLoop` to `exception_ignored` — it is already added automatically during interpreter initialization. Adding it again has no additional effect; attempting to remove it would cause `CATCH` blocks inside loops to accidentally capture `BreakLoop`, breaking loop semantics.

## IllegalState (v0.3.0+)

Raised when an operation is attempted in an invalid state. Common triggers:

- Calling `terminate_all()` or `wait_all()` on a non-top-level interpreter
- Starting `run()` on an interpreter that is already running
- Accessing `wait` on an interpreter that is not running
- Violating TRY/CATCH syntax constraints (e.g., adding CATCH after FINALLY, duplicate THEN)

See [Subgraph Isolation](../../guide/practice/subgraph-isolation.md) for correct usage patterns.

## DependsException and subclasses

All dependency injection exceptions inherit from `DependsException`.

```python
class DependsException(Exception):
    """Base class for all dependency injection related exceptions."""
```

### AliasNotFoundError (v0.4.x+)

Raised when a GOTO or CALL instruction references an alias that does not exist in the workflow graph's alias registry. Detected at compile time during `_post_compile`. Replaces the generic `RuntimeError` / `ValueError` previously used for alias resolution failures.

### DependsResolveFailed

```python
class DependsResolveFailed(Exception):
    """Raised when a node's dependencies cannot be resolved.

    This occurs when required parameters in the function signature
    cannot be matched to any available dependency source.
    """
```

**Trigger conditions**

- A node's function signature has an unmatched parameter (no dependency source of matching type, and no default value).
- Multiple dependency sources match the same parameter and cannot be disambiguated.

### DependsInjectFailed

```python
class DependsInjectFailed(Exception):
    """Raised when runtime dependency injection fails during node execution.

    This typically occurs when a Depends factory function raises an
    exception that is not in the exception_ignored tuple.
    """
```

**Trigger conditions**

- A `Depends` factory function raises an exception at runtime that is not in `_exc_ignored`.
- When resolving multiple dependencies concurrently, all failures are collected into an `ExceptionGroup` and re-raised.

**Critical behavior: `Depends` returning `None` terminates immediately**

Unlike the event system's "return `None` to skip" behavior, in node execution, if a dependency factory declared via `Depends` returns `None`, the workflow **raises an exception and terminates immediately**. Nodes are atomic execution units, and dependency resolution failure means the node cannot run — this is not a "skip" scenario. Therefore, dependency factory functions designed for nodes should always return a valid value (or raise an explicit exception when unable to provide one, rather than returning `None`).

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

## Exception Hierarchy

```text
BaseException
├── InterruptNotice          # Inherits BaseException; uncatchable by CATCH by default
│   └── InterruptKeepContext  # Interrupts but preserves interpreter context

Exception
├── IllegalState              # Invalid state operation
├── NullPointerException      # Invalid address
├── BreakLoop                 # Loop exit signal
├── AliasNotFoundError        # Alias resolution failure
├── GraphBuildError           # Graph build/render failure
├── StreamStateError          # Stream operation in illegal state
└── DependsException          # Dependency injection base class
    ├── DependsResolveFailed   # Dependencies cannot be resolved
    └── DependsInjectFailed    # Exception during dependency injection
```

**Design principles**:

- `InterruptNotice` inherits from `BaseException`, achieving natural uncatchability.
- `InterruptKeepContext` inherits from `InterruptNotice`, preserving context for later recovery.
- `BreakLoop` inherits from `Exception`, but gains equivalent penetration capability through automatic inclusion in `_exc_ignored`.
- `IllegalState` was added in v0.3.0 to protect interpreter tree API call validity and instruction syntax constraints.
- `AliasNotFoundError` / `GraphBuildError` / `StreamStateError` are fine-grained exception types added in v0.4.x+.
- All dependency-related exceptions inherit from `DependsException`, allowing users to catch the entire dependency error category as needed.

## `search_exceptions()` (v0.3.0+)

```python
from amrita_sense.utils import search_exceptions

def search_exceptions(
    seq: Sequence[BaseException | list | None],
) -> list[BaseException]
```

Recursively searches a sequence (potentially containing nested lists of exceptions) and returns a flat list of all `BaseException` instances. Used internally by `FUN_BLOCK` to collect exceptions from sub-interpreter trees.
