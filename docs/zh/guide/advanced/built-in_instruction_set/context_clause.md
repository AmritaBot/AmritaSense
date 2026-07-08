# 上下文快照与中断转移指令 (PUSH_CONTEXT/POP_CONTEXT/INTERRUPT_INTO/INTERRUPT_RET)

`PUSH_CONTEXT`、`POP_CONTEXT`、`INTERRUPT_INTO` 和 `INTERRUPT_RET` 是 v0.3.x+ 引入的四条指令，它们协同工作以提供**完整的解释器状态保存/恢复**——类似于 CPU 的上下文切换机制。

> **核心区分**
> `PUSH_STACK` / `RET_FAR` 仅保存和恢复**返回地址**（`_ret_addr_stack`）。`PUSH_CONTEXT` / `POP_CONTEXT` 保存和恢复**整个解释器状态**：指针、异常忽略列表、依赖注入参数、返回地址栈和 panic 异常。`INTERRUPT_INTO` / `INTERRUPT_RET` 将前者封装为便捷的"中断 ➔ 处理 ➔ 返回"模式。

## 指令特性：非自编译的直接节点

四条指令均**不是** `SelfCompileInstruction`。它们不会在编译期展开为 `NodeCompose` 结构，而是作为单个节点存在于工作流数组中，在运行时直接修改解释器状态。

它们从 `amrita_sense.instructions` 导出：

```python
from amrita_sense.instructions import (
    PUSH_CONTEXT,
    POP_CONTEXT,
    INTERRUPT_INTO,
    INTERRUPT_RET,
)
```

## PUSH_CONTEXT

```python
def PUSH_CONTEXT(
    exclude_deps: bool = True,
    exclude_stack: bool = True,
) -> NodeType[None]
```

将当前解释器状态的完整快照保存到**上下文栈**（`pc.context_stack`）上。快照以 `InterpreterContext` 数据类存储。

### 参数

| 参数            | 类型   | 默认值 | 说明                                  |
| --------------- | ------ | ------ | ------------------------------------- |
| `exclude_deps`  | `bool` | `True` | 若为 `True`，从快照中排除依赖注入参数 |
| `exclude_stack` | `bool` | `True` | 若为 `True`，从快照中排除返回地址栈   |

### 保存内容

| 字段                  | 条件                            |
| --------------------- | ------------------------------- |
| `ptr` (PointerVector) | 始终保存                        |
| `exception_ignored`   | 始终保存                        |
| `s_args` / `s_kwargs` | 仅当 `exclude_deps=False` 时    |
| `stack`（返回地址栈） | 仅当 `exclude_stack=False` 时   |
| `extra`               | 始终保存（空字典）              |
| `exception`           | 始终保存（panic 异常或 `None`） |

### 执行流程

1. 调用 `pc.dump_interpreter(exclude_deps, exclude_stack)` 构建 `InterpreterContext`。
2. 将上下文压入 `pc.context_stack`。
3. 返回 `None`——执行继续到 `>>` 链中的下一个节点。

---

## POP_CONTEXT

```python
def POP_CONTEXT() -> NodeType[InterpreterContext]
```

从上下文栈弹出顶部 `InterpreterContext`，并将其**作为节点结果返回**。调用方自行决定如何处理上下文——可以检查、序列化，或传递给 `pc.rebase_context(ctx)` 以真正恢复保存的状态。

### 执行流程

1. 弹出 `pc.context_stack` 顶部。
2. 将 `InterpreterContext` 作为节点输出返回。
3. **`>>` 链中的下一个节点**以该 `InterpreterContext` 作为输入参数接收。

### 重要说明

`POP_CONTEXT` **不会**自动恢复状态。若需恢复，接收节点必须调用 `pc.rebase_context(ctx)`：

```python
@Node()
async def restore(ctx: InterpreterContext, pc: WorkflowInterpreter) -> None:
    pc.rebase_context(ctx)
```

或使用 `INTERRUPT_RET()` 自动执行恢复。

---

## INTERRUPT_INTO

```python
def INTERRUPT_INTO(
    alias_or_idata: str | list[int],
    if_state: bool = False,
) -> NodeType[None]
```

一条便捷指令，在单个节点中组合 `PUSH_CONTEXT` + `jump_to`。它保存当前解释器状态后跳转到目标地址——正如 CPU 中断在向量到 ISR 之前保存上下文。

### 参数

| 参数             | 类型               | 默认值  | 说明                                 |
| ---------------- | ------------------ | ------- | ------------------------------------ |
| `alias_or_idata` | `str \| list[int]` | —       | 目标别名（运行时解析）或绝对地址向量 |
| `if_state`       | `bool`             | `False` | 跳转后为解释器的 `if_flag` 设置的值  |

