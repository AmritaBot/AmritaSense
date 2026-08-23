# 高级主题：手动栈空间管理分配

`CALL` 指令和 `call_sub` 方法会为你自动管理返回地址栈（`_ret_addr_stack`）：进入子程序前压入当前指针，`finally` 块在返回时弹出。对于大多数工作流，这已经足够。

然而，AmritaSense 也暴露了返回地址栈供**手动控制**，通过 `PUSH_STACK` 和 `RET_FAR` 实现。其使用模式为：

1. **PUSH_STACK**——将别名或地址压入 `_ret_addr_stack`
2. **GOTO 跳转**——跳转到工作流中的其他位置
3. **RET_FAR 返回**——弹出保存的地址并跳回

这让你可以实现不遵循 `CALL`/`call_sub` 固定规则的自定义调用/返回方案。

## 返回地址栈

`_ret_addr_stack` 是 `WorkflowInterpreter` 上的一个 `Stack[PointerVector]`。`CALL` 将当前指针压入其中；`call_sub` 的 `finally` 块弹出并恢复。通过 `PUSH_STACK`，你可以在编排链中直接将任意别名目标压栈，无需编写自定义节点。

```mermaid
sequenceDiagram
    participant N as PUSH_STACK
    participant S as _ret_addr_stack
    participant W as 工作区

    N->>S: push(target_addr)
    N->>W: GOTO("work")
    W-->>W: 执行...
    W->>S: RET_FAR 弹栈
    W->>N: rebase_ptr(base_addr) → advance 落到目标
```

## PUSH_STACK 与 RET_FAR

- `PUSH_STACK(alias_or_idata)`——将目标别名（或裸地址列表）解析后的地址压入 `_ret_addr_stack`。该指令返回的是一个 `NodeType[None]`（内联 `@Node` 装饰的可调用对象），直接放在 `>>` 链中。
- `RET_FAR()`——从 `_ret_addr_stack` 弹出栈顶条目，通过 `rebase_ptr` 恢复指针。与 `jump_to` / `jump_far_ptr` 不同，`rebase_ptr` **不会**设置跳转标记，解释器在返回后会自然**推进到下一指令**（`返回地址 + 1`）。调用方应压入 `目标 - 1`，使 advance 恰好落在目标节点上。

两个指令都**不能**从 `@Node()` 函数内部 `return`——直接放在 `>>` 链中。

## 示例：PUSH_STACK + GOTO + RET_FAR

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, PUSH_STACK, RET_FAR


@Node()
async def start() -> None:
    print("开始")


@Node()
async def doing_work() -> None:
    """GOTO 跳入的工作区。"""
    print("  执行工作")


@Node()
async def after_return() -> None:
    """RET_FAR 弹栈后在此恢复执行。"""
    print("回到这里（通过 RET_FAR）")


comp = (
    start
    >> PUSH_STACK("resume")  # 压入返回地址（after_return 前面的 NOP）
    >> GOTO("work")  # 跳入工作区
    >> ALIAS(NOP, "resume")  # RET_FAR rebase 到这里；advance 落到 after_return
    >> after_return
    >> ALIAS(doing_work, "work")
    >> RET_FAR()
)
await WorkflowInterpreter(comp.render()).run()
```

**执行流程**（新 `RET_FAR` 语义）：

1. `PUSH_STACK("resume")` 将别名为 `"resume"` 的 `NOP`（即 `after_return` **前一个**节点）的地址压入 `_ret_addr_stack`
2. `GOTO("work")` 跳转到 `doing_work` 节点
3. `doing_work` 执行完毕后，`RET_FAR` 弹出保存的地址并 `rebase_ptr` 到那里，解释器随后推进到 `after_return`

> 因为 `RET_FAR` 不设置跳转标记，保存的地址必须是真正目标的**前驱**（`目标 - 1`）。这里的 `"resume"` NOP 就扮演这个角色。

## PUSH_AND_GOTO（v0.3.0+）

`PUSH_AND_GOTO(from_adr, to_adr)` 是一个便捷指令，将 `PUSH_STACK` + `GOTO` 合并为一个节点。内部执行：

1. 将 `from_adr` 压入 `_ret_addr_stack`（与 `PUSH_STACK` 一致）
2. 跳转到 `to_adr`（与 `GOTO` 一致）

`from_adr` 接受别名字符串、裸地址列表，或 `None`。为 `None` 时：

- 在子程序调用内部（`pc.outer_interpreting` 为 `True`——即通过 `call_sub` 进入的执行），复用 `_ret_addr_stack` 栈顶（父级压入的返回地址）。
- 否则（主流程 `run()`），使用当前指针——`RET_FAR` 随后会推进到 `PUSH_AND_GOTO` 之后的节点。

```python
from amrita_sense.instructions import PUSH_AND_GOTO, RET_FAR
from amrita_sense.instructions.subprogram import ARCHIVED_SEGMENT

