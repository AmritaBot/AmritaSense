# Dependency Injection

The AmritaSense workflow engine deeply integrates AmritaCore’s dependency injection (DI) system, providing powerful dependency resolution and injection capabilities for workflow nodes. This integration allows node functions to declare their dependencies, and the engine will automatically resolve and inject those dependencies at execution time.

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
from amrita_core.hook.matcher import Depends

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

## 4.1.4 Important behavior: returning None terminates the workflow

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
    Node(lambda: print("This won't execute"))
).CATCH(DependsResolveFailed, Node(lambda: print("Caught dependency failure")))
```

This design ensures that dependency injection remains robust and predictable while giving developers a clear error handling mechanism.
