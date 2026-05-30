# Core Node Classes

AmritaSense represents workflow logic as node objects. The core node classes are `BaseNode`, `Node`, `NodeCompose`, and `NodeComposeRendered`.

## BaseNode

`BaseNode` is the abstract base class for all workflow nodes. It provides shared metadata, a tag, the underlying callable, and a dependency signature.

Key attributes:

- `tag`: Human-readable node identifier.
- `func`: Underlying callable function or coroutine.
- `wrap_to_async`: Whether sync functions should be executed in an async-friendly way.
- `address_able`: Whether the node can be referenced by alias.
- `fun_sign`: Dependency injection metadata extracted from the callable’s signature.

`BaseNode` also exposes `_pre_check()`, a hook that subclasses can override to perform validation before executing the node.

## Node

`Node` is the concrete wrapper around a Python callable. It is created by the `@Node()` decorator and is the most common executable unit in AmritaSense.

A `Node` preserves the original function signature and adds workflow metadata. Sync functions can be automatically wrapped to async if `wrap_to_async=True`.

Example:

```python
@Node()
def my_node(value: int):
    print(value)
```

Because `Node` implements `__rshift__`, nodes can be composed using `>>`.

## NodeCompose

`NodeCompose` is a container for a sequence of nodes or nested compositions. It is built using the `>>` operator and represents a workflow before rendering.

Example:

```python
a = NodeType(lambda: 1, wrap_to_async=False, address_able=False, tag=None)
b = NodeType(lambda x: x + 1, wrap_to_async=False, address_able=False, tag=None)
workflow = a >> b
```

`NodeCompose.render()` compiles the composition into a `NodeComposeRendered` instance.

## NodeComposeRendered

`NodeComposeRendered` is the compiled, executable workflow graph. It converts nested compositions, alias declarations, and self-compile instructions into a final node structure.

Important features:

- `alias2vector_map`: maps alias names to absolute `PointerVector` addresses.
- `__getitem__`: access nodes by index in the rendered graph.
- `__iter__`: iterate over compiled nodes.

Example:

```python
rendered = workflow.render()
node = rendered[0]
```

`NodeComposeRendered` is the input expected by `WorkflowInterpreter` for execution.
