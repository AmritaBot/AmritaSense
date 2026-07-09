# 4.1 依赖注入

AmritaSense 工作流引擎集成了依赖注入（Dependency Injection, DI）系统，为工作流节点提供了强大的依赖解析和注入能力。这种集成使得节点函数可以声明其依赖项，而引擎会在执行时自动解析并注入这些依赖。

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

## 4.1.7 DI 结果缓存（v0.4.2+）

从 v0.4.2 起，`WorkflowInterpreter` 维护一个内部 DI 结果缓存（`_di_cache`），避免在相同参数类型下重复执行同一节点的依赖解析。

### 工作原理

缓存键由两部分组成：

- **指针哈希**：`hash(self._pointer)` —— 解释器当前执行位置
- **参数哈希**：基于 `_ava_args` 和 `_ava_kwargs` 的类型指纹

工具函数 `_fingerprint_args()` 按以下方式生成参数哈希：

1. 对每个位置参数提取 `type(arg).__name__`
2. 对每个关键字参数提取 `(key, type(v).__name__)`（排序以保证稳定性）
3. 合并后取 hash

```python
# 缓存键的简化示意
cache_key = hash((hash(pointer), _fingerprint_args(ava_args, ava_kwargs)))
```

缓存载体是 `cachetools` 的 `LRUCache`，最大容量 2048 条。缓存满时按最近最少使用策略淘汰。

### 缓存生命周期

- **初始化**：`WorkflowInterpreter.__init__()` 中创建，携带初始参数哈希。
- **查询**：解析节点依赖前，先检查 `_di_cache.payload` 是否有匹配键。命中则直接使用缓存的 kwargs，跳过全部依赖解析。
- **失效**：修改 `_ava_args` 或 `_ava_kwargs` 会将 `hash_trustable` 设为 `False`，表示参数哈希可能过期。调用 `rehash_args()` 重新计算并恢复信任。若新哈希与旧值不同，整个缓存被清空。
- **禁用**：设置 `__flags__.WORKFLOW_DI_NO_CACHE = True` 完全关闭缓存。

### 代码示例

```python
from amrita_sense._unsafe import __flags__
from amrita_sense.runtime.workflow import WorkflowInterpreter

# 默认：DI 缓存开启
pc = WorkflowInterpreter(rendered, extra_args=(my_service,))
await pc.run()  # 循环体的第二次迭代将复用缓存的 DI 结果

# 为有副作用的提供者禁用缓存
__flags__.WORKFLOW_DI_NO_CACHE = True
pc2 = WorkflowInterpreter(rendered)
await pc2.run()  # 每个节点从头重新解析依赖
```

## 4.1.8 DI 预加载缓存（v0.4.2+）

启用 `__flags__.WORKFLOW_DI_PRELOAD_CACHE` 后，解释器在 `run()` 初始化阶段为**每个节点**预解析依赖注入——在第一个节点执行之前完成。

### 工作原理

1. `run()` 在解析完运行时参数后调用 `_refresh_di_cache_full()`
2. 方法使用临时 `PointerVector` + `advance_pointer()` 遍历整个工作流图
3. 为每个节点启动一个异步 worker，解析 DI 并将结果存入 `_di_cache.payload`
4. Worker 以 `WORKFLOW_DI_PRELOAD_BATCH`（默认 10）控制的并发批量运行
5. 预加载器尊重缓存容量上限——若 `_di_cache.payload` 达到最大容量（2048），跳过剩余节点以避免缓存颠簸
6. 预加载完成后主循环启动——每次 `_call()` 均为缓存命中

### 性能特征

| 方面           | 无预加载               | 有预加载                    |
| -------------- | ---------------------- | --------------------------- |
| **启动延迟**   | 极低                   | 与图大小 × 批量数成正比     |
| **逐节点延迟** | 首次访问：完整 DI 解析 | 始终：缓存命中（O(1) 查找） |
| **内存**       | 随节点访问惰性增长     | 启动时为所有节点预分配      |
| **最适合**     | 短工作流、一次性执行   | 长时间循环、节点重复访问    |

### 代码示例

```python
from amrita_sense._unsafe import __flags__

__flags__.WORKFLOW_DI_PRELOAD_CACHE = True
__flags__.WORKFLOW_DI_PRELOAD_BATCH = 20  # 提高并行度

pc = WorkflowInterpreter(rendered)
await pc.run()  # 第一个节点运行前，所有节点的 DI 已预解析完成
```

## 4.1.9 缓存限制与标志冲突

### `NO_DEPENDENCY_META_CACHE` 冲突

同时设置 `WORKFLOW_DI_PRELOAD_CACHE = True` 和 `NO_DEPENDENCY_META_CACHE = True` 会抛出 `RuntimeError`。预加载机制依赖缓存的 `DependencyMeta`（来自 `sign_func`）进行高效批量解析——禁用元数据缓存会使预加载不可靠。

### `WORKFLOW_DI_NO_CACHE` 冲突

同时设置 `WORKFLOW_DI_NO_CACHE = True` 和 `WORKFLOW_DI_PRELOAD_CACHE = True` 也会抛出 `RuntimeError`。这两个标志意图矛盾：一个禁用缓存，另一个预填充缓存。

### `hash_trustable` 守卫

调用 `_refresh_di_cache_full()` 时若 `hash_trustable` 为 `False`，将抛出 `DependsResolveFailed`。修改 DI 参数后务必调用 `rehash_args()` 以确保缓存完整性。
