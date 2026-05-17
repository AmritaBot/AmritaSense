# 定位与空间

在 AmritaSense 中，工作流不是一张静态的节点连接图，而是一个**线性节点数组**上的**非线性执行流**。理解“定位与空间”，就是理解如何在这个数组上精准地标记目标、计算偏移、建立作用域，从而让 GOTO 等指令实现精确的跳转。

本章将深入解析构成这套寻址体系的核心机制：编译期的别名绑定、运行时的地址解析，以及 Bubble 作用域的空间隔离。

---

## 4.2.1 编译期绑定：ALIAS 别名系统

`ALIAS` 是定位体系的**编译期基础**。它为节点绑定一个全局唯一的符号名，并在渲染阶段注册到 `alias2vector_map`，供 GOTO 和 CALL 在运行时查表解析。

### 别名注册机制

当工作流编译（`render()`）时，所有 `ALIAS` 节点按其在编排数组中的位置，将其别名与对应的 `PointerVector` 地址存入 `NodeComposeRendered.alias2vector_map`。这个字典在整个执行期间保持不变，是**符号到物理地址的唯一映射源**。

### 使用约束

`ALIAS` 并非可以随意附加到任何节点上。它有三项严格的编译期校验：

- **唯一性**：同一别名在同一工作流内重复定义会直接抛出 `RuntimeError`，防止符号污染
- **可寻址性**：被标记的节点必须具有 `address_able=True` 属性，否则无法被指针向量正确定位
- **类型限制**：不能为 `SelfCompileInstruction` 类型的节点创建别名，因为自编译指令在编译期会被展平成 `NodeCompose`，不再是单个可寻址节点

这些约束保证了别名表在运行时始终是干净、可解析的。

### 实际应用

```python
from amrita_sense.instructions import ALIAS, IF, GOTO
from amrita_sense.node import Node

@Node()
def action():
    print("Executing action")

# ALIAS 将 action 节点绑定到符号 "main_action"
# 此后 GOTO("main_action") 或 CALL("main_action") 即可直接引用
labeled_action = ALIAS(action, "main_action")

workflow = IF(some_condition, GOTO("main_action")) >> labeled_action
```

---

## 4.2.2 运行时解析：GOTO 无条件跳转

`GOTO` 是 AmritaSense 中最直接的控制流跳转指令。它在运行时通过别名查表获取目标地址，然后执行一次指针改写，使解释器下一步直接执行目标节点。

### 跳转目标验证

`GOTO` 的 `JumpNode` 在 `_pre_check` 阶段完成地址解析。这一设计让错误可以被**前置到首次执行前**：

- 如果使用别名，`_pre_check` 会检查该别名是否存在于 `alias2vector_map` 中
- 如果别名不存在，`JumpNode` 会列出所有已注册别名，并用 `difflib` 做模糊匹配，抛出带有“你是否想写 X？”建议的错误
- 如果使用绝对地址（`list[int]`），会直接验证该地址是否指向有效节点

### 跳转标记机制

所有跳转方法（`jump_to`、`jump_near`、`jump_offset` 等）都使用 `@markup` 装饰器。它的作用是：在跳转发生后设置 `_jump_marked` 标志，阻止解释器在跳转后立即执行常规的指针推进。这确保了**跳转和步进是两个互斥的操作**——执行权要么被显式移动，要么自动前进一步，不会同时发生。

### 最佳实践

1. **优先使用别名而非裸地址**：`GOTO("target")` 比 `GOTO([1, 3, 5])` 更具可读性，且别名表在编译期做了唯一性校验
2. **避免用 GOTO 替代循环**：GOTO 不会在调用栈上压入返回地址，不适用于需要返回的场景。如果需要子程序调用并返回，应使用 `CALL` 指令——这将在 [下一章](./child_node.md) 详细展开
3. **留意 Bubble 边界**：GOTO 可以在任意层级间跳转，但滥用跨层级跳转会使控制流难以追踪。建议同一 Bubble 内用 `jump_near`，跨 Bubble 用 `jump_to`

---

## 4.2.3 CALL 指令：子程序调用的入口

除了 `GOTO` 的单向跳转，AmritaSense 还提供了 `CALL` 指令，用于**调用子程序并在执行完毕后自动返回**。`CALL` 与 `GOTO` 共享同一套别名寻址体系——两者都依赖 `ALIAS` 注册符号名，都在 `_pre_check` 阶段完成地址解析和拼写纠错。

### 核心区别

| 特性             | GOTO                   | CALL                         |
| ---------------- | ---------------------- | ---------------------------- |
| 是否保存返回地址 | 否                     | 是（压入 `_ret_addr_stack`） |
| 执行完毕后行为   | 继续从目标节点向后推进 | 自动弹栈，回到调用点继续     |
| 适用场景         | 单向跳转、分支合并     | 子程序复用、中断处理         |

> **详细展开**
> `CALL` 指令的完整机制——包括调用栈管理、`ARCHIVED_NODES` 子程序存储结构、`SubprogramJumpNode` 的跳过逻辑、以及中断向量表的实现——将在 [第 4.3 章：子节点调用](./child_node.md) 中详细解析。

---

## 4.2.4 空间隔离：Bubble 作用域与 Near 寻址

AmritaSense 使用 `PointerVector` 实现多层嵌套的地址空间管理。每一个被括号 `()` 包裹的节点组，在编译后形成一个独立的 `NodeComposeRendered`，拥有自己的内部 `near` 地址空间——这就是 **Bubble**。

### 地址向量结构

`PointerVector` 是一个变长整数数组。它的每个维度对应一个嵌套层级，该维度上的数值是当前层级内的绝对偏移索引。例如 `[0, 2, 1]` 表示：顶层第 0 个元素 → 进入该元素的子 Bubble → 子 Bubble 内第 2 个元素 → 进入该元素的子 Bubble → 第 1 个元素。

### 寻址模式

AmritaSense 提供三种层级的寻址操作：

| 方法           | 行为                       | 适用场景                 |
| -------------- | -------------------------- | ------------------------ |
| `near_to(n)`   | 替换当前层级的索引为 `n`   | 同一 Bubble 内的跳转     |
| `offset(n)`    | 在当前层级索引上增加 `n`   | 同一 Bubble 内的相对跳转 |
| `far_to(addr)` | 用完整地址向量替换当前指针 | 跨 Bubble 跳转           |

### 作用域隔离

Bubble 的核心价值在于**作用域隔离**：

- 每个 Bubble 拥有独立的 `near` 地址空间。Bubble 内部的跳转指令只在该 Bubble 内部有效，不会越界影响外层
- 当一个 Bubble 执行完毕，解释器自动弹出指针向量的最后一个维度，回到上一层 Bubble 继续推进
- 异常和中断的传播也遵循 Bubble 层级——它们可以穿透嵌套，但内部状态不会污染外层

### 应用

在复杂条件链中，不同分支可能各自包含嵌套的工作流结构。Bubble 作用域确保每个分支内部的节点跳转彼此隔离：

```python
complex_flow = (
    IF(cond1, GOTO("exit"))
    >> ALIAS(nested_workflow, "branch_a")
    >> ALIAS(NOP, "exit")
)
```

`nested_workflow` 是一个独立的 Bubble，其内部的 GOTO、CALL 等操作不会影响外层 `complex_flow` 的地址空间。这种隔离是 AmritaSense 能够安全处理多层嵌套工作流的关键——开发者可以像写代码一样用括号划清作用域边界，而解释器自动管理进出。
