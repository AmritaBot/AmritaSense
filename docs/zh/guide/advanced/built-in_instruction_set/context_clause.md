# 上下文快照与中断转移指令 (PUSH_CONTEXT/POP_CONTEXT/INTERRUPT_INTO/INTERRUPT_RET)

`PUSH_CONTEXT`、`POP_CONTEXT`、`INTERRUPT_INTO` 和 `INTERRUPT_RET` 是 v0.4.x+ 引入的四条指令，它们协同工作以提供**完整的解释器状态保存/恢复**——类似于 CPU 的上下文切换机制。

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
    alias_or_idata: str | list[int],
    *,
    exclude_deps: bool = True,
    exclude_stack: bool = True,
) -> NodeType[None]
```

将当前解释器状态的完整快照保存到**上下文栈**（`pc.context_stack`）上，**然后跳转到** `alias_or_idata`。快照以 `InterpreterContext` 数据类存储。

这是底层原语——与 `INTERRUPT_INTO` 不同，它**不**设置 `if_flag`。配合 `INTERRUPT_RET` 恢复；也可手动弹出并调用 `pc.rebase_context()`。

### 参数

| 参数             | 类型               | 默认值 | 说明                                   |
| ---------------- | ------------------ | ------ | -------------------------------------- |
| `alias_or_idata` | `str \| list[int]` | —      | 要跳转到的别名（运行时解析）或绝对地址 |
| `exclude_deps`   | `bool`             | `True` | 若为 `True`，从快照中排除依赖注入参数  |
| `exclude_stack`  | `bool`             | `True` | 若为 `True`，从快照中排除返回地址栈    |

### 保存内容

| 字段                  | 条件                            |
| --------------------- | ------------------------------- |
| `ptr` (PointerVector) | 始终保存（跳转前位置的快照）    |
| `exception_ignored`   | 始终保存                        |
| `s_args` / `s_kwargs` | 仅当 `exclude_deps=False` 时    |
| `stack`（返回地址栈） | 仅当 `exclude_stack=False` 时   |
| `extra`               | 始终保存（空字典）              |
| `exception`           | 始终保存（panic 异常或 `None`） |

### 执行流程

1. 将 `alias_or_idata` 解析为绝对地址。
2. 调用 `pc.dump_interpreter(exclude_deps, exclude_stack)` 构建 `InterpreterContext`。
3. 将上下文压入 `pc.context_stack`。
4. 调用 `pc.jump_to(addr)`——执行在目标处继续。

---

## POP_CONTEXT

```python
def POP_CONTEXT() -> NodeType[InterpreterContext]
```

从上下文栈弹出顶部 `InterpreterContext`，并**将其作为节点结果返回**。返回值流向解释器的步进生成器——**不会**自动流入下一个 `>>` 节点的参数。

要实际恢复状态，要么使用 `INTERRUPT_RET()` 自动弹出并恢复，要么在 `@Node` 函数内通过 `pc.context_stack.pop()` 手动弹出。

### 执行流程

1. 弹出 `pc.context_stack` 顶部。
2. 将 `InterpreterContext` 作为节点输出返回。

---

## INTERRUPT_INTO

```python
def INTERRUPT_INTO(
    jump_to: str | list[int],
    ret_to: str | list[int],
    if_state: bool = False,
) -> NodeType[None]
```

中断式控制转移的便捷指令。保存当前解释器状态并跳转到 `jump_to`，但**用 `ret_to` 覆盖保存的指针**，使 `INTERRUPT_RET` 在 `ret_to` 处恢复——而不是原始位置。

这反映了真实的 CPU 中断语义：返回地址显式地是被中断指令**之后**的指令。

### 参数

| 参数       | 类型               | 默认值  | 说明                           |
| ---------- | ------------------ | ------- | ------------------------------ |
| `jump_to`  | `str \| list[int]` | —       | 跳转到**哪里**（处理程序入口） |
| `ret_to`   | `str \| list[int]` | —       | 快照中保存的返回目标地址       |
| `if_state` | `bool`             | `False` | 跳转后为 `if_flag` 设置的值    |

### 执行流程

1. **守卫检查**：若 `pc.if_flag` 已为 `True`，抛出 `IllegalState("Interrupt into is not allowed in IF statement")`。
2. 设置 `pc.if_flag = if_state`。
3. 解析 `jump_to` 和 `ret_to` 地址（首次解析后缓存）。
4. 通过 `pc.dump_interpreter()` 保存解释器状态。
5. **覆盖** `ctx.ptr` 为 `PointerVector(ret_to)`。
6. 将上下文压入 `pc.context_stack`。
7. 通过 `pc.jump_to()` 跳转到 `jump_to`。

### 限制

- **不能在 IF 分支内使用**（`pc.if_flag == True` 时抛出异常）。

---

## INTERRUPT_RET

```python
def INTERRUPT_RET() -> NodeType[None]
```

`INTERRUPT_INTO` 的对应指令。从上下文栈弹出顶部 `InterpreterContext`，通过 `pc.rebase_context(ctx)` 将解释器恢复到中断前的状态。同时清除 `pc.if_flag`。

### 执行流程

1. 弹出 `pc.context_stack` 顶部的 `InterpreterContext`。
2. 调用 `pc.rebase_context(ctx)`——恢复指针、异常忽略列表、依赖注入参数、返回地址栈。
3. 设置 `pc.if_flag = False`。

---

## 三种保存/恢复机制对比

| 特性             | PUSH_STACK + RET_FAR | PUSH_CONTEXT + INTERRUPT_RET | INTERRUPT_INTO + INTERRUPT_RET |
| ---------------- | -------------------- | ---------------------------- | ------------------------------ |
| **保存内容**     | 仅返回地址           | 完整解释器状态               | 完整解释器状态                 |
| **保存时跳转**   | 否（需单独 GOTO）    | 是（跳转到目标）             | 是（jump_to）                  |
| **返回地址**     | PUSH_STACK 目标      | 从保存的指针恢复             | 显式 ret_to 参数               |
| **依赖注入参数** | 不保存               | 可选（exclude_deps=False）   | 始终保存                       |
| **if_flag 管理** | 不涉及               | 不涉及                       | 入口自动设置，出口自动清除     |
| **适用场景**     | 自定义调用/返回方案  | 上下文保存 + 跳转底层        | 中断式处理入口/出口            |
| **复杂度**       | 低                   | 低                           | 低                             |

---

## 示例

### 基本上下文保存/恢复

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_RET, PUSH_CONTEXT

@Node()
async def start() -> None:
    print("Start — 保存上下文")

@Node()
async def sub_work() -> None:
    print("  [子流程] 在隔离上下文中工作")

@Node()
async def after_restore() -> None:
    print("Back — 由 INTERRUPT_RET 恢复")

comp = (
    start
    >> PUSH_CONTEXT("sub_entry")
    >> after_restore
    >> GOTO("done")
    >> ALIAS(sub_work, "sub_entry")
    >> INTERRUPT_RET()
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

handler_block = ARCHIVED_NODES(
    ALIAS(handler, "int_handler"),
    INTERRUPT_RET(),
)

comp = (
    main_start
    >> INTERRUPT_INTO("int_handler", "restore_here")
    >> ALIAS(NOP, "restore_here")
    >> back
    >> GOTO("done")
    >> handler_block
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

> **另见**：[中断例程与中断返回](/zh/guide/practice/interrupt-routine) 了解高级模式。
