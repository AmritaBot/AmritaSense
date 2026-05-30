# Minimal Example

## 2.2.1 Example

### Code example

```python
import asyncio
from amrita_sense import Node, WorkflowInterpreter, NOP

@Node()
async def my_fun():
    print("hello world")

comp = my_fun >> NOP
graph = comp.render()

interpreter = WorkflowInterpreter(graph)

if __name__ == "__main__":
    asyncio.run(interpreter.run())
```

### Explanation

In this example, we use the `@Node()` decorator to create a node named `my_fun`. `Node` accepts both synchronous and asynchronous functions; we will cover its usage in detail later.

A single node cannot run by itself, so we need to compose nodes into a complete workflow. In the example, we append a reference to an empty node and use the `>>` operator to link it to the `NOP` node.

We use the `render()` method to convert the workflow into an executable data structure, then create a `WorkflowInterpreter` object and pass that data to it.

`WorkflowInterpreter` is the workflow interpreter and scheduler runtime, and we use it to execute the workflow.

Finally, we launch the workflow with `asyncio.run(interpreter.run())`. If everything goes well, you should see logs in the console and a "Hello, World!" message.

> **More examples**: See the `demos/` directory in the source repository for more standalone, runnable examples covering all core features.
