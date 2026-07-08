# 运行时系统

运行时系统负责执行编译后的工作流图，管理指针推进、调用栈和跳转控制。AmritaSense 的核心运行时是 `WorkflowInterpreter`——它不是一个“图调度器”，而是一个**指令解释器**，以步进循环的方式逐节点执行编译产物。

## WorkflowInterpreter

```python
class WorkflowInterpreter(Generic[io_T]):
    """Core interpreter responsible for executing compiled workflow graphs.

    This class manages the execution pointer (PointerVector), return address
    stack, and all control flow operations. It executes workflows step-by-step
    rather than as a bulk-synchronous graph traversal, giving each node atomic
    execution guarantees and enabling precise external intervention.
    """
```

**设计定位**

`WorkflowInterpreter` 是 AmritaSense 的“CPU”。它从编译产物 `NodeComposeRendered`（代码段）中读取节点，用 `PointerVector`（程序计数器）追踪当前位置，通过 `_ret_addr_stack`（调用栈）管理子程序返回。所有控制流指令——`IF`、`GOTO`、`CALL`、`TRY`——最终都通过解释器提供的跳转和调用方法实现。

**泛型参数**

- `io_T`：协变的 `SuspendObjectStream` 子类型。当 `io_T = SuspendObjectStream` 时，解释器编排纯异步任务；当 `io_T = ChatObject` 时，节点获得 LLM 对话能力。同一套指令集和解释器逻辑，通过类型参数实现能力替换。

