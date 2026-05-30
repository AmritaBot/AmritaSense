# TRY / CATCH / THEN / FIN Exception Handling

AmritaSense provides a complete exception handling instruction system that aligns closely with Python’s `try-except-else-finally`. Before using it, ask yourself: **when should you use instruction-based exception handling, and when should you write `try-except` inside a node?**

## Choosing between two exception handling modes

### Inline try-catch inside a node

When exception handling is tightly coupled with the current node, or the handling logic is very simple, write Python native try-catch inside the node:

```python
@Node()
async def fetch_data():
    try:
        response = await http_get("/api/data")
        return response.json()
    except TimeoutError:
        return get_cached_data()
```

**Use this when**:

- the handling logic is tightly coupled with normal logic
- the fallback is simple
- the exception type is a standard Python exception and does not need dependency injection or interrupt control

### Instruction orchestration mode (TRY/CATCH/THEN/FIN)

When exception handling is an independent, reusable workflow step, or when you want to leverage AmritaSense capabilities like dependency injection, suspension, and exception penetration, use instruction-based orchestration:

```python
TRY(call_api).CATCH(TimeoutError, use_cache).CATCH(AuthError, refresh_token).FINALLY(cleanup)
```

**Use this when**:

- exception handling itself is a reusable node sequence
- handling logic needs dependency injection (database connection, logger, etc.)
- the handler should be suspendable or interruptible
- you want to control exception penetration with `exception_ignored`
- multiple catch branches are needed and each is complex enough to be an independent node

### Decision guide

| Scenario                                        | Recommended mode                      |
| ----------------------------------------------- | ------------------------------------- |
| Handling logic is 1-2 lines and tightly coupled | inline node try-catch                 |
| Handling logic is an independent reusable step  | instruction-based TRY/CATCH           |
| Handler requires dependency injection           | instruction-based                     |
| Handler requires suspension/interrupt control   | instruction-based                     |
| Exception type should penetrate local handlers  | instruction-based + exception_ignored |
| Simple resource cleanup                         | inline try-finally or TRY/FINALLY     |

> **Core principle**
> Use Python for exceptions that belong inside a node. Use instructions for workflow-level exception control. They can be mixed — a TRY block may contain nodes that use their own inline try-catch.

## Instruction syntax and semantics

### Full syntax

```python
TRY(do).CATCH(exc, handler)
TRY(do).FINALLY(cleanup)
TRY(do).CATCH(exc, handler).FINALLY(cleanup)
TRY(do).THEN(success).CATCH(exc, handler).FINALLY(cleanup)
TRY(do).CATCH(exc, handler).THEN(success)
TRY(do).CATCH(exc1, handler1).CATCH(exc2, handler2).FINALLY(cleanup)
```

### Semantic mapping

| Instruction           | Python equivalent     | Execution condition                             |
| --------------------- | --------------------- | ----------------------------------------------- |
| `TRY(do)`             | `try: do`             | always execute first                            |
| `CATCH(exc, handler)` | `except exc: handler` | execute when a matching exception occurs        |
| `THEN(node)`          | `else: node`          | execute only if TRY completes without exception |
| `FINALLY(node)`       | `finally: node`       | execute whether or not an exception occurs      |

### Syntax constraints

1. `TRY` must be followed by at least one `CATCH` or `FINALLY`.
2. A single `TRY` structure may define at most one `FINALLY` and one `THEN`.
3. `CATCH` may appear multiple times and is matched top-to-bottom with short-circuit behavior.

## Runtime execution logic

`TryClause` is a `SelfCompileInstruction` and expands at compile time into:

```text
[TryNode, try_body, ..., CatchHandler_1, catch_body_1, ..., FinNode(opt), fin_body(opt), NOP(escape)]
```

The `NOP` at the end is an **escape sentinel** — every execution path (success, caught, uncaught, finally) ends with `pc.jump_near(self._escape_addr)` to reach it. This ensures control never falls through into the next instruction in the enclosing composition.

The runtime behavior of `TryNode` is:

1. **Execute the TRY block** via `call_near`.
2. **If no exception occurs**:
   - if `THEN` is defined, call `then_body` via `call_near`
3. **If an exception occurs**:
   - `TryNode` catches `BaseException`
   - if the exception type is in `_exc_ignored`, it is re-raised immediately
   - iterate through `_catch_addr_chain` and match exception types with `isinstance`
   - execute the first matching `CATCH` block via `call_near`
   - if no catch matches, re-raise the exception
4. **Regardless of exception**: the `finally` block executes via `call_near` if defined.
5. **After all blocks complete**: jump to the escape NOP sentinel via `pc.jump_near(self._escape_addr)`.

## Exception penetration rules

When the `WorkflowInterpreter` is initialized with `exception_ignored`, those exception types are not caught by any `CATCH` block:

```python
pc = WorkflowInterpreter(
    workflow,
    exception_ignored=(CriticalError, InterruptNotice, BreakLoop)
)
```

When `TryNode` encounters one of these exceptions, it re-raises it immediately, allowing it to propagate upward. This ensures:

- **`InterruptNotice`** can terminate the entire workflow and is not swallowed by a local TRY.
- **`BreakLoop`** can jump out of the innermost loop and is not intercepted by intermediate exception handlers.
- **Critical errors** can bypass local fault tolerance and reach a global handler.

## Usage examples

### Instruction orchestration: API call fault tolerance

```python
@Node()
async def call_api():
    return await http_get("/api")

@Node()
async def use_cache():
    return get_cached()

@Node()
async def cleanup():
    http_client.close()

api_flow = TRY(call_api).CATCH(TimeoutError, use_cache).FINALLY(cleanup)
```

### Inline node fallback

```python
@Node()
async def call_api_simple():
    try:
        return await http_get("/api")
    except TimeoutError:
        return get_cached()
```

### Multiple exception handling

```python
TRY(risky_op)\
    .CATCH(ValueError, handle_value)\
    .CATCH(TypeError, handle_type)\
    .CATCH(Exception, handle_unknown)\
    .FINALLY(cleanup)
```

### Ensure cleanup even without exceptions

```python
TRY(acquire_resource).FINALLY(release_resource)
```

## Dependency injection in exception handlers

Nodes in `CATCH`, `THEN`, and `FINALLY` blocks can use `Depends` normally. The caught exception object itself can also be injected into a handler node — this is a unique advantage of instruction-based exception handling over inline try-catch.

> **About `Depends` returning `None`**
> If a handler node declares a dependency via `Depends` and the provider returns `None`, the workflow raises an exception and terminates. Dependency resolution failure is not a recoverable skip. Exception handler nodes should ensure that required dependencies can be resolved on all execution paths.
