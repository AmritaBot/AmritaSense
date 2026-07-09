# Unsafe Features

The `amrita_sense._unsafe` module exposes internal engine switches that alter low-level framework behavior. These switches are **not** meant for casual use — they are implementation details surfaced for rare edge cases where the default behavior is insufficient.

::: warning
These flags are **not** covered by Semantic Versioning (SemVer) compatibility guarantees. Their semantics, names, and even existence may change without notice across minor or patch releases. In production environments they should be left at their defaults.
:::

## `__flags__` — The Flag Registry

All flags live in a single `_Flags` dataclass instance named `__flags__`:

```python
from amrita_sense._unsafe import __flags__
```

### One-Time Set, Lock Forever

Most flags may only be set **once**. Attempting to assign a one-time flag a second time raises `RuntimeError`. This design prevents accidental runtime toggling and ensures consistent behavior throughout the interpreter lifecycle.

A small number of flags (listed in the `_writeables` set) are **repeatable** — they can be changed at any time. Currently these are `WORKFLOW_DI_PRELOAD_BATCH` and `WORKFLOW_DI_NO_CACHE`. See [Flag Conflict Detection](#flag-conflict-detection) for rules about mutually exclusive flags.

The recommended practice is to configure flags at the very top of your application entry point, **before** any interpreter is created:

```python
# ✅ Correct: at the top of main.py / __main__.py
from amrita_sense._unsafe import __flags__
__flags__.ALLOW_CALL_NODECOMPOSE = True

# ... rest of your application
```

```python
# ❌ Wrong: this will raise RuntimeError
__flags__.ALLOW_CALL_NODECOMPOSE = True
# ... later ...
__flags__.ALLOW_CALL_NODECOMPOSE = False  # RuntimeError!
```

## Flag Reference

### `FORCE_NOT_WRAP_TO_ASYNC`

```python
FORCE_NOT_WRAP_TO_ASYNC: bool = False
```

By default, nodes whose functions are synchronous but have `wrap_to_async=True` are executed via `asyncio.to_thread()` to avoid blocking the event loop. Setting this flag to `True` forces all such nodes to run synchronously on the event loop thread instead.

**When to use**: In pure-CPU-bound workflows where thread-pool overhead is undesirable and you can tolerate brief event-loop blocks.

### `DISABLE_EXC_IGNORED`

```python
DISABLE_EXC_IGNORED: bool = False
```

By default, `InterruptNotice` and `BreakLoop` are automatically added to `_exc_ignored` so they penetrate all `TRY/CATCH` blocks. The matcher system also respects `exception_ignored` types during dependency resolution. Setting this flag to `True` disables all of this behavior — no exceptions are automatically ignored, and the matcher treats every exception as catchable.

**When to use**: When you need `TRY/CATCH` blocks to intercept `BreakLoop` or `InterruptNotice`, or when you want fully manual control over which exceptions penetrate.

### `ALLOW_CALL_NODECOMPOSE`

```python
ALLOW_CALL_NODECOMPOSE: bool = False
```

By default, calling `_call()` on a `NodeCompose` raises `RuntimeError`. Setting this flag to `True` suppresses that error and allows `NodeCompose` to be invoked directly. This is sometimes useful when a `SelfCompileInstruction` renders a `NodeCompose` that is meant to be called as a single unit.

**When to use**: When your custom `SelfCompileInstruction` needs to call into a `NodeCompose` without wrapping it in a `FUN_BLOCK`.

### `NO_DEPENDENCY_META_CACHE`

```python
NO_DEPENDENCY_META_CACHE: bool = False
```

By default, `FunctionData` caches the resolved `DependencyMeta` (from `sign_func`) on the node's function object. Setting this flag to `True` forces re-resolution of `DependencyMeta` on every call, bypassing the cache.

**When to use**: When you dynamically modify function signatures at runtime (e.g., monkey-patching) and need fresh resolution each time. Comes with a performance cost.

### `NO_SHARED_MIDDLEWARE`

```python
NO_SHARED_MIDDLEWARE: bool = False
```

By default, `fork_interpreter()` inherits the parent's middleware when `middleware=UNSET`. Setting this flag to `True` forces `fork_interpreter()` to pass `None` as middleware unless explicitly overridden.

**When to use**: When you want strict middleware isolation between parent and child interpreters, and prefer an explicit opt-in model.

### `SQUASHED_LOOP` (v0.4.3+)

```python
SQUASHED_LOOP: bool = False
```

When enabled, `WHILE` and `DO-WHILE` loops execute as a single native Python `while` loop instead of bouncing between `WhileNode`/`DONode` → condition → action → `CheckUpNode`/`DowhileNode` via repeated `call_offset`/`jump_near` calls. The entire loop body runs inside one interpreter step, avoiding the overhead of per-iteration pointer advances, lock acquisitions, and jump operations.

**When to use**: In hot-loop scenarios (tight inner loops with many iterations) where per-iteration overhead is measurable and you don't need external interruption at individual loop sub-steps. Note that in squashed mode, `BreakLoop` and `jump_marked` are still respected — jumps to addresses outside the loop structure are not supported.

### `NO_ADDRESSING_CACHE` (v0.4.3+)

```python
NO_ADDRESSING_CACHE: bool = False
```

Disables the `_ptr_cache` in `advance_pointer()`. When `False` (default), the interpreter caches the result of pointer advancement — if the same pointer position is visited again, the cached `base_addr` is reused, avoiding the O(D²) backtracking traversal for nested workflows.

Setting this flag to `True` forces the interpreter to recompute the next pointer position from the graph on every call, bypassing the cache entirely.

**When to use**: During debugging or when workflow graph structure changes dynamically at runtime and cached results may be stale. Disabling the cache also reduces memory usage at the cost of performance.

### `WORKFLOW_DI_NO_CACHE` (v0.4.2+)

```python
WORKFLOW_DI_NO_CACHE: bool = False
```

Disables the DI result cache for workflow execution. When `False` (default), the interpreter caches dependency injection results per node address — if the same node is revisited at the same pointer position with the same DI argument types, the cached kwargs are reused, avoiding repeated dependency resolution.

Setting this flag to `True` forces every node invocation to re-resolve dependencies from scratch, bypassing the `_di_cache` entirely.

**When to use**: When your dependency providers have side effects that must execute on every invocation, or when args change frequently and the cache hit rate is expected to be low. Note that this flag is in `_writeables` and can be toggled at runtime.

### `WORKFLOW_DI_PRELOAD_CACHE` (v0.4.2+)

```python
WORKFLOW_DI_PRELOAD_CACHE: bool = False
```

When enabled, the interpreter pre-resolves dependency injection for **all nodes** in the workflow during the `run()` initialization phase, populating the `_di_cache` before the first node executes. This front-loads all DI resolution work so that individual node invocations during the main loop are cache hits with zero resolution overhead.

**When to use**: In workflows where DI resolution is expensive (e.g., complex type matching, many nodes) and you want predictable, low-latency per-node execution. The trade-off is a one-time startup cost proportional to the size of the workflow graph.

> **⚠️ Conflict**: This flag conflicts with `NO_DEPENDENCY_META_CACHE`. Setting both simultaneously raises `RuntimeError`.

### `WORKFLOW_DI_PRELOAD_BATCH` (v0.4.2+)

```python
WORKFLOW_DI_PRELOAD_BATCH: int = 10
```

Controls the batch size for DI preloading when `WORKFLOW_DI_PRELOAD_CACHE` is enabled. During `_refresh_di_cache_full()`, nodes are resolved in concurrent batches of this size via `asyncio.gather()`. A larger batch increases parallelism but may overwhelm the event loop; a smaller batch is more gradual but takes longer overall.

**When to use**: Tune this value when you need to balance preload speed against event-loop responsiveness. This flag is in `_writeables` and can be adjusted at any time before calling `run()`.

### Flag Conflict Detection (v0.4.2+)

Certain flag combinations are mutually exclusive. The engine enforces this at assignment time — setting a flag that would create a conflict raises `RuntimeError` with a message listing the conflicting flags.

The following conflicts are defined:

| Flag A                      | Flag B                      | Rationale                                                   |
| --------------------------- | --------------------------- | ----------------------------------------------------------- |
| `WORKFLOW_DI_NO_CACHE`      | `WORKFLOW_DI_PRELOAD_CACHE` | Preloading populates a cache that is immediately disabled   |
| `WORKFLOW_DI_PRELOAD_CACHE` | `NO_DEPENDENCY_META_CACHE`  | Preloading relies on cached metadata for efficient batch DI |

The conflict check runs on every flag assignment. It evaluates each conflict group: if all flags in a group would be truthy after the current assignment, the assignment is rejected.

## Interaction with Other Systems

Several built-in instructions and the matcher system read flags at key decision points:

| Flag                        | Affected Systems                                                                 |
| --------------------------- | -------------------------------------------------------------------------------- |
| `DISABLE_EXC_IGNORED`       | `TryNode._call()`, `MatcherFactory._resolve()`, `WorkflowInterpreter.__init__()` |
| `ALLOW_CALL_NODECOMPOSE`    | `WorkflowInterpreter._call()`                                                    |
| `NO_DEPENDENCY_META_CACHE`  | `WorkflowInterpreter._call()`, `MatcherFactory._prepare()`                       |
| `FORCE_NOT_WRAP_TO_ASYNC`   | `WorkflowInterpreter._call()`                                                    |
| `NO_SHARED_MIDDLEWARE`      | `WorkflowInterpreter.fork_interpreter()`                                         |
| `SQUASHED_LOOP`             | `WhileNode._while_worker()`, `DONode._do_worker()`                               |
| `NO_ADDRESSING_CACHE`       | `WorkflowInterpreter.advance_pointer()`                                          |
| `WORKFLOW_DI_NO_CACHE`      | `WorkflowInterpreter._call()`                                                    |
| `WORKFLOW_DI_PRELOAD_CACHE` | `WorkflowInterpreter.run()`, `WorkflowInterpreter._call()`                       |
| `WORKFLOW_DI_PRELOAD_BATCH` | `WorkflowInterpreter._refresh_di_cache_full()`                                   |

## Summary

| Flag                        | Default | Effect                                    |
| --------------------------- | ------- | ----------------------------------------- |
| `FORCE_NOT_WRAP_TO_ASYNC`   | `False` | Force sync nodes to stay sync             |
| `DISABLE_EXC_IGNORED`       | `False` | Disable automatic exception penetration   |
| `ALLOW_CALL_NODECOMPOSE`    | `False` | Allow `NodeCompose` to be called directly |
| `NO_DEPENDENCY_META_CACHE`  | `False` | Re-resolve dependency metadata each call  |
| `NO_SHARED_MIDDLEWARE`      | `False` | Don't inherit parent middleware in forks  |
| `SQUASHED_LOOP`             | `False` | Squash while/do-while into native loops   |
| `NO_ADDRESSING_CACHE`       | `False` | Disable pointer advancement cache         |
| `WORKFLOW_DI_NO_CACHE`      | `False` | Disable DI result caching (repeatable)    |
| `WORKFLOW_DI_PRELOAD_CACHE` | `False` | Pre-resolve DI for all nodes at startup   |
| `WORKFLOW_DI_PRELOAD_BATCH` | `10`    | Batch size for DI preloading (repeatable) |
