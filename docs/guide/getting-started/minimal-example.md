# Minimal Example

## 2.2.1 Example

### Code example

```python
import asyncio
from amrita_sense import Node, WorkflowInterpreter


@Node()
async def my_fun():
    print("hello world")


comp = my_fun.as_compose()  # a single node is composed via as_compose()
graph = comp.render()

interpreter = WorkflowInterpreter(graph)

if __name__ == "__main__":
    asyncio.run(interpreter.run())
```

### Explanation

In this example, we use the `@Node()` decorator to create a node named `my_fun`. `Node` accepts both synchronous and asynchronous functions; we will cover its usage in detail later.

A single node cannot run by itself, so we wrap it with `as_compose()` to turn it into a workflow. When composing multiple nodes, use the `>>` operator (`node1 >> node2`). No trailing `NOP` sentinel is needed — the interpreter simply finishes when the workflow reaches its end.

We use the `render()` method to convert the workflow into an executable data structure, then create a `WorkflowInterpreter` object and pass that data to it.

`WorkflowInterpreter` is the workflow interpreter and scheduler runtime, and we use it to execute the workflow.

Finally, we launch the workflow with `asyncio.run(interpreter.run())`. If everything goes well, you should see logs in the console and a "Hello, World!" message.

> **More examples**: See the `demos/` directory in the source repository for more standalone, runnable examples covering all core features.