### 构造参数

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
    context_stack: Stack[InterpreterContext] | None = None,
    middleware: Callable[['WorkflowInterpreter'], Awaitable[Any]] | None = None,
)
```

- `node_compose`：编译后的工作流图，或一个 `SelfCompileInstruction`（会自动调用 `extract().render()` 编译）
- `object_io`：可选的外部 I/O 接口。若不传，解释器内部创建一个最基础的 `SuspendObjectStream`。传入 `ChatObject` 等子类时，节点可通过 `pc.object_io` 访问流式能力
- `exception_ignored`：声明为不可捕获的异常类型元组。`InterruptNotice` 和 `BreakLoop` 会被自动加入此元组
- `extra_args` / `extra_kwargs`：传递给每个节点的额外参数，供依赖注入使用
- `addr_stack`：可选的外部调用栈。若不传，解释器内部创建一个新的 `Stack[PointerVector]`
- `context_stack`（v0.3.x+）：可选的预初始化解释器上下文栈，用于保存/恢复工作流。默认创建新的空 `Stack[InterpreterContext]`
- `middleware`：可选异步可调用对象，接收 `WorkflowInterpreter` 实例。设置后，`run_step_by()` 和 `call_sub()` 不再直接调用节点，而是将执行委托给 middleware。middleware 可自行决定是否执行节点、如何执行、以及如何转换结果。
- `parent_interpreter`（v0.3.0+）：可选的父 `WorkflowInterpreter`，用于构建解释器树。由 `fork_interpreter()` 自动设置——一般无需直接使用。

### Panic / Recover（v0.3.1+）

当未处理异常从主执行循环逃逸时，解释器进入 **panic** 状态：保留异常（`_panic_exc`）、当前指针位置和所有调用栈，以便检查崩溃现场，并可恢复执行。

这与 `TRY/CATCH` 机制有明确分工：

| 方面         | Try-Catch                  | Panic / Recover                               |
| ------------ | -------------------------- | --------------------------------------------- |
| **范围**     | 局部、可控的正常业务异常   | 全局、不可预料的意外崩溃                      |
| **开销**     | 低（指令级拦截）           | 高（保留完整解释器状态）                      |
| **崩溃后**   | CATCH 块处理，继续执行     | 解释器 Dump，保留崩溃现场                     |
| **恢复**     | CATCH 内自动完成           | 再次调用 `run()` / `run_step_by()` 从断点继续 |
| **适用场景** | 节点级重试、降级、事务回滚 | 调试、审计、崩溃后续跑                        |

恢复只需在同一个解释器上再次调用 `run()`（或 `run_step_by()`）——指针仍停留在崩溃位置，执行会从断点继续。解释器会在下一次执行时记录 "Recovered from panic" 并清除 `_panic_exc`。

### 核心属性

- `_graph: NodeComposeRendered`：编译后的只读工作流图，解释器从中读取节点
- `_pointer: PointerVector`：当前执行位置。解释器主循环始终以它指向的节点作为执行目标
- `_ret_addr_stack: Stack[PointerVector]`：返回地址栈。`call_sub` 和 `CALL` 指令压入返回地址，执行完毕弹栈恢复
- `_jump_marked: bool`：跳转标记。当 `True` 时，主循环跳过本次的 `advance_pointer()` 步进，下一轮直接从跳转目标继续
- `_interpret_lock: aiologic.Lock`：解释锁。每次迭代获取一次，保证单个节点的执行原子性。同时也是外部安全调用的互斥锁
- `_if_flag: bool`（v0.3.x+）：标记解释器是否处于中断上下文的布尔标志
- `_context_stack: Stack[InterpreterContext]`（v0.3.x+）：`InterpreterContext` 快照的后进先出栈，用于 PUSH_CONTEXT/POP_CONTEXT 和 INTERRUPT_INTO/INTERRUPT_RET
- `_ava_args / _ava_kwargs`：执行期可用参数池，供依赖注入系统从中匹配节点的参数签名
- `_exc_ignored: tuple[type[BaseException], ...]`：运行时自动包含 `InterruptNotice` 和 `BreakLoop`。这些异常不会被任何 `CATCH` 块捕获，直接穿透到顶层。**v0.3.0+**：可通过 `__flags__.DISABLE_EXC_IGNORED = True` 禁用此自动加入行为
- `object_io: io_T`：泛型的外部 I/O 接口。节点可通过 `pc.object_io` 进行流式产出、挂起控制

### 解释器树（v0.3.0+）

解释器形成树结构：顶层解释器可通过 `fork_interpreter()` 创建子解释器，子解释器也可以有自己的子节点。

**`id: str`** — 标识该解释器实例的唯一 UUID 字符串。

**`parent: WorkflowInterpreter | None`** — 父解释器，顶层解释器为 `None`。

**`top_interpreter: WorkflowInterpreter`** — 解释器树的根节点。

**`sub_interpreters: dict[str, WorkflowInterpreter]`** — 直接子解释器的字典，以 ID 为键。

**`all_sub_interpreters: dict[str, WorkflowInterpreter]`** —（仅顶层）整棵树中所有后代解释器的字典。

**`is_running: bool`** — 解释器主循环是否正在执行。工作流完成（或终止）后返回 `False`。

**`pending_stop: bool`** — 是否已对该解释器调用 `terminate()`。

**`wait: asyncio.Future[None]`** — 一个在解释器执行完成时 resolve 的 future。若解释器未运行则抛出 `IllegalState`。

**`get_exception() -> Exception | None`**（v0.3.1+）— 获取上次 panic 异常。若解释器正常完成或从未崩溃，返回 `None`。崩溃后即时可用，用于诊断。

### 主要方法

#### 解释器树管理（v0.3.0+）

**`fork_interpreter(compose=None, middleware=UNSET, object_io=None) -> WorkflowInterpreter`**

在解释器树中创建子解释器。默认继承父解释器的图和中间件。

- `compose`：可选的 `NodeComposeRendered`。若为 `None`，使用父解释器的图。
- `middleware`：`UNSET`（继承父中间件）、`None`（无中间件）或自定义可调用对象。
- `object_io`：可选的 `SuspendObjectStream`。若为 `None`，共享父解释器的 `object_io`。自 v0.3.2 起，`SuspendObjectStream` 通过 CLCA 信号设计模式实现了并发安全。

**`async terminate(eol: bool = True)`**

标记该解释器为优雅停止。设置 `pending_stop = True` 并等待 `wait` future。若 `eol=True`，终止后将解释器从树中移除。

**`terminate_all_forks(eol: bool = True, exclude_self: bool = False) -> asyncio.Future`**

标记所有直接子解释器为终止。返回一个在所有子解释器终止后 resolve 的 future。

**`async terminate_all(eol: bool = True, exclude_self: bool = False)`**

仅顶层可用：标记该解释器及所有后代为终止。在非顶层解释器上调用会抛出 `IllegalState`。

**`async wait_all_forks(return_exc=False, exclude_self=False)`**

等待所有直接子解释器完成。若 `return_exc=True`，返回 `BaseException | None` 列表。

**`async wait_all(return_exc=False, exclude_self=False)`**

仅顶层可用：等待整棵解释器树完成。在非顶层解释器上调用会抛出 `IllegalState`。

**`get_exception() -> Exception | None`**（v0.3.1+）

返回上次 panic 异常，或 `None`（若解释器正常完成或从未崩溃）。用于检查前一次 `run()` 是否崩溃及为何崩溃。

**`reset()`**（v0.3.1+）

将解释器执行状态重置为初始值：清除指针、返回地址栈、跳转标记、pending stop 标志、waiter future 和 panic 异常。此方法**与恢复流程无关**——从 panic 恢复只需直接调用 `run()`，无需先 reset。

`reset()` 适用于在不创建新解释器的前提下、从同一工作流图重新开始执行的场景。

**`if_flag` 属性**（v0.3.x+）

获取或设置中断上下文标志。setter 校验值为 bool 类型。当为 `True` 时，`INTERRUPT_INTO` 无法调用（抛出 `IllegalState`）。

**`context_stack` 属性**（v0.3.x+）

返回解释器的上下文栈——一个用于保存/恢复工作流的 `Stack[InterpreterContext]`。

**`dump_interpreter(exclude_deps=True, exclude_stack=True) -> InterpreterContext`**（v0.3.x+）

导出当前解释器状态的完整快照。由 `PUSH_CONTEXT` 和 `INTERRUPT_INTO` 使用。

参数：

- `exclude_deps`：若为 `True`（默认），从快照中排除依赖注入参数。
- `exclude_stack`：若为 `True`（默认），从快照中排除返回地址栈。

返回：包含 `ptr`、`exception_ignored`、可选 `s_args`/`s_kwargs`、可选 `stack`、`extra` 和 `exception` 字段的 `InterpreterContext` 数据类。

**`rebase_context(ctx: InterpreterContext) -> None`**（v0.3.x+）

从 `InterpreterContext` 快照恢复解释器状态。从上下文中设置指针、异常忽略列表、依赖注入参数、返回地址栈和 panic 异常。

参数：

- `ctx`：要从中恢复的 `InterpreterContext`。

#### 地址解析

**`find_addr_alias(alias: str) -> list[int]`**

在 `alias2vector_map` 中查找别名并返回其指针向量地址。若别名不存在，抛出 `NullPointerException`。

**`find_addr(addr: list[int]) -> BaseNode | NodeComposeRendered`**

通过绝对地址查找节点或子容器。地址无效时抛出 `NullPointerException`。

**`get_graph() -> NodeComposeRendered`**

返回当前工作流的编译产物。调试节点常通过此方法读取工作流结构。

#### 跳转操作

所有跳转方法均受 `@markup` 保护。`@markup` 确保一次调用只设置 `_jump_marked` 一次，且在 `_jump_marked` 已为 `True` 时不再执行。跳转后解释器主循环检测到标记，跳过常规指针推进，下一轮从跳转目标继续。

**`jump_to(addr: list[int])`**

绝对跳转。用 `far_to(addr)` 完整替换 `_pointer`。适用于跨 Bubble 跳转。

**`jump_near(addr: int)`**

近距跳转。用 `near_to(addr)` 替换当前层级的索引，其他维度不变。适用于同一 Bubble 内的跳转。

**`jump_offset(offset: int)`**

相对偏移跳转。在当前层级索引上增加 `offset`。适用于三元组内的条件分支跳转。

**`jump_offset_top(offset: int)`**

顶层相对偏移跳转。调整最外层索引并重置所有内层维度，用于跨层级返回。

**`jump_to_top(addr: int)`**

跳转到顶层的指定绝对索引。

**`jump_far_ptr(offset: list[int])`**

多维绝对跳转。用 `far_to(offset)` 完整替换 `_pointer`。被 `RET_FAR` 用于从嵌套作用域返回。

**`jump_offset_far(offset: list[int])`**

多维相对偏移跳转。与 `jump_offset()` 只调整最内层维度不同，此方法通过 `offset_far()` 对所有嵌套层级同时施加偏移量。适用于跨层级的复杂跳转场景。

#### 子程序调用

**`call_sub(addr, /, \*extra_arg, interrupt=False, **extra_kwargs) -> Any`\*\*

子程序调用的底层原语。执行流程：

1. 将当前 `_pointer` 压入 `_ret_addr_stack`
2. 将 `_pointer` 替换为目标地址
3. 若 `interrupt=True`，获取 `_interpret_lock`（用于外部安全调用）
4. 调用 `_call` 执行子程序入口节点
5. `finally` 块弹栈恢复 `_pointer`（除非 `_jump_marked` 为 `True`）

`interrupt=True` 用于外部系统在节点边界注入子程序。内部节点调用子程序时**必须**使用 `interrupt=False`，否则触发 `aiologic` 死锁检测。

**`call_near(addr: int, \*ag, interrupt=False, **kw) -> Any`\*\*

在当前层级内以近距地址调用子程序。通过 `near_to(addr)` 计算目标地址。

**`call_offset(offset: int, \*ag, interrupt=False, **kw) -> Any`\*\*

在当前指针上偏移 `offset` 后调用子程序。适用于三元组内 `ConditionJumpNode` 调用条件节点和行动节点。

**`call_offset_far(offset: list[int], \*ag, interrupt=False, **kw) -> Any`\*\*

以多维偏移调用子程序。先通过 `offset_far()` 计算目标地址，再委托给 `call_sub()` 执行。适用于跨嵌套层级调用子节点。

#### `@markup` 装饰器

`markup` 是一个静态方法装饰器，用于将方法标记为**指针操作**（跳转及其他修改程序计数器的操作）。被装饰的方法在调用时自动设置 `_jump_marked = True`，阻止主执行循环在方法完成后推进指针。

装饰器的类型注解使用 `fun_T` TypeVar 保留原始方法签名。在 `TYPE_CHECKING` 下，它会返回原始函数以避免混淆静态类型检查器。所有被装饰的方法必须是返回 `None` 的实例方法。

#### 指针推进

**`advance_pointer(ptr: PointerVector | None = None) -> bool`**

推进执行指针到工作流图中的下一个节点。此方法实现了嵌套工作流结构的导航逻辑，处理顺序执行和层级遍历。

**参数**

- `ptr`：可选的外部指针向量。传入后，方法将推进此参数所指的指针，而**不会改变解释器自身的 `_pointer`**。默认为 `None` 时，推进解释器自身的 `_pointer`。此参数使外部系统可以在不破坏解释器状态的前提下，预演指针推进路径。

**返回值**

- `True`：指针成功推进到下一个节点
- `False`：已到达工作流末尾，无更多节点可执行

**推进算法**

1. 从 `ptr`（或 `self._pointer`）开始，沿 `base_addr` 逐层定位到当前节点所在容器
2. 若当前节点是**非空 `NodeComposeRendered`** -> 指针进入嵌套容器（`append(0)`），返回 `True`
3. 若当前节点有**后继兄弟节点**：
   - 兄弟节点是非空 `NodeComposeRendered` -> 进入该嵌套容器，返回 `True`
   - 否则 -> 移动到兄弟节点，返回 `True`
4. 若当前节点无后继 -> 沿指针栈**逐层向上回溯**，寻找父容器的下一个兄弟
5. 回溯中寻得后继 -> 按相同逻辑处理，返回 `True`
6. 回溯到顶层仍未找到 -> 返回 `False`（工作流结束）

**弃用说明**

`_advance_pointer` 属性已在 v0.3.0 弃用，请使用 `advance_pointer()` 方法。旧属性仅作为兼容性委托存在，将在未来版本中移除。

### 执行行为

`WorkflowInterpreter` 通过持有 `_interpret_lock` 保证单个节点的执行原子性。它仅在安全边界检查挂起点：

- 每个节点执行前通过全局检查点 `WorkflowInterpreter::each_node`
- 每个节点通过其 tag 的检查点

`object_io` 实现负责协调挂起与恢复。

### 示例

```python
from amrita_sense.node.core import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter

