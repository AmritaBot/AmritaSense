# 事件系统

AmritaSense 的事件系统是与工作流解释器**并行独立**的运行时钩子机制。它不绑定于任何特定节点或生命周期，而是作为一条独立的管道，让工作流节点能够触发自定义事件，并由注册的处理器使用与节点完全相同的依赖注入机制进行响应。

### 核心角色

| 角色                                | 职责                                         |
| ----------------------------------- | -------------------------------------------- |
| `BaseEvent`                         | 所有自定义事件的基类，定义事件类型标识       |
| `on_event(event_type)`              | 装饰器，将异步函数注册为特定事件类型的处理器 |
| `MatcherFactory.trigger_event(...)` | 运行时入口，分发事件给所有匹配的处理器       |

### 分发流程

当调用 `trigger_event(event)` 时，系统依次执行：

1. 从 `BaseEvent` 实例获取事件类型字符串
2. 在 `EventRegistry` 中查找该类型的所有注册处理器
3. 对每个处理器，解析其 `Depends(...)` 声明的运行时依赖
4. 按优先级顺序调用处理器

如果事件类型没有注册处理器，调用静默跳过，不产生任何副作用。

## 发散式分发：与工作流中断的本质区别

**事件系统是发散式的**——它负责将事件广播给所有匹配的处理器，然后继续执行。它**不内置中断或挂起能力**。这与 Sense 工作流的挂起/中断机制有本质区别：

|              | 事件系统                           | 工作流中断                                                        |
| ------------ | ---------------------------------- | ----------------------------------------------------------------- |
| **模式**     | 发散式广播                         | 协作式暂停                                                        |
| **控制流**   | 处理器执行完毕后自动返回           | 挂起后需显式 `resume()` 才能继续                                  |
| **介入能力** | 处理器只能响应事件，不能暂停工作流 | 外部可通过 `ARCHIVED_NODES` + `call_sub(interrupt=True)` 注入执行 |
| **适用场景** | 日志记录、审计、通知、状态同步     | 调试、人工审批、动态流程修改                                      |

如果需要在事件处理器内部实现中断或挂起行为，**必须由开发者在处理器中手动实现**——例如，处理器内部主动调用 `pc.object_io.wait_to_suspend()` 或调用 `pc.call_sub(interrupt=True)` 注入归档节点。这些能力来自 Sense 工作流的解释器，而非事件系统本身。

## 与工作流节点共享依赖注入

事件处理器**完全复用** AmritaSense 的依赖注入系统。处理器可以通过 `Depends(...)` 声明任意依赖——包括 `POINTER_DEPENDS` 获取当前 `WorkflowInterpreter` 实例——运行时会在调用前自动解析并注入。这意味着事件处理器享有和 `@Node()` 节点完全相同的 DI 能力：类型安全、并发解析、以及 `Depends` 返回 `None` 时终止执行的行为。

> **与 Core 事件系统的关系**：AmritaSense 的事件系统是 Core 事件系统的独立镜像，两者共享完全相同的 API 设计与依赖注入契约，但各自独立运行。Core 的事件处理器不需要感知 Sense，Sense 的节点也不需要依赖 Core——它们只通过 `DependencyMeta` 这一通用数据结构进行协作。

## 自定义事件示例

```python
from dataclasses import dataclass

from amrita_sense.hook.event import BaseEvent
from amrita_sense.hook.matcher import MatcherFactory, Depends
from amrita_sense.hook.on import on_event
from amrita_sense.node.core import Node
from amrita_sense.runtime.deps import POINTER_DEPENDS
from amrita_sense.runtime.workflow import WorkflowInterpreter

@dataclass
class TaskCompletedEvent(BaseEvent[str]):
    task_id: str

    @property
    def event_type(self) -> str:
        return "task.completed"

    def get_event_type(self) -> str:
        return self.event_type

@on_event("task.completed")
async def handle_task_completed(
    event: TaskCompletedEvent,
    pc: WorkflowInterpreter = Depends(POINTER_DEPENDS),
):
    print(f"任务完成：{event.task_id}")

@Node()
async def complete_task_node() -> str:
    # ... 任务逻辑 ...
    await MatcherFactory.trigger_event(TaskCompletedEvent(task_id="email-send"))
    return "done"
```

## 处理顺序与阻塞

同一事件类型的处理器按优先级升序执行。处理器可以通过抛出 `CancelException` 立即终止整个事件链，或通过 `PassException` 跳过自身并让下一个处理器继续执行。标准分发是协作式的——除非显式中断，所有匹配的处理器都会按序执行。

## ConstructableEvent 与 TRIGGER_EVENT

### ConstructableEvent

`ConstructableEvent` 继承自 `BaseEvent`，额外定义了一个 `constructor()` 类方法，使事件能够在**工作流执行期间按需构造**。这是它与 `BaseEvent` 的关键区别：`BaseEvent` 要求你在分发前手动实例化事件，而 `ConstructableEvent` 允许你通过 `TRIGGER_EVENT` 将事件构造直接嵌入工作流编排中。

```python
@dataclass
class ConstructableEvent(BaseEvent):
    @abstractmethod
    @classmethod
    def constructor(cls, *args, **kwargs) -> Self | Awaitable[Self]: ...
```

子类必须实现 `constructor()`，可以是同步或异步的。运行时调用此方法构建事件实例，然后通过 `MatcherFactory.trigger_event()` 分发。

### TRIGGER_EVENT 指令

`TRIGGER_EVENT` 是一个**自编译指令**，用于在工作流编排中触发可构造事件。它接收一个 `ConstructableEvent` 子类，在渲染期展开为三个节点的序列：

```text
[EventTrigger -> event.constructor() -> NOP]
```

#### 运行时流程

1. `EventTrigger` 调用 `pc.call_offset(1)` 执行偏移 +1 处的构造器节点
2. 校验返回值是否为 `BaseEvent` 实例
3. 通过 `MatcherFactory.trigger_event(event, ...)` 分发事件，传递 `extra_args`/`extra_kwargs`
4. 跳转到偏移 +2（`NOP`）继续正常执行

#### 示例

```python
from dataclasses import dataclass

from amrita_sense.hook.event import ConstructableEvent
from amrita_sense.hook.on import on_event
from amrita_sense.instructions import TRIGGER_EVENT
from amrita_sense.node.core import Node

@dataclass
class OrderPlacedEvent(ConstructableEvent[str]):
    order_id: str

    @property
    def event_type(self) -> str:
        return "order.placed"

    def get_event_type(self) -> str:
        return self.event_type

    @classmethod
    def constructor(cls, order_id: str = "auto-generated") -> "OrderPlacedEvent":
        return cls(order_id=order_id)

@on_event("order.placed")
async def notify_warehouse(event: OrderPlacedEvent):
    print(f"仓库已收到通知：{event.order_id}")

@Node()
async def checkout() -> str:
    return "结账完成"

# 编排：结账后触发事件
workflow = checkout >> TRIGGER_EVENT(OrderPlacedEvent)
```

由于 `TRIGGER_EVENT` 是 `SelfCompileInstruction`，它可以直接用 `>>` 与普通节点组合。构造器会从解释器接收 `extra_args` 和 `extra_kwargs`，因此可以通过 DI 机制在运行时参数化。
