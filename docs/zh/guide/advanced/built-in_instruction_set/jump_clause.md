# 4.5.3 GOTO 与 CALL 跳转指令

`GOTO` 与 `CALL` 是 AmritaSense 中两种核心的控制流跳转指令。它们共享同一套基于 `ALIAS` 的地址解析基础设施，但服务于截然不同的场景：`GOTO` 是无条件单向跳转，`CALL` 是带返回的子程序调用。

> **共同基础**
> 两者都依赖 `ALIAS` 系统注册的符号名来寻址，都在 `_pre_check` 阶段完成地址解析和拼写纠错，都使用 `@markup` 装饰器管理跳转标记。理解这些共同机制，有助于掌握两者的本质差异。

## 指令特性：非自编译的直接节点

`GOTO` 和 `CALL` **不是** `SelfCompileInstruction`。它们不会在编译期展开为 `NodeCompose` 结构，而是直接作为单个跳转节点存在于工作流数组中。

这意味着：

- 它们在编译产物里就是一个 `JumpNode` 或 `CallNode` 元素
- 执行时不会创建新的 Bubble 或嵌套作用域
- 所有行为完全体现在运行时的地址解析与指针改写上

## GOTO 指令

`GOTO` 是对 `JumpNode` 的工厂封装，执行时调用解释器的 `jump_to` 方法，完成一次**单向、不返回**的指针改写。

### 执行流程

1. **地址解析**（`_pre_check` 阶段）：将别名查表解析为 `list[int]` 绝对地址，或直接验证裸地址的有效性
2. **跳转标记**：调用 `pc.jump_to(addr)`，该方法受 `@markup` 保护，设置 `_jump_marked=True`
3. **指针替换**：`_pointer` 被完整替换为目标地址向量
4. **解释器响应**：主循环检测到 `_jump_marked`，跳过常规的 `advance_pointer()` 步进，下一轮迭代从跳转目标开始执行

### 关键特性

- **不管理调用栈**：GOTO 不会向 `_ret_addr_stack` 压入任何内容。跳了就跳了，没有“返回”的概念
- **可在任意层级跳转**：因为 `far_to(addr)` 直接替换整个指针向量，GOTO 可以跨越 Bubble 边界
- **别名与裸地址双模**：`GOTO("target")` 使用符号名，`GOTO([1, 2, 3])` 使用绝对地址

### 典型使用场景

- **错误处理跳转**：在检测到错误时，直接跳到统一的错误处理节点
- **分支合并**：多个条件分支最终跳转到同一个汇合点 `NOP`
- **状态机转换**：在复杂状态机中，根据运行时状态跳转到不同的下一状态

## CALL 指令

`CALL` 是对 `CallNode` 的工厂封装，执行时调用解释器的 `call_sub` 方法，完成一次**压栈 -> 跳转 -> 执行 -> 弹栈返回**的子程序调用。

### 执行流程

1. **地址解析**（`_pre_check` 阶段）：将别名查表解析为 `list[int]` 绝对地址并缓存
2. **压栈保存**：`call_sub` 将当前指针向量压入 `_ret_addr_stack`
3. **指针替换**：执行指针被设置为目标子程序的入口地址
4. **子程序执行**：解释器从入口开始推进，执行子程序内所有节点
5. **弹栈返回**：子程序执行完毕后，`call_sub` 的 `finally` 块从 `_ret_addr_stack` 弹出原指针并恢复
6. **继续推进**：解释器从 CALL 指令的下一个节点继续执行

### 关键特性

- **管理调用栈**：压栈保存返回地址，弹栈恢复，支持多层嵌套调用
- **子程序来源**：目标子程序通常由 `ARCHIVED_NODES` 定义，但 CALL 本身不限定目标必须来自存储区——任何有合法别名的节点序列都可以被 CALL 调用
- **参数传递**：CALL 指令自身不传递参数。若子程序节点需要参数，应通过 `Depends` 依赖注入声明，或在子程序节点内部自行调用 `call_sub` 传入操作数

### 典型使用场景

- **代码复用**：将可复用的节点序列封装为子程序，在工作流中多次 CALL 调用
- **模块化分解**：将复杂流程拆分为独立子程序，主流程只保留编排逻辑
- **中断处理**：外部系统通过 `call_sub(interrupt=True)` 调用预置的中断处理子程序

## GOTO vs CALL：对比总结

|                  | GOTO                         | CALL                         |
| ---------------- | ---------------------------- | ---------------------------- |
| 是否保存返回地址 | 否                           | 是（压入 `_ret_addr_stack`） |
| 执行完毕后行为   | 从目标节点继续向后推进       | 自动弹栈，回到调用点继续     |
| 调用栈影响       | 无                           | 压栈一次，弹栈一次           |
| 适用场景         | 单向跳转、分支合并、错误跳转 | 子程序复用、模块化、中断响应 |
| 底层 API         | `pc.jump_to(addr)`           | `pc.call_sub(addr)`          |

## 使用注意

- **GOTO 不能替代循环**：GOTO 没有“返回”语义，如果在循环内部使用 GOTO 跳出，循环的调用栈不会被正确管理。循环内需要跳出应使用 `BreakLoop`，循环内需要子程序复用应使用 CALL
- **CALL 的目标必须是可寻址节点**：被调用的节点（或子程序入口节点）必须具有 `address_able=True`，这是 `ALIAS` 的前提条件
- **GOTO 与 CALL 共享别名空间**：两者都从 `alias2vector_map` 查表，别名污染会影响两种指令。保持别名命名规范，避免冲突
- **CALL 的返回依赖调用栈完整**：在子程序内部使用 GOTO 会设置 `_jump_marked`，导致 `call_sub` 跳过弹栈恢复。开发者需要理解：子程序内的 GOTO 会“覆盖”正常的返回行为

## 示例

```python
from amrita_sense.instructions import GOTO, CALL, ALIAS, ARCHIVED_NODES
from amrita_sense.node import Node

@Node()
def error_handler():
    print("Handling error")

@Node()
def reusable_step():
    print("Executing reusable logic")

# GOTO：错误时直接跳转
workflow = (
    start
    >> do_something
    >> GOTO("error_cleanup")
    >> ALIAS(error_handler, "error_cleanup")
)

# CALL：复用封装的子程序
subprogram = ARCHIVED_NODES(
    ALIAS(reusable_step, "reusable"),
)

main = (
    init
    >> CALL("reusable")   # 第一次调用
    >> process
    >> CALL("reusable")   # 第二次复用
    >> end
    >> subprogram         # 子程序放在末尾，正常流程跳过
)
```

> **手动栈空间管理**：`PUSH_STACK` + `GOTO` + `RET_FAR` 可显式控制返回地址栈，配合 `ARCHIVED_NODES` 还能实现子图式调用。完整说明请参见：[高级主题：手动栈空间管理分配](/zh/guide/practice/manual-stack-management)。
