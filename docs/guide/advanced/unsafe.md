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

Each flag may only be set **once**. Attempting to assign a flag a second time raises `RuntimeError`. This design prevents accidental runtime toggling and ensures consistent behavior throughout the interpreter lifecycle.

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

### `JIT_OPTIMIZE` (v0.4.x+)

```python
JIT_OPTIMIZE: bool = False
```

When enabled, NOP nodes (`_no_operation`) are skipped during `_call()` execution without invoking the full dependency-injection path. This avoids the overhead of an asyncio context switch and lock acquire/release for placeholder nodes.

**When to use**: In workflows with many NOP convergence points (e.g., heavy use of IF/ELIF branching), this flag can reduce per-node overhead.

> **Note**: This flag is marked `# TODO: more optimizations` — additional JIT optimizations may be added in future versions.

## Interaction with Other Systems

Several built-in instructions and the matcher system read flags at key decision points:

| Flag                       | Affected Systems                                                                 |
| -------------------------- | -------------------------------------------------------------------------------- |
| `DISABLE_EXC_IGNORED`      | `TryNode._call()`, `MatcherFactory._resolve()`, `WorkflowInterpreter.__init__()` |
| `ALLOW_CALL_NODECOMPOSE`   | `WorkflowInterpreter._call()`                                                    |
| `NO_DEPENDENCY_META_CACHE` | `WorkflowInterpreter._call()`, `MatcherFactory._prepare()`                       |
| `FORCE_NOT_WRAP_TO_ASYNC`  | `WorkflowInterpreter._call()`                                                    |
| `NO_SHARED_MIDDLEWARE`     | `WorkflowInterpreter.fork_interpreter()`                                         |
| `JIT_OPTIMIZE`             | `WorkflowInterpreter._call()`                                                    |

## Summary

| Flag                       | Default | Effect                                    |
| -------------------------- | ------- | ----------------------------------------- |
| `FORCE_NOT_WRAP_TO_ASYNC`  | `False` | Force sync nodes to stay sync             |
| `DISABLE_EXC_IGNORED`      | `False` | Disable automatic exception penetration   |
| `ALLOW_CALL_NODECOMPOSE`   | `False` | Allow `NodeCompose` to be called directly |
| `NO_DEPENDENCY_META_CACHE` | `False` | Re-resolve dependency metadata each call  |
| `NO_SHARED_MIDDLEWARE`     | `False` | Don't inherit parent middleware in forks  |
| `JIT_OPTIMIZE`             | `False` | Skip NOP nodes during execution           |