# 模式 A：显式两步（压入前驱 + GOTO）
comp_a = (
    start
    >> PUSH_STACK("resume")
    >> GOTO("work")
    >> ALIAS(NOP, "resume")
    >> after_return
    >> ALIAS(doing_work, "work")
    >> RET_FAR()
)

# 模式 B：PUSH_AND_GOTO 便捷写法——None = 当前指针
# RET_FAR rebase 到 PUSH_AND_GOTO 自身，advance 落到 after_return。
# 函数体藏进 ARCHIVED_SEGMENT，正常流跳过。
comp_b = (
    start
    >> PUSH_AND_GOTO(None, "work")
    >> after_return
    >> ARCHIVED_SEGMENT(ALIAS(doing_work, "work") >> RET_FAR())
)
```

`PUSH_AND_GOTO` 在语义上与两步模式等价（`None` 默认值覆盖了最常见的“返回到下一节点”场景）。注意：模式 B 中函数体必须归档（`ARCHIVED_SEGMENT`）——否则正常流在 `after_return` 之后会再次进入函数体。

## 何时使用手动栈管理

| 场景                | 方案                              |
| ------------------- | --------------------------------- |
| 简单子程序调用/返回 | `CALL` + 自然的 `call_sub` 返回   |
| 自定义返回目标      | `PUSH_STACK` + `GOTO` + `RET_FAR` |
| 压栈跳转便捷方式    | `PUSH_AND_GOTO` + `RET_FAR`       |
| 多级栈展开          | 压入多个地址，每级一个 `RET_FAR`  |
| 非线性控制流        | 结合 `GOTO` 实现任意跳转模式      |

## 子图式调用：配合 FN 使用

v0.6.0 起，编写自包含"子程序"的现代方式是 **`FN(entrypoint, block)`**——它内嵌跳过机制（`_fn_escape`）并自动追加 `RET_FAR()`。用 `PUSH_AND_GOTO(None, entrypoint)` 调用即可，无需手动 `PUSH_STACK` / `GOTO` / `RET_FAR` 管线：

```python
from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.instructions import FN, PUSH_AND_GOTO


@Node()
async def start() -> None:
    print("开始")


@Node()
async def step1() -> None:
    print("  步骤 1")


@Node()
async def step2() -> None:
    print("  步骤 2")


@Node()
async def after_return() -> None:
    print("回到这里（通过 FN）")


# 自包含子程序：正常流经 _fn_escape 跳过，
# PUSH_AND_GOTO 进入；FN 自动在末尾追加 RET_FAR()。
subroutine = FN("sub_entry", step1 >> step2)

comp = (
    start
    >> PUSH_AND_GOTO(None, "sub_entry")  # None = 返回本节点之后
    >> after_return  # RET_FAR rebase 到调用点 -> advance 落到这里
    >> subroutine
)
await WorkflowInterpreter(comp.render()).run()
```

**执行流程**（新 `RET_FAR` 语义）：

1. `PUSH_AND_GOTO(None, "sub_entry")` 压入当前指针并跳入子程序
2. `step1 >> step2` 顺序执行
3. 自动追加的 `RET_FAR()` 弹出保存的地址，`rebase_ptr` 到调用点，解释器随后推进到 `after_return`

> **FN 与手动栈操作**：`PUSH_STACK` / `GOTO` / `RET_FAR` 仍可用于完全手动栈控制（非线性流、多级展开）。普通"调用例程并返回"场景推荐 `FN` + `PUSH_AND_GOTO`——更不易出错。

> 对于完整函数体或中断服务例程，优先使用 `ARCHIVED_SEGMENT`（配合 `FN` / `INTER_FN` 或在末尾显式 `RET_FAR`），而不是 `ARCHIVED_NODES`——后者面向归档单个节点或很短序列。

## 注意事项

- **栈完整性**：`RET_FAR` 无条件从 `_ret_addr_stack` 弹出。如果栈为空，会引发 `IndexError`。始终确保在到达 `RET_FAR` 之前已压入对应地址（通过 `CALL` 或 `PUSH_STACK`）。
- **返回地址 + 1**：`RET_FAR` 使用 `rebase_ptr`（不设跳转标记），执行在保存地址的**下一个节点**恢复。请压入 `目标 - 1`（或依赖 `PUSH_AND_GOTO` 的 `None` 默认值——它指向指令自身）。
- **不是子程序指令**：`PUSH_STACK` 和 `RET_FAR` 是编排链中的独立节点。不要从 `@Node()` 函数内部调用它们——直接放在 `>>` 链中。
