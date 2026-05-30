# 最小示例

## 2.2.1 示例

### 代码示例

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

### 解析

在这个示例中，我们使用`@Node()`装饰器来创建了一个名为`my_fun`的节点。`Node`接受同步和异步函数，有关详细使用我们会在之后的篇章中提及。

但是单个节点不能直接运行，我们需要将它们组合成一个完整的工作流。在示例，我们在末尾添加了一个空节点的引用，并使用`>>`运算符将其链接到`NOP`节点。

我们使用`render()`方法将工作流转换为可执行的数据结构，并创建一个`WorkflowInterpreter`对象，将数据传递给它。

`WorkflowInterpreter`是工作流的解释与调度运行时，我们使用它来执行工作流。

最后，我们使用`asyncio.run(interpreter.run())`启动工作流。如果不出意外，您会在控制台看到日志和一个“Hello, World!”消息。

> **更多示例**：源码仓库的 `demos/` 目录包含了更多覆盖全部核心功能的可独立运行示例。
