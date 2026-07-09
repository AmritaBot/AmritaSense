# Dependency Injection

The AmritaSense workflow engine integrates the dependency injection (DI) system, providing powerful dependency resolution and injection capabilities for workflow nodes. This integration allows node functions to declare their dependencies, and the engine will automatically resolve and inject those dependencies at execution time.

## 4.1.1 Overview: node and event DI mechanism

In AmritaSense, every workflow node is essentially a callable function. Through dependency injection, these functions can declare the dependencies they require, including:

- **Workflow interpreter instance**: obtained via `POINTER_DEPENDS`
- **Address computation tools**: obtained via `ADDR`, `NEAR_OFFSET`, `FAR_OFFSET` for dynamic node address calculation
- **Custom dependency providers**: any function that returns the required type can act as a dependency provider

The dependency injection system resolves dependencies before node execution and ensures that all declared dependencies are provided. If dependency resolution fails, the workflow throws an exception and terminates.

## 4.1.2 Basic usage: Depends() declaration

Dependency injection is implemented through `Depends()`. `Depends()` accepts a dependency provider function and returns a dependency factory that is called at node execution time to obtain the actual dependency value.

### Syntax

```python
from amrita_sense.hook.matcher import Depends
from amrita_sense.runtime.deps import POINTER_DEPENDS, ADDR, NEAR_OFFSET

@Node()
def my_node(
    dependency_value: ReturnType = Depends(dependency_provider_function)
):
    # use dependency_value
    pass
```

### Built-in dependency tools

AmritaSense provides several built-in dependency helpers in the `amrita_sense.runtime.deps` module:

- `POINTER_DEPENDS`: injects the current `WorkflowInterpreter` instance
- `ADDR(alias)`: injects the absolute address (`PointerVector`) of the specified alias node
- `NEAR_OFFSET(alias)`: injects the near offset (`int`) of the specified alias node
- `FAR_OFFSET(alias)`: injects the far offset (`PointerVector`) of the specified alias node

### Example usage

```python
from amrita_sense.runtime.deps import POINTER_DEPENDS, ADDR, NEAR_OFFSET
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector

@Node()
def navigation_node(
    pc: WorkflowInterpreter = Depends(POINTER_DEPENDS),
    target_addr: PointerVector = Depends(ADDR("my_target")),
    offset: int = Depends(NEAR_OFFSET("my_target"))
):
    # Use the interpreter to jump
    pc.jump_to(target_addr)
    # or use a relative offset for near jumps
    pc.jump_offset(offset)
```

## 4.1.3 Concurrent resolution and runtime injection

AmritaSense’s dependency injection system supports concurrent resolution and runtime injection, which means:

1. **Concurrency-safe**: dependency resolution is thread-safe and can be used safely in concurrent environments.
2. **Runtime dynamism**: dependency values are computed at node execution time, not at workflow compile time.
3. **Context awareness**: dependency provider functions can access the current workflow context.

The dependency injection system automatically handles both synchronous and asynchronous dependency providers. If a provider is asynchronous, the system awaits it; if it is synchronous, it calls it directly.

### Asynchronous dependency example

```python
async def async_dependency():
    await asyncio.sleep(0.1)
    return "async_result"

@Node()
def async_node(result: str = Depends(async_dependency)):
    print(f"Received: {result}")
```

## 4.1.5 Event and hook integration

AmritaSense uses the same dependency matcher for workflow nodes and hook/event handlers. That means event listener callbacks can also declare `Depends(...)` dependencies, and the runtime will resolve them before invoking the callback. This makes it possible to share the same dependency provider functions across normal nodes and external hooks.

```python
from amrita_sense.hook.matcher import Depends

async def on_event(event: Any, pc: WorkflowInterpreter = Depends(POINTER_DEPENDS)):
    # Event handlers can also receive runtime context via Depends
    pass
```

The event/hook system resolves dependencies through the same `MatcherFactory` machinery used by node execution, so the behavior is consistent across the engine.

## 4.1.6 Important behavior: returning None terminates the workflow

The dependency injection system has an important behavior: **if a dependency provider function returns `None`, the workflow terminates immediately**.

This design decision is based on:

1. **Clear failure semantics**: `None` is treated as a clear signal that dependency resolution failed.
2. **Avoid null propagation**: preventing `None` values from spreading through the workflow reduces debugging complexity.
3. **Fail-fast principle**: if a dependency cannot be satisfied, fail immediately rather than continuing with potentially invalid logic.

### Handling optional dependencies

If a dependency can legitimately be absent, use a pattern like:

```python
def optional_dependency():
    if some_condition:
        return "value"
    else:
        return OptionalValue(None)

class OptionalValue:
    def __init__(self, value):
        self.value = value
```

Or handle the conditional inside the node function instead of at the injection layer:

```python
def get_maybe_value():
    if some_condition:
        return "value"
    return "default_value"

@Node()
def safe_node(value: str = Depends(get_maybe_value)):
    pass
```

### Error handling

If a dependency provider returns `None`, the workflow raises a `DependsResolveFailed` exception. This exception can be caught with TRY/CATCH:

