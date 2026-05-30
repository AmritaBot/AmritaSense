# 内联工作流：将工作流封装在类中

AmritaSense 工作流通常由顶层 `@Node()` 函数编排而成，通过独立的 `WorkflowInterpreter` 执行。但在实际应用中，你常常希望将**整个工作流封装在一个类中**——将节点、编排、渲染和执行全部集中在一个可复用的单元里。

这种模式称为**内联工作流**。

::: tip LangGraph 风格替代方案
如果你熟悉 LangGraph，内联工作流提供了一种与之类似的编程体验——用 Python 类封装图结构，实例方法作为节点，状态挂在 `self` 上。但区别在于：AmritaSense 不需要 `StateGraph` 或 `add_node` / `add_edge` 的建造者模式，直接用 `>>` 运算符编排，DI 自动传递节点间数据，渲染仅需一行 `.render()`。
:::

## 为什么使用内联工作流？

| 自由函数工作流         | 内联工作流                                 |
| ---------------------- | ------------------------------------------ |
| 节点是模块级函数       | 节点是类的实例方法                         |
| 状态通过节点输出传递   | 状态自然地存在于 `self` 上                 |
| 编排和解释器在外部管理 | 二者均在类内部创建和存储                   |
| 一次性或全局使用       | 实例化、配置、运行——像普通 Python 对象一样 |

内联工作流提供了一个干净、自包含的单元，可以接受构造参数、持有可变字段，并对外暴露简单的 `run()` 方法。

## 核心设计

该模式遵循三条规则：

1. **用 `@Node()` 装饰实例方法**——它们成为可编排的工作流节点。`self` 由 Python 方法绑定机制自动注入，**不会**出现在 DI 签名中。
2. **在 `__init__` 中编排**——用 `>>` 串联节点，将编排结果存储为实例属性。
3. **在 `__init__` 中渲染并创建解释器**——调用 `.render()` 并构造 `WorkflowInterpreter`，存储供后续执行。

## 简化示例

```python
from amrita_sense.node.core import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter

class SimpleWorkflow:
    """一个自包含的工作流：将值翻倍，然后格式化结果。"""

    def __init__(self, value: int):
        self.value = value
        self.result: str | None = None

        # 编排、渲染、创建解释器——一站式完成
        rendered = (self.double >> self.format).render()
        self.interpreter = WorkflowInterpreter(rendered)

    @Node()
    async def double(self) -> int:
        """将 self.value 翻倍。"""
        self.value *= 2
        return self.value

    @Node()
    async def format(self) -> str:
        """格式化 self.value 的结果。"""
        self.result = f"已处理: {self.value}"
        return self.result

    async def run(self) -> str | None:
        await self.interpreter.run()
        return self.result
```

### 使用方式

```python
wf = SimpleWorkflow(value=21)
result = await wf.run()
print(result)  # "已处理: 42"
```

## 关键点

### `self` 是自动的

`@Node()` 正常装饰实例方法。Python 的方法绑定在函数调用前注入 `self`——它永远不会出现在 DI 的依赖解析过程中。你不需要通过 `extra_args` 或 `extra_kwargs` 来传递 `self`。

### 类字段作为共享状态

节点直接读写 `self.xxx`。节点的返回值**不会**自动流入下一个节点的 DI 上下文——使用 `self` 上的实例字段来跨节点共享状态。

## 真实示例

AmritaCore 中的 `ChatObject` 是内联工作流模式的生产级实现：它继承 `SuspendObjectStream`，在 `__init__` 中用 `@Node()` 装饰十多个实例方法（`_render_train`、`_limiting_memory`、`_prepare_messages`、`_call_completion` 等），通过 `>>` 编排成完整流水线，渲染后创建解释器——所有状态自然挂在 `self` 字段上。上面展示的 `SimpleWorkflow` 正是其设计的简化核心。

## 何时使用（以及何时不使用）

### 适合内联工作流

| 场景                       | 说明                                                       |
| -------------------------- | ---------------------------------------------------------- |
| 可复用、可配置的工作流单元 | 构造函数接受参数，实例化后即可运行                         |
| 多个节点共享可变状态       | `self` 作为天然的状态容器，无需在节点间传递                |
| 类库式 API                 | 对外暴露 `run()` / `resume()` / `terminate()` 等清晰方法   |
| 动态编排                   | 根据构造参数在 `__init__` 中动态选择节点组合               |
| LangGraph 迁移             | 如果你的项目已有基于类的图定义，内联工作流是最近的迁移路径 |

### 不适合内联工作流

| 场景                        | 建议                                             |
| --------------------------- | ------------------------------------------------ |
| 只有 2-3 个节点的一次性脚本 | 顶层函数 `>>` 编排更快，无需类的样板代码         |
| 节点之间完全无状态共享      | 自由函数工作流更简洁，每个节点只关心输入输出     |
| 需要跨模块组合的工作流      | 自由函数工作流天然支持跨文件导入和混排           |
| 团队成员不熟悉 OOP 范式     | 内联工作流依赖对 `self` 和方法绑定的理解         |
| 极致性能场景（超高频调用）  | 类的实例化开销虽小，但在百万级调用循环中需要考虑 |