### 执行流程

1. **守卫检查**：若 `pc.if_flag` 已为 `True`，抛出 `IllegalState("Interrupt into is not allowed in IF statement")`。不允许在 IF 分支内嵌套 interrupt-into 调用。
2. 设置 `pc.if_flag = if_state`。
3. 若为字符串，通过 `pc.find_addr_alias()` 解析别名为绝对地址。
4. 通过 `pc.dump_interpreter()` 保存解释器状态并压入 `pc.context_stack`。
5. 通过 `pc.jump_to(addr)` 跳转到目标地址。

### 限制

- **不能在 IF 分支内使用**（`pc.if_flag == True` 时抛出异常）。这防止中断式跳转破坏条件流程的完整性。

---

## INTERRUPT_RET

```python
def INTERRUPT_RET() -> NodeType[None]
```

`INTERRUPT_INTO` 的对应指令。从上下文栈弹出顶部 `InterpreterContext`，并通过 `pc.rebase_context(ctx)` 将解释器恢复到中断前的状态。同时清除 `pc.if_flag`。

### 执行流程

1. 从 `pc.context_stack` 弹出顶部 `InterpreterContext`。
2. 调用 `pc.rebase_context(ctx)`——恢复指针、异常忽略列表、依赖注入参数、返回地址栈。
3. 设置 `pc.if_flag = False`。

这是从通过 `INTERRUPT_INTO` 进入的处理程序中返回的推荐方式。

---

## 三种保存/恢复机制对比

| 特性             | PUSH_STACK + RET_FAR | PUSH_CONTEXT + POP_CONTEXT       | INTERRUPT_INTO + INTERRUPT_RET |
| ---------------- | -------------------- | -------------------------------- | ------------------------------ |
| **保存内容**     | 仅返回地址           | 完整解释器状态                   | 完整解释器状态                 |
| **依赖注入参数** | 不保存               | 可选（`exclude_deps=False`）     | 始终保存                       |
| **返回地址栈**   | 调用方手动管理       | 可选（`exclude_stack=False`）    | 始终保存                       |
| **if_flag 管理** | 不涉及               | 不涉及                           | 入口自动设置，出口自动清除     |
| **恢复方式**     | `RET_FAR` 弹出并跳转 | 调用方调用 `rebase_context(ctx)` | `INTERRUPT_RET` 自动恢复       |
| **适用场景**     | 自定义调用/返回方案  | 细粒度状态检查/操作              | 中断式处理入口/出口            |
| **复杂度**       | 低                   | 中（需手动 rebase）              | 低（一键保存/恢复）            |

---

## 示例

### 基本上下文保存/恢复

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, POP_CONTEXT, PUSH_CONTEXT

@Node()
async def start() -> None:
    print("Start — 保存上下文")

@Node()
async def sub_work() -> None:
    print("  [子流程] 在隔离上下文中工作")

@Node()
async def inspect_context(ctx) -> None:
    # ctx 是 POP_CONTEXT 弹出的 InterpreterContext
    print(f"  上下文快照 — 指针位于: {ctx.ptr}")

@Node()
async def finish() -> None:
    print("完成")

comp = (
    start
    >> PUSH_CONTEXT()
    >> GOTO("sub")
    >> ALIAS(sub_work, "sub")
    >> POP_CONTEXT()
    >> inspect_context
    >> finish
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

### 中断式处理程序（配合 ARCHIVED_NODES）

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()
async def main_start() -> None:
    print("[主流程] 触发中断...")

@Node()
async def handler() -> None:
    print("  [处理程序] 正在处理中断")

@Node()
async def back() -> None:
    print("[主流程] 从中断返回")

# 存档处理程序——正常执行时跳过
handler_block = ARCHIVED_NODES(
    ALIAS(handler, "int_handler"),
    INTERRUPT_RET(),
)

comp = (
    main_start
    >> INTERRUPT_INTO("int_handler")
    >> back
    >> GOTO("done")
    >> handler_block
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

### 在快照中包含依赖注入参数

```python
# 保存所有内容，包括依赖注入状态
comp = (
    start
    >> PUSH_CONTEXT(exclude_deps=False, exclude_stack=False)
    >> GOTO("sub")
    >> ALIAS(sub_work, "sub")
    >> POP_CONTEXT()
    >> restore_and_continue  # 接收完整的 InterpreterContext
)
```

> **另见**：[中断例程与中断返回](/zh/guide/practice/interrupt-routine) 了解高级模式，包括嵌套中断、手动 rebase 以及与外部中断调用的集成。
