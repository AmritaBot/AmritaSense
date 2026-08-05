# 函数块调用

AmritaSense 提供了 `FN` / `INTER_FN` —— 看起来像高级语言**函数定义**的辅助结构。使用之前，必须认清一个关键事实：

> **函数块本质是一次控制流转移，不是真正的函数调用。** 它只是"跳入一段节点区域，再跳回来"。**没有函数上下文**：没有栈帧、没有局部变量、没有闭包捕获、没有参数自动传递、也没有返回值约定。"函数"只是一个方便的比喻。

## 函数块是什么（以及不是什么）

| 方面          | 高级语言函数             | AmritaSense `FN` / `INTER_FN`                          |
| ------------- | ------------------------ | ------------------------------------------------------ |
| 入口          | 调用方求值参数、压入栈帧 | `PUSH_AND_GOTO` / `INTERRUPT_INTO` 跳转到别名          |
| 局部变量      | 独立栈帧 + 局部变量      | ❌ 没有——解释器只有一份共享状态                        |
| 参数          | 按值/按引用传递          | ❌ 没有——数据通过**依赖注入**从解释器参数池流入        |
| 返回值        | `return expr`            | ❌ 没有——`RET_FAR` / `INTERRUPT_RET` 只恢复指针/上下文 |
| 栈            | 每个函数独立的调用栈     | 共享的 `_ret_addr_stack`（只记一个跳转目标）           |
| 递归          | 支持                     | ❌ 无意义——没有可供重新进入的栈帧                      |
| 闭包 / 作用域 | 词法作用域、捕获         | ❌ 没有——整个工作流共享同一个指针空间                  |

把函数块想象成一个**命名且归档的跳转目标**：进入它改变指针，结束它把指针改回来。除此之外你对函数的一切期待都不存在。

## `FN(entrypoint, block)` —— 普通函数块

```python
from amrita_sense.instructions import FN

fn_block = FN(
    "fn_entry",          # 必填：入口别名
    fn_body,             # NodeCompose 或 SelfCompileInstruction
)
```

`FN` 在编译期展开为：

```text
[_fn_escape, ALIAS(NOP, "fn_entry"), <block>, RET_FAR()]
```

- `_fn_escape` —— 隐藏节点（`rebase_ptr(pointer.copy().offset(3))`）。正常顺序流到达函数块时，它把指针 rebase **越过**整个块（`offset(3)` 恰好落在末尾 `RET_FAR` 上），因此整个块被跳过。
- `ALIAS(NOP, "fn_entry")` —— 命名入口。跳转以该别名为目标。
- `<block>` —— 你的函数体（嵌套容器，经指针进入）。
- `RET_FAR()` —— 自动追加。弹出 `_ret_addr_stack`，`rebase_ptr` 到调用方保存的地址，解释器随后推进到调用点之后的节点。

### 调用 FN 函数块

```python
from amrita_sense.instructions import PUSH_AND_GOTO

comp = (
    start
    >> PUSH_AND_GOTO(None, "fn_entry")   # 调用：None = 返回调用点之后的节点
    >> after_fn                           # RET_FAR 之后在这里恢复执行
    >> fn_block                           # 正常流经 _fn_escape 跳过
)
```

`PUSH_AND_GOTO(None, entrypoint)` 压入当前指针（主流程语义：不在 `call_sub` 内时 `None` 解析为当前指针）并跳到入口。`RET_FAR` 把指针恢复到那里，解释器推进到下一节点——即 `after_fn`。

## `INTER_FN(entrypoint, block)` —— 中断服务例程

```python
from amrita_sense.instructions import INTER_FN

isr = INTER_FN(
    "isr_entry",
    isr_body,
)
```

结构相同，但末尾指令是 `INTERRUPT_RET()` 而非 `RET_FAR`：

```text
[_fn_escape, ALIAS(NOP, "isr_entry"), <block>, INTERRUPT_RET()]
```

`INTERRUPT_RET` 弹出保存的 `InterpreterContext` 并**恢复整个解释器状态**（指针、异常忽略表、依赖参数、返回地址栈）——不只是指针。

### 调用 INTER_FN 函数块

```python
from amrita_sense.instructions import INTERRUPT_INTO

comp = (
    main_start
    >> INTERRUPT_INTO("isr_entry", None)  # 派发：None = 返回调用点之后的节点
    >> after_isr                          # INTERRUPT_RET 之后在这里恢复执行
    >> isr                                # 正常流经 _fn_escape 跳过
)
```

`INTERRUPT_INTO(entrypoint, None)` 快照解释器上下文（以当前指针为返回地址）并跳到处理器。例程结束时 `INTERRUPT_RET` 恢复快照；恢复使用 `rebase_context`（不设跳转标记），执行推进到下一节点——即 `after_isr`。

## 与 `ARCHIVED_SEGMENT` 的关系

`FN` / `INTER_FN` 已内嵌自己的跳过机制（`_fn_escape`），函数块可以直接放进 `>>` 链，无需额外包裹：

```python
comp = (
    start
    >> PUSH_AND_GOTO(None, "fn_entry")
    >> after_fn
    >> FN("fn_entry", fn_body)   # 可以——不需要 ARCHIVED_SEGMENT
)
```

`ARCHIVED_SEGMENT` 是更底层的积木（`[JMP 2, Payload, NOP]`），用于归档任意编排而不带函数调用语义——例如一段只能通过 `GOTO` 进入、由自己手动返回（`RET_FAR` / `INTERRUPT_RET`）的普通区域。

## 没有函数上下文时的数据交换

因为没有参数传递，请通过工作流的**依赖注入**共享数据：

```python
@Node()
async def fn_body(ctx: WorkflowContext) -> None:
    ...  # DI 从解释器参数池解析 `ctx`
```

解释器从同一份 `_ava_args` / `_ava_kwargs` 池解析函数体的参数——函数块在**调用方的上下文**中执行，而不是一个全新的上下文。

## 小结

- `FN` / `INTER_FN` 是**命名且归档的跳转目标**，末尾自动追加返回指令。
- 它们改变的是**控制流**，不是执行上下文。
- 通过 `PUSH_AND_GOTO(None, entrypoint)` / `INTERRUPT_INTO(entrypoint, None)` 进入；通过自动追加的 `RET_FAR()` / `INTERRUPT_RET()` 退出。
- 没有局部变量、没有参数、没有返回值、没有递归——请据此设计（数据用依赖注入，"返回"用指针/上下文恢复）。
