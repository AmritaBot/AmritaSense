# 4.5.4 NOP 哨兵指令与 INTERRUPT 强制终止指令

`NOP` 和 `INTERRUPT` 是 AmritaSense 指令集中两个特殊的“原子”指令。它们不是 `SelfCompileInstruction`，没有编译期展开的空间结构，而是直接作为单个节点存在于工作流中，其功能完全体现在运行时的行为上。

## NOP 哨兵指令

`NOP`（No Operation）是一个**空操作哨兵节点**。它存在的意义不是“做什么”，而是“站在哪里”，为跳转指令提供一个合法的目标地址。

### 实现

```python
@_node_fun(wrap_to_async=False, address_able=True)
def _no_operation() -> None:
    pass

NOP: _Node[None] = _no_operation
```

### 关键属性

- `address_able=True`：这是它最重要的特性。一个可寻址的节点才能被 `ALIAS` 标记，进而成为 `GOTO` 或 `CALL` 的目标。`NOP` 将这一点作为其核心职责
- `wrap_to_async=False`：纯同步函数，执行时仅是一次 `return None`，几乎零开销

### 典型用途

**作为跳转的汇合点**：在条件分支中，无论走哪个分支，最终都跳到同一个 `NOP` 继续执行：

```python
# IF(cond, GOTO("then")) >> ... >> ALIAS(NOP, "end_if")
```

`NOP` 为不同控制流路径提供了一个统一的汇合地址。

**作为子程序的返回点**：`ARCHIVED_NODES` 中的子程序以 `NOP` 结尾，子程序执行完毕后，解释器步进到 `NOP`，随即 `call_sub` 的 `finally` 块弹栈恢复调用者。

**作为 ELSE 空分支**：`IF(cond, do).ELSE(NOP)` —— 语义上表示“条件不成立时什么都不做”，`NOP` 让这个意图显式化。

## INTERRUPT 强制终止指令

`INTERRUPT` 是工作流的**紧急终止按钮**。执行到它时，工作流立即、无条件、干净地退出。

### 实现

```python
@_node_fun(wrap_to_async=False, address_able=False)
def _interrput_operation() -> NoReturn:
    raise InterruptNotice("Interrupt Node")

INTERRUPT: _Node[NoReturn] = _interrput_operation
```

### 执行机制

1. **抛出 `InterruptNotice`**：这个异常是 `BaseException` 的子类，不是普通的 `Exception`
2. **全局捕获**：解释器主循环在最外层专门捕获 `InterruptNotice`，一旦捕获，执行清理流程：
   - 清空 `_ret_addr_stack`（调用栈）
   - 重置 `_pointer`（指针向量）
   - 重置 `_jump_marked` 标记
3. **干净退出**：工作流以可控、可预测的方式终止，不留残留状态

### 关键属性

- `address_able=False`：它是终结符，不应该成为跳转目标。跳转到一个立即终止的节点毫无意义
- `NoReturn` 返回类型：类型系统明确告诉开发者，执行 `INTERRUPT` 之后的代码永不可达

### 异常穿透规则

`InterruptNotice` 是 `BaseException` 子类。在 Python 的异常体系中，`except Exception` 不会捕获 `BaseException` 的子类。因此，**工作流中的 `TRY/CATCH` 块默认无法捕获 `InterruptNotice`**，它天然具有穿透性。

唯一的例外：如果在 `WorkflowInterpreter` 初始化时**显式**将 `InterruptNotice` 加入 `exception_ignored` 元组，它将变为可捕获的普通异常。但通常情况下不需要这样做——`INTERRUPT` 的设计意图就是“不可拦截”的紧急终止。

### 使用场景

- **外部信号响应**：工作流执行过程中，外部系统发出终止信号，下一个节点边界检查到信号后，通过跳转或直接放置 `INTERRUPT` 来终止工作流
- **紧急安全停止**：在检测到不可恢复的错误或危险状态时，编排中主动插入的 `INTERRUPT` 节点触发立即退出
- **超时处理**：`@Node()` 节点在开始执行前检查超时条件，若超时则返回 `INTERRUPT`，强制终止后续流程

## 对比总结

|                | NOP                                | INTERRUPT                      |
| -------------- | ---------------------------------- | ------------------------------ |
| 职责           | 占位、汇合、返回点                 | 紧急终止                       |
| 可寻址         | 是                                 | 否                             |
| 返回类型       | `None`                             | `NoReturn`                     |
| 对控制流的影响 | 无，执行后自动推进                 | 彻底终止整个工作流             |
| 典型位置       | `ALIAS` 目标、分支尾部、子程序末尾 | 错误处理路径末端、超时检查之后 |

`NOP` 是编织复杂控制流的**静默节点**，`INTERRUPT` 是守护工作流安全边界的**最后防线**。两者一静一动，构成了 AmritaSense 控制流体系的基石。