```python
def failing_dependency():
    return None

TRY(
    NodeType(lambda: print("This won't execute"))
).CATCH(DependsResolveFailed, NodeType(lambda: print("Caught dependency failure")))
```

This design ensures that dependency injection remains robust and predictable while giving developers a clear error handling mechanism.

## 4.1.7 DI Result Cache (v0.4.2+)

Starting from v0.4.2, the `WorkflowInterpreter` maintains an internal DI result cache (`_di_cache`) to avoid redundant dependency resolution when the same node is executed multiple times with the same argument types.

### How it works

The cache key is a composite of:

- **Pointer hash**: `hash(self._pointer)` — the interpreter's current execution position
- **Args hash**: a fingerprint computed from the types of `_ava_args` and `_ava_kwargs`

The utility function `_fingerprint_args()` generates the args hash by:

1. Extracting `type(arg).__name__` for each positional argument
2. Extracting `(key, type(v).__name__)` for each keyword argument (sorted for stability)
3. Hashing the combined tuple

```python
# Simplified illustration of the cache key
cache_key = hash((hash(pointer), _fingerprint_args(ava_args, ava_kwargs)))
```

The cache payload is an `LRUCache` (from `cachetools`) with a maximum of 1024 entries. When the cache is full, the least recently used entry is evicted.

### Cache lifecycle

- **Initialization**: The cache is created during `WorkflowInterpreter.__init__()` with an initial args hash.
- **Lookup**: Before resolving dependencies for a node, the interpreter checks `_di_cache.payload` for a matching key. On a cache hit, the cached kwargs are used directly, skipping all dependency resolution.
- **Invalidation**: Modifying `_ava_args` or `_ava_kwargs` sets `hash_trustable = False`, indicating the args hash may be stale. Call `rehash_args()` to recompute the hash and restore trust. If the new hash differs from the old one, the entire cache is cleared.
- **Disable**: Set `__flags__.WORKFLOW_DI_NO_CACHE = True` to disable caching entirely.

### Code example

```python
from amrita_sense._unsafe import __flags__
from amrita_sense.runtime.workflow import WorkflowInterpreter

# Default: DI cache enabled
pc = WorkflowInterpreter(rendered, extra_args=(my_service,))
await pc.run()  # Second pass of a loop body will reuse cached DI results

# Disable cache for providers with side effects
__flags__.WORKFLOW_DI_NO_CACHE = True
pc2 = WorkflowInterpreter(rendered)
await pc2.run()  # Every node re-resolves dependencies from scratch
```

## 4.1.8 DI Preload Cache (v0.4.2+)

When `__flags__.WORKFLOW_DI_PRELOAD_CACHE` is enabled, the interpreter pre-resolves dependency injection for **every node** during the `run()` initialization phase — before the first node executes.

### How it works

1. `run()` calls `_refresh_di_cache_full()` after resolving runtime arguments
2. The method walks the entire workflow graph using `advance_pointer()` with a temporary `PointerVector`
3. For each node, it spawns an async worker that resolves DI and stores the result in `_di_cache.payload`
4. Workers run in concurrent batches controlled by `WORKFLOW_DI_PRELOAD_BATCH` (default: 10)
5. After preloading completes, the main loop starts — every `_call()` is a cache hit

### Performance characteristics

| Aspect               | Without preload                      | With preload                             |
| -------------------- | ------------------------------------ | ---------------------------------------- |
| **Startup latency**  | Minimal                              | Proportional to graph size × batch count |
| **Per-node latency** | First visit: full DI resolution      | Always: cache hit (O(1) lookup)          |
| **Memory**           | Grows lazily as nodes are visited    | Pre-allocated for all nodes at startup   |
| **Best for**         | Short workflows, one-shot executions | Long-running loops, repeated node visits |

### Code example

```python
from amrita_sense._unsafe import __flags__

__flags__.WORKFLOW_DI_PRELOAD_CACHE = True
__flags__.WORKFLOW_DI_PRELOAD_BATCH = 20  # Increase parallelism

pc = WorkflowInterpreter(rendered)
await pc.run()  # DI is pre-resolved for all nodes before the first node runs
```

## 4.1.9 Cache Constraints and Flag Conflicts

### `NO_DEPENDENCY_META_CACHE` conflict

Setting `WORKFLOW_DI_PRELOAD_CACHE = True` together with `NO_DEPENDENCY_META_CACHE = True` raises a `RuntimeError`. The preload mechanism depends on cached `DependencyMeta` (from `sign_func`) for efficient batch resolution — disabling the meta cache makes preloading unreliable.

### `WORKFLOW_DI_NO_CACHE` conflict

Setting `WORKFLOW_DI_NO_CACHE = True` together with `WORKFLOW_DI_PRELOAD_CACHE = True` also raises a `RuntimeError`. These flags have contradictory intent: one disables caching, the other pre-populates it.

### `hash_trustable` guard

`_refresh_di_cache_full()` will raise `DependsResolveFailed` if `hash_trustable` is `False` when called. Always call `rehash_args()` after modifying DI arguments to ensure cache integrity.
