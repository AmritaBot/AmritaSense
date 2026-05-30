# Inline Workflows: Encapsulating Workflows Inside Classes

AmritaSense workflows are typically composed from top-level `@Node()` functions and executed via a standalone `WorkflowInterpreter`. But in real-world applications, you often want to **encapsulate an entire workflow inside a class** — keeping nodes, composition, rendering, and execution all in one reusable unit.

This pattern is called an **inline workflow**.

::: tip LangGraph-style alternative
If you're familiar with LangGraph, inline workflows offer a similar programming experience — Python classes encapsulate graph structures, instance methods serve as nodes, and state lives on `self`. The key differences: AmritaSense skips the `StateGraph` / `add_node` / `add_edge` builder pattern in favor of the `>>` operator, DI automatically feeds inter-node data, and rendering is a single `.render()` call.
:::

## Why Inline Workflows?

| Free-function workflow                         | Inline workflow                                      |
| ---------------------------------------------- | ---------------------------------------------------- |
| Nodes are module-level functions               | Nodes are instance methods of a class                |
| State flows through node outputs               | State lives naturally on `self`                      |
| Composition and interpreter managed externally | Both created and stored inside the class             |
| One-off or global use                          | Instantiate, configure, run — like any Python object |

Inline workflows give you a clean, self-contained unit that can accept constructor parameters, hold mutable fields, and expose a simple `run()` method.

## Core Design

Three rules define the pattern:

1. **Decorate instance methods with `@Node()`** — they become composable workflow nodes. `self` is automatically injected by Python's method binding and does **not** appear in the DI signature.
2. **Compose in `__init__`** — use `>>` to chain nodes together, store the composition as an instance attribute.
3. **Render and create the interpreter in `__init__`** — call `.render()` and construct `WorkflowInterpreter`, storing it for later execution.

## Simplified Example

```python
from amrita_sense.node.core import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter

class SimpleWorkflow:
    """A self-contained workflow: double a value, then format the result."""

    def __init__(self, value: int):
        self.value = value
        self.result: str | None = None

        # Compose, render, create interpreter — all in one place
        rendered = (self.double >> self.format).render()
        self.interpreter = WorkflowInterpreter(rendered)

    @Node()
    async def double(self) -> int:
        """Double the value stored on self."""
        return self.value * 2

    @Node()
    async def format(self, prev: int) -> str:
        """Format the doubled value. `prev` is the return value of `double`."""
        self.result = f"processed: {prev}"
        return self.result

    async def run(self) -> str | None:
        await self.interpreter.run()
        return self.result
```

### Usage

```python
wf = SimpleWorkflow(value=21)
result = await wf.run()
print(result)  # "processed: 42"
```

## Key Points

### `self` is automatic

`@Node()` decorates instance methods normally. Python's method binding injects `self` before the function is called — it never appears in the DI dependency resolution. You don't need `extra_args` or `extra_kwargs` just to pass `self` into your nodes.

### Inter-node data flow via DI

The return value of one node is fed forward and matched by type to the next node's parameter. In the example above, `double` returns `int`, and `format` declares `prev: int` — the DI system matches them automatically.

### Class fields as shared state

Nodes read and write `self.xxx` directly. This is the natural way to share mutable state across nodes without threading return values through every step.

## Real-World Example

AmritaCore's `ChatObject` is a production-grade implementation of the inline workflow pattern: it extends `SuspendObjectStream`, decorates over a dozen instance methods with `@Node()` in `__init__` (`_render_train`, `_limiting_memory`, `_prepare_messages`, `_call_completion`, etc.), chains them into a full pipeline via `>>`, renders and creates the interpreter — all state lives naturally on `self`. The `SimpleWorkflow` above is the simplified core of that design.

## When to Use (and When Not To)

### Good fits for inline workflows

| Scenario                             | Notes                                                                                                       |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| Reusable, configurable workflow unit | Constructor accepts parameters; instantiate and run                                                         |
| Shared mutable state across nodes    | `self` is the natural state container                                                                       |
| Library-style API                    | Expose clear methods like `run()` / `resume()` / `terminate()`                                              |
| Dynamic composition                  | Select node combinations at `__init__` time based on constructor args                                       |
| LangGraph migration                  | If your project already uses class-based graph definitions, inline workflows are the closest migration path |

### When to avoid inline workflows

| Scenario                              | Recommendation                                                                             |
| ------------------------------------- | ------------------------------------------------------------------------------------------ |
| One-off script with 2-3 nodes         | Top-level `>>` composition is faster; no class boilerplate                                 |
| No shared state between nodes         | Free-function workflows are simpler — each node only cares about inputs and outputs        |
| Cross-module composition needed       | Free-function workflows naturally support cross-file imports and mixing                    |
| Team unfamiliar with OOP patterns     | Inline workflows rely on an understanding of `self` and method binding                     |
| Ultra-high-frequency invocation loops | While class instantiation overhead is small, consider it at million-call-per-second scales |
