# Composition & Execution

## 3.1.1 Nodes

In AmritaSense, the common way to declare a node is using the `@Node()` decorator. For example:

```python
@Node()
def my_fun():...
```

The `Node()` decorator accepts three parameters:

```python
def Node(
    tag: str | None = None,
    wrap_to_async: bool = True,
    address_able: bool = True,
):...
```

**Explanation:**

- `tag`: the node label used to **identify** the node, useful for external breakpoints, debugging, and visualization. See [Execution & Interrupt](/guide/concepts/exec_and_interrupt). Note that tags can be repeated.
- `wrap_to_async`: whether to convert a **synchronous function** into an asynchronous one.
- `address_able`: whether the node is allowed to be referenced by other nodes (via `ALIAS`, which will be covered later).

Using `@Node()` returns a `Node` object. In fact, `Node` is a wrapper class with function metadata. It inherits from `BaseNode`, implements `__call__`, and can also be used like a normal function; the function signature comes from the original function.

So how do we chain nodes together? That brings us to composition.

## 3.1.2 Composition

A single node cannot execute on its own. We need to compose it; composition links nodes together and defines their positional relationship. In AmritaSense, we can use the `>>` operator to define ordering between nodes, for example:

```python
compose: NodeCompose = node1 >> node2
```

After composing, the next step is **rendering** (or “compiling”). Since `.render()` returns a new object `NodeComposeRendered`, this step should be assigned to a variable:

```python
comp_rendered: NodeComposeRendered = compose.render()
```

At this point, the preparation is complete. The next step is to run it.

## 3.1.3 Execution

The rendered composition is essentially a **data container containing nodes**. Execution requires an interpreter. Here we introduce the concept of `WorkflowInterpreter`. Before that, let’s inspect its constructor:

```python
def __init__(
    self,
    node_compose: NodeComposeRendered | SelfCompileInstruction,
    object_io: SuspendObjectStream[Any] | None = None,
    *,
    exception_ignored: tuple[type[BaseException], ...] = (),
    extra_args: tuple = (),
    extra_kwargs: dict[str, Any] | None = None,
    addr_stack: Stack[PointerVector] | None = None,
):...
```

### Parameters before `*`

- `node_compose`: the node composition, which can be `NodeComposeRendered` or `SelfCompileInstruction` (you do not need to know what self-compiled instructions are yet. We will cover them later in advanced chapters. For now, just know that `IF()`, `WHILE`, and other control flow instructions are `SelfCompileInstruction`, and they automatically expand into node compositions).
- `object_io`: an object input/output stream used for object I/O. See [AmritaCore-IOStream](https://core.amritabot.com/zh/guide/api-reference/classes/SuspendObjectStream.html).

### Keyword-only parameters after `*`

These parameters must be passed as kwargs, not args.

- `exception_ignored`: a tuple containing exception types to ignore. Ignored exceptions will not be caught by internal exception chains and are rethrown. The default is `(InterruptNotice, BreakLoop)`.
- `extra_args`: a tuple of extra positional arguments. These arguments are passed to internal functions by type-bound dependency injection.
- `extra_kwargs`: a dictionary of extra keyword arguments. These are also passed by type-bound dependency injection.

The dependency injection details are explained in [Dependency Declaration](/guide/concepts/compose_and_exec#3.1.4-dependency-declaration) later.

### Running the workflow

There are two ways to execute:

1. Use the `run()` method to run the full workflow.
2. Use `run_step_by()` as an async generator to run node by node.

Example:

```python
inter = WorkflowInterpreter(...)
if __name__ == '__main__':
    inter.run()
# or:
async def main():
    inter = WorkflowInterpreter(...)
    async for resp in inter.run_step_by():
        # resp can actually obtain the output of each node
        ...

if __name__ == '__main__':
    asyncio.run(main())
```

## 3.1.4 Dependency declaration

This is an abstract concept, but if you have used frameworks like `FastAPI` or `NoneBot2`, you will quickly understand how dependency resolution works in AmritaSense. If not, don’t worry — we will unpack it step by step.

**In short**: a node function’s parameters need values from outside. These values can be constants, outputs from other nodes, or global dependencies provided by the `WorkflowInterpreter`. AmritaSense automatically fills them based on parameter types and names.

### What counts as a “dependency”?

Suppose you have a function `my_fun` defined as:

```python
async def my_fun(a: int, b: int) -> int:
    return a + b
```

This function depends on `a` and `b` and returns an integer. We call these formal parameters declarations of **dependencies**.

Dependency injection and matching can be abstractly understood as the process of dynamically binding provided values to parameters.

### Passing and binding arguments

Arguments are passed through `extra_args` and `extra_kwargs` in the `WorkflowInterpreter` constructor. What do they do?

- `extra_args`: available positional arguments are matched by **parameter type** and **function parameter type**.
- `extra_kwargs`: available keyword arguments are matched by **parameter name** and **function parameter name**. It has higher priority than `extra_args` and does not perform type matching.

::: tip
If any parameter fails to resolve during execution, the workflow will terminate.
:::

This may still feel abstract, so here is an example:

```python
# assume you have a tuple a and a dict b
a = (MyType(), MyOtherType())
b = {"arg": MyOtherType()}
# define a node my_func
@Node()
def my_func(arg: MyType):...

interpreter = WorkflowInterpreter(my_func >> NOP, extra_args=a, extra_kwargs=b)

...
```

In this example, `extra_kwargs` is tried first, but `b["arg"]` has type `MyOtherType` which does not match the signature's `MyType`. Matching then falls back to `extra_args` and scans in order, skipping the first mismatch and finding the first `MyType` instance. If no match is found, an error is raised.

Let’s look at a second example:

```python
from amrita_sense.instructions import NOP
# assume you have a tuple a and a dict b
a = (MyOtherType(),)
b = {"other_arg": MyType()}
# define a node my_func
@Node()
def my_func(arg: MyType):...

interpreter = WorkflowInterpreter(my_func >> NOP, extra_args=a, extra_kwargs=b)

...
```

This program will raise an error because `extra_kwargs` cannot be matched by type, and `extra_args` does not contain a value of the same type.

::: warning
Note that function signatures cannot use `*args` or `**kwargs`, because those parameters cannot be matched. Also, parameters injected via `extra_args` **must** declare a type in the formal parameters, otherwise an error will occur.
:::
