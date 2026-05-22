# 4.1 依赖注入

AmritaSense 工作流引擎深度集成了 AmritaCore 的依赖注入（Dependency Injection, DI）系统，为工作流节点提供了强大的依赖解析和注入能力。这种集成使得节点函数可以声明其依赖项，而引擎会在执行时自动解析并注入这些依赖。

## 4.1.1 概述：节点与事件的 DI 机制

在 AmritaSense 中，每个工作流节点本质上都是一个可调用的函数。通过依赖注入机制，这些函数可以声明它们需要的各种依赖项，包括：

- **工作流解释器实例**：通过 `POINTER_DEPENDS` 获取当前 `WorkflowInterpreter`
- **地址计算工具**：通过 `ADDR`、`NEAR_OFFSET`、`FAR_OFFSET` 动态计算节点地址
- **自定义依赖提供者**：任何返回所需类型值的函数都可以作为依赖提供者

依赖注入系统在节点执行前进行依赖解析，确保所有声明的依赖都能被正确提供。如果依赖解析失败，工作流将抛出相应的异常并终止执行。

## 4.1.2 基本用法：Depends() 声明

依赖注入通过 `Depends()` 函数实现。`Depends()` 接收一个依赖提供者函数，并返回一个依赖工厂，该工厂会在节点执行时被调用来获取实际的依赖值。

### 基本语法

```python
from amrita_sense.hook.matcher import Depends
from amrita_sense.runtime.deps import POINTER_DEPENDS, ADDR, NEAR_OFFSET

@Node()
def my_node(
    dependency_value: ReturnType = Depends(dependency_provider_function)
):
    # 使用 dependency_value
    pass
```

### 内置依赖工具

AmritaSense 提供了几个内置的依赖工具函数，位于 `amrita_sense.runtime.deps` 模块中：

- `POINTER_DEPENDS`：注入当前的 `WorkflowInterpreter` 实例
- `ADDR(alias)`：注入指定别名节点的绝对地址（`PointerVector`）
- `NEAR_OFFSET(alias)`：注入指定别名节点的近偏移量（`int`）
- `FAR_OFFSET(alias)`：注入指定别名节点的远偏移量（`PointerVector`）

### 使用示例

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
    # 使用解释器进行跳转操作
    pc.jump_to(target_addr)
    # 或者使用偏移量进行相对跳转
    pc.jump_offset(offset)
```

## 4.1.3 并发解析与运行时注入

AmritaSense 的依赖注入系统支持并发解析和运行时注入，这意味着：

1. **并发安全**：依赖解析过程是线程安全的，可以在并发环境中安全使用
2. **运行时动态性**：依赖值在节点执行时才被计算，而不是在工作流编译时
3. **上下文感知**：依赖提供者函数可以访问当前的工作流上下文

依赖注入系统会自动处理同步和异步依赖提供者函数。如果依赖提供者是异步函数，系统会自动等待其完成；如果是同步函数，则直接调用。

### 异步依赖示例

```python
async def async_dependency():
    # 模拟异步操作
    await asyncio.sleep(0.1)
    return "async_result"

@Node()
def async_node(result: str = Depends(async_dependency)):
    print(f"Received: {result}")
```

## 4.1.5 事件与钩子集成

AmritaSense 对节点和事件处理器使用相同的依赖匹配机制。这意味着事件回调也可以声明 `Depends(...)` 依赖项，运行时在调用回调前会解析这些依赖。

```python
from amrita_sense.hook.matcher import Depends

async def on_event(event: Any, pc: WorkflowInterpreter = Depends(POINTER_DEPENDS)):
    # 事件处理器同样可以通过 Depends 获取运行时上下文
    pass
```

事件/钩子系统通过与节点执行相同的 `MatcherFactory` 机制解析依赖，因此整个引擎中的行为是一致的。

## 4.1.6 关键行为：返回 None 将直接“炸掉”工作流

依赖注入系统有一个重要的行为特性：**如果依赖提供者函数返回 `None`，整个工作流将被终止**。

这个设计决策基于以下考虑：

1. **明确的失败语义**：`None` 被视为依赖解析失败的明确信号
2. **避免空值传播**：防止 `None` 值在工作流中传播导致难以调试的问题
3. **快速失败原则**：在依赖无法满足时立即失败，而不是继续执行可能产生错误结果的逻辑

### 处理可选依赖

如果某个依赖可能是可选的（即允许为 `None`），应该使用以下模式：

```python
def optional_dependency():
    # 可能返回 None，但这不是错误
    if some_condition:
        return "value"
    else:
        return OptionalValue(None)  # 使用包装类或其他非 None 值

class OptionalValue:
    def __init__(self, value):
        self.value = value
```

或者在节点函数内部处理条件逻辑，而不是依赖注入层：

```python
def get_maybe_value():
    if some_condition:
        return "value"
    return "default_value"  # 不返回 None

@Node()
def safe_node(value: str = Depends(get_maybe_value)):
    # value 永远不会是 None
    pass
```

### 错误处理

当依赖提供者返回 `None` 时，工作流会抛出 `DependsResolveFailed` 异常。这个异常可以通过 TRY/CATCH 机制捕获：

```python
def failing_dependency():
    return None  # 这会导致工作流终止

TRY(
    NodeType(lambda: print("This won't execute"))
).CATCH(DependsResolveFailed, NodeType(lambda: print("Caught dependency failure")))
```

这种设计确保了依赖注入系统的健壮性和可预测性，同时为开发者提供了清晰的错误处理机制。
