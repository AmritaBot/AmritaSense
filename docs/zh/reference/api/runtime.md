# 运行时系统

运行时系统负责执行编译后的工作流图，管理指针推进、调用栈和跳转控制。AmritaSense 的核心运行时是 `WorkflowInterpreter`——它不是一个“图调度器”，而是一个**指令解释器**，以步进循环的方式逐节点执行编译产物。

---

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

---

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
)
```

- `node_compose`：编译后的工作流图，或一个 `SelfCompileInstruction`（会自动调用 `extract().render()` 编译）
- `object_io`：可选的外部 I/O 接口。若不传，解释器内部创建一个最基础的 `SuspendObjectStream`。传入 `ChatObject` 等子类时，节点可通过 `pc.object_io` 访问流式能力
- `exception_ignored`：声明为不可捕获的异常类型元组。`InterruptNotice` 和 `BreakLoop` 会被自动加入此元组
- `extra_args` / `extra_kwargs`：传递给每个节点的额外参数，供依赖注入使用
- `addr_stack`：可选的外部调用栈。若不传，解释器内部创建一个新的 `Stack[PointerVector]`

---

### 核心属性

- `_graph: NodeComposeRendered`：编译后的只读工作流图，解释器从中读取节点
- `_pointer: PointerVector`：当前执行位置。解释器主循环始终以它指向的节点作为执行目标
- `_ret_addr_stack: Stack[PointerVector]`：返回地址栈。`call_sub` 和 `CALL` 指令压入返回地址，执行完毕弹栈恢复
- `_jump_marked: bool`：跳转标记。当 `True` 时，主循环跳过本次的 `_advance_pointer()` 步进，下一轮直接从跳转目标继续
- `_interpret_lock: aiologic.Lock`：解释锁。每次迭代获取一次，保证单个节点的执行原子性。同时也是外部安全调用的互斥锁
- `_ava_args / _ava_kwargs`：执行期可用参数池，供依赖注入系统从中匹配节点的参数签名
- `_exc_ignored: tuple[type[BaseException], ...]`：运行时自动包含 `InterruptNotice` 和 `BreakLoop`。这些异常不会被任何 `CATCH` 块捕获，直接穿透到顶层
- `object_io: io_T`：泛型的外部 I/O 接口。节点可通过 `pc.object_io` 进行流式产出、挂起控制

---

### 主要方法

#### 地址解析

**`find_addr_alias(alias: str) -> list[int]`**

在 `alias2vector_map` 中查找别名并返回其指针向量地址。若别名不存在，抛出 `NullPointerException`。

**`find_addr(addr: list[int]) -> BaseNode | NodeComposeRendered`**

通过绝对地址查找节点或子容器。地址无效时抛出 `NullPointerException`。

**`get_graph() -> NodeComposeRendered`**

返回当前工作流的编译产物。调试节点常通过此方法读取工作流结构。

---

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

---

#### 子程序调用

**`call_sub(addr, /, \*extra_arg, interrupt=False, **extra_kwargs) -> Any`\*\*

子程序调用的底层原语。执行流程：

1. 将当前 `_pointer` 压入 `_ret_addr_stack`
2. 将 `_pointer` 替换为目标地址
3. 若 `interrupt=True`，获取 `_interpret_lock`（用于外部安全调用）
4. 调用 `_call` 执行子程序入口节点
5. `finally` 块弹栈恢复 `_pointer`（除非 `_jump_marked` 为 `True`）

`interrupt=True` 用于外部系统在节点边界注入子程序。内部节点调用子程序时**必须**使用 `interrupt=False`，否则触发 `aiologic` 死锁检测。

**`call_offset(offset: int, \*ag, interrupt=False, **kw) -> Any`\*\*

在当前指针上偏移 `offset` 后调用子程序。适用于三元组内 `ConditionJumpNode` 调用条件节点和行动节点。

**`call_near(addr: int, \*ag, interrupt=False, **kw) -> Any`\*\*

在当前层级内以近距地址调用子程序。

---

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
6. 否则调用 `_advance_pointer()` 推进指针
7. 指针推进失败（到达末尾）则退出

外层 `try` 捕获 `InterruptNotice` 后清理调用栈和指针，干净退出。

此方法让外部系统可以在每次节点执行前后介入——配合挂起机制和 `interrupt=True` 的 `call_sub`，构成了完整的调试器基础。

---

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