@Node()
async def a():
    return 1

@Node()
async def b():
    return 2

compose = a >> b
rendered = compose.render()
pc = WorkflowInterpreter(rendered)
await pc.run()
```

**`call_near(addr: int, \*ag, interrupt=False, **kw) -> Any`\*\*

在当前层级内以近距地址调用子程序。

#### 主执行循环

**`async run() -> None`**

执行整个工作流。内部调用 `run_step_by()` 并消费所有生成器产出。适用于一次性跑完工作流的场景。

**`async run_step_by() -> AsyncGenerator[Any, None]`**

步进式执行生成器。每次迭代：

1. 获取 `_interpret_lock`
2. 确保 `_pointer` 有效（空则从 `[0]` 开始，图形空则退出）
3. 在 `PC_CHECKPOINT` 断点等待外部挂起
4. 执行当前节点（`_call()`）
5. 若 `_jump_marked`，重置标记并跳过指针推进
6. 否则调用 `advance_pointer()` 推进指针
7. 指针推进失败（到达末尾）则退出

外层 `try` 捕获 `InterruptNotice` 后清理调用栈和指针，干净退出。

此方法让外部系统可以在每次节点执行前后介入——配合挂起机制和 `interrupt=True` 的 `call_sub`，构成了完整的调试器基础。

### 使用示例

**基础执行**

```python
compose = a >> b >> c
rendered = compose.render()
pc = WorkflowInterpreter(rendered)
await pc.run()
```

**注入 ChatObject 获得 LLM 能力**

```python
chat = ChatObject(train=..., user_input=..., ...)
pc = WorkflowInterpreter[ChatObject](
    rendered,
    object_io=chat,
)
# 节点内可通过 pc.object_io 访问 LLM 流
```

**节点内调用子程序**

```python
@Node()
async def caller(pc: WorkflowInterpreter):
    addr = pc.find_addr_alias("sub_routine")
    result = await pc.call_sub(addr, extra_param=42)
```

**外部安全注入**

```python
# 在另一个协程中，工作流挂起时
await pc.call_sub(
    pc.find_addr_alias("__inspector__"),
    interrupt=True,
)
```

**步进调试**

```python
async for _ in pc.run_step_by():
    print(f"Executed node at {pc._pointer}")
    if should_pause:
        break  # 暂停，稍后可从同一个 run_step_by 继续
```
