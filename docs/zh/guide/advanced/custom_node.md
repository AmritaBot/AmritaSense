# 4.6 自定义节点

在 AmritaSense 中，节点是执行流的基本单元。内置指令最终都会被展开为节点组合，而自定义节点则是开发者封装自身业务逻辑的直接方式。本章将解析节点的本质、生命周期，以及如何借助 `POINTER_DEPENDS` 在必要时获得对解释器的完全控制。

## 4.6.1 @Node 装饰器与节点本质

`@Node()` 装饰器将一个普通的 Python 函数或协程转换为工作流节点。它不做任何复杂的事情——只是把函数对象、签名信息和几个元数据字段打包进一个 `Node` 实例。

### 装饰器参数

```python
@Node(
    tag="custom_tag",        # 可选：挂起点标签，默认自动生成
    wrap_to_async=True,      # 可选：是否将同步函数包装为异步执行
    address_able=True        # 可选：是否可被 ALIAS 引用
)
def my_function():
    pass
```

`tag` 既是调试时的标识符，也是流程中断的挂起点名称。如果不指定，默认使用 `NodeSuspend::{函数名}`。

### 节点的本质：一个 Callable 的薄封装

每个节点本质上是对原始函数的一次“薄封装”。它保留了原始函数的所有签名信息（`fun_sign`）和执行能力（`func`），同时附加了 AmritaSense 所需的元数据：

- **`func`**：原始函数对象。节点执行时，解释器调用的就是它
- **`fun_sign`**：由 `inspect.signature` 提取的函数签名，依赖注入依赖它来匹配参数
- **`tag`**：节点的唯一标识字符串
- **`wrap_to_async`**：同步函数是否需要被 `asyncio.to_thread` 包裹
- **`address_able`**：是否可被 `ALIAS` 引用——只有为 `True` 的节点才能成为 `GOTO` 或 `CALL` 的目标

### 节点创建过程

`@Node()` 的 `wrapper` 函数在模块加载时执行：

1. 捕获当前帧对象（`fun_frame`）
2. 用 `inspect.signature` 提取函数签名
3. 将原始函数、签名、参数打包为 `Node` 实例
4. 返回 `Node` 对象

**一切皆是节点**——这是 AmritaSense 的核心哲学。条件、循环体、异常处理器、GOTO 的目标——它们都是 `Node` 或 `BaseNode` 的实例。自定义节点也不例外。

## 4.6.2 同步与异步节点的处理

AmritaSense 统一处理同步和异步节点，在 `_call()` 中根据 `iscoroutinefunction` 和 `wrap_to_async` 两个条件决定执行方式。

### 异步节点

用 `async def` 定义的节点会被直接 `await`：

```python
@Node()
async def fetch_data():
    return await http_get("/api")
```

解释器检测到它是协程函数后，直接 `await fun(*args, **kwargs)`。

### 同步节点 + wrap_to_async=True（默认）

同步函数默认 `wrap_to_async=True`，解释器使用 `asyncio.to_thread` 将函数在线程池中执行：

```python
@Node()
def heavy_compute():
    return sum(range(10**7))
```

这避免了阻塞事件循环。适用于 CPU 密集型任务或无法改为异步的遗留同步代码。

### 同步节点 + wrap_to_async=False

当 `wrap_to_async=False` 时，解释器直接调用 `fun(*args, **kwargs)`：

```python
@Node(wrap_to_async=False)
def quick_check():
    return len(queue) > 0
```

适用于极轻量的同步操作（如简单的条件检查），零调度开销。

### 性能考量

- **CPU 密集任务** → `wrap_to_async=True`，避免阻塞事件循环
- **I/O 密集任务** → 优先使用原生 `async def`
- **极简同步操作**（如 `NOP`、简单布尔判断）→ `wrap_to_async=False`

节点的内存占用也经过了优化——`Node` 类使用了 `__slots__`，避免了默认的 `__dict__` 开销，让每个节点尽可能轻量。

## 4.6.3 节点的生命周期与原子性

### 生命周期

1. **创建**：模块加载时，`@Node()` 装饰器执行，创建 `Node` 实例
2. **编译**：`render()` 阶段，节点被放置到 `NodeComposeRendered` 的 `_graph` 数组中，分配 `PointerVector` 地址
3. **预检查**：每次执行前，`_pre_check` 被调用。这是编译期验证（如 `CallNode` 的别名存在性检查）的入口
4. **执行**：解释器获取锁，等待挂起信号，解析依赖，调用 `func`
5. **完成**：节点执行完毕，锁释放，解释器推进指针到下一个节点

### 原子性保证

节点的原子性由**解释锁**和**协作式中断**共同保证：

- **同一时刻只有一个节点在执行**：解释锁确保没有其他节点或外部注入并发执行
- **节点边界就是安全边界**：中断信号只在节点执行完毕后被检查，节点内部不会被抢占
- **异常安全**：节点抛出异常时，解释器的 `run_step_by()` 主循环在最外层捕获并处理。调用栈（`_ret_addr_stack`）和指针状态在异常后仍然保持一致——因为节点执行不直接操作这些数据结构，它们由解释器管理

### 预检查机制

如果自定义节点类继承自 `BaseNode`，可以重写 `_pre_check` 方法。这个方法在每次节点执行前被调用，可以访问当前解释器实例来执行地址验证、别名查表等工作。`CallNode` 和 `JumpNode` 正是利用这一机制，在第一次执行前完成别名到地址的解析。

## 4.6.4 POINTER_DEPENDS：获得对解释器的访问

`POINTER_DEPENDS` 是一个特殊的依赖注入工厂，允许节点获取当前 `WorkflowInterpreter` 实例。

```python
from amrita_sense.runtime.deps import POINTER_DEPENDS
from amrita_sense.runtime.workflow import WorkflowInterpreter

@Node()
def my_node(pc: WorkflowInterpreter = Depends(POINTER_DEPENDS)):
    current_addr = pc._pointer           # 读取当前位置
    target = pc.find_addr_alias("foo")   # 解析别名
    await pc.call_sub(target, arg=42)    # 调用子程序
```

### 节点获得了什么？

通过 `pc`，节点获得了对解释器的完全访问——读取当前指针、解析别名、调用子程序、甚至直接执行跳转。这是 AmritaSense 的核心理念之一：**节点不是被框架“调用”的被动单元，而是可以主动控制执行流的独立协程。**

### 何时使用，何时不用

- **需要**使用 `POINTER_DEPENDS`：当节点内部需要调用子程序（`call_sub`）、解析别名（`find_addr_alias`）、或执行动态跳转时
- **不需要**使用：当节点只做纯业务逻辑（如数据处理、API 调用）时。节点完全可以只声明业务依赖（如数据库连接、HTTP 客户端），不碰工作流控制流

### 能力越大，责任越大

获得解释器实例后，节点可以直接操作指针和调用栈。这种能力伴随着责任——节点内部的跳转会设置 `_jump_marked` 标志，影响解释器的后续行为；手动压栈而不弹栈会破坏调用栈的完整性。

因此，**只在必要时注入 `POINTER_DEPENDS`**。大多数节点应优先通过节点内部的 Python 逻辑和编排层面的指令（IF、WHILE、CALL）来完成控制流，只在指令无法表达时才直接操作解释器。

### 小结

自定义节点是 AmritaSense 的“细胞”。它们保持了最简单本质——一个被薄封装的 Python 函数——同时通过 `Depends` 和 `POINTER_DEPENDS` 获得了对 Amrita 生态完整能力的访问。在下一节中，我们将探讨如何把重复出现的节点组合模式封装为新的自编译指令，进一步扩展工作流的表达能力。
