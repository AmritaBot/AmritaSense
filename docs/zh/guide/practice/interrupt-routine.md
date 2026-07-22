# 中断例程与中断返回

AmritaSense v0.4.x+ 引入了一项新能力：**工作流内部的中断式控制转移**——保存完整解释器状态，跳转到处理例程，然后恢复并返回。这类似于 CPU 在向量到中断服务例程（ISR）之前保存上下文并在返回时恢复。

> **与 PUSH_STACK / RET_FAR 的对比**
> `PUSH_STACK` / `RET_FAR` 仅管理**返回地址栈**——如同 CPU 只保存程序计数器。`PUSH_CONTEXT` / `POP_CONTEXT` 保存**完整解释器状态**——如同包含所有寄存器的完整 CPU 上下文切换。仅返回地址的方案请参见[手动栈空间管理分配](/zh/guide/practice/manual-stack-management)。

---

## 核心概念

### 上下文栈

每个 `WorkflowInterpreter` 现在维护一个**上下文栈**（`pc.context_stack`），一个 `InterpreterContext` 快照的后进先出栈。每个快照捕获：

| 字段                  | 描述                               |
| --------------------- | ---------------------------------- |
| `ptr`                 | 当前 `PointerVector`（程序计数器） |
| `exception_ignored`   | 绕过 TRY/CATCH 的异常类型          |
| `s_args` / `s_kwargs` | 依赖注入参数（可选）               |
| `stack`               | 返回地址栈（可选）                 |
| `exception`           | panic 异常（如有）                 |

### if_flag 标志位

`pc.if_flag` 是一个布尔值，标记解释器当前是否处于**中断上下文**中。它由 `INTERRUPT_INTO` 自动设置，由 `INTERRUPT_RET` 自动清除。当 `if_flag` 为 `True` 时，不能再次调用 `INTERRUPT_INTO`——这防止了在 IF 分支内嵌套 interrupt-into。

---

## 模式一：PUSH_CONTEXT + INTERRUPT_RET（最简上下文保存）

最简洁的模式——保存完整状态，跳转到子例程，恢复并返回。

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_RET, PUSH_CONTEXT

@Node()
async def start() -> None: ...
@Node()
async def sub_routine() -> None: ...
@Node()
async def after_restore() -> None: ...

comp = (
    start
    >> PUSH_CONTEXT("sub_entry")   # 保存状态，跳转到 sub
    >> after_restore                # INTERRUPT_RET 后在此恢复
    >> GOTO("done")
    >> ALIAS(sub_routine, "sub_entry")
    >> INTERRUPT_RET()              # 弹出并恢复
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

---

## 模式二：INTERRUPT_INTO + INTERRUPT_RET（显式返回地址的中断）

`INTERRUPT_INTO(jump_to, ret_to)` 接收**两个**地址：现在去哪里，以及返回哪里。这是 CPU 中断语义的最接近类比。

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()
async def main_logic() -> None: ...
@Node()
async def error_handler() -> None:
    print("处理错误")

handler_block = ARCHIVED_NODES(
    ALIAS(error_handler, "on_error"),
    INTERRUPT_RET(),
)

comp = (
    main_logic
    >> INTERRUPT_INTO("on_error", "restore_here")
    #     ^现在跳转              ^保存在上下文中的返回地址
    >> ALIAS(NOP, "restore_here")
    >> after_handler
    >> GOTO("done")
    >> handler_block
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

**执行过程：**

1. `INTERRUPT_INTO("on_error", "restore_here")` 保存解释器状态，**替换**保存的 ptr 为 `"restore_here"`，设置 `if_flag`，跳转到 `error_handler`。
2. `error_handler` 运行。`INTERRUPT_RET` 弹出并恢复状态——在 `"restore_here"` 处恢复。
3. `after_handler` 执行，然后 `GOTO("done")`。

---

## 模式三：配合 ARCHIVED_NODES 构建中断处理程序库

构建一组命名中断处理程序，正常执行时跳过。

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()
async def main_flow() -> None: ...

@Node()
async def handle_timeout() -> None:
    print("[超时处理] 正在清理...")

@Node()
async def handle_auth_failure() -> None:
    print("[认证处理] 正在刷新凭据...")

handler_library = ARCHIVED_NODES(
    ALIAS(handle_timeout, "timeout"),
    INTERRUPT_RET(),
    ALIAS(handle_auth_failure, "auth"),
    INTERRUPT_RET(),
)

comp = (
    main_flow
    >> INTERRUPT_INTO("timeout", "after_timeout")
    >> ALIAS(NOP, "after_timeout")
    >> GOTO("done")
    >> handler_library
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

---

## 模式四：嵌套中断

上下文栈支持**嵌套**保存/恢复——如同 CPU 处理嵌套中断。

```python
@Node()
async def outer_handler() -> None:
    print("  [外层] 开始...")
    # 内部触发 INTERRUPT_INTO

@Node()
async def inner_handler() -> None:
    print("    [内层] 深度处理")

handlers = ARCHIVED_NODES(
    ALIAS(outer_handler, "outer_handler"),
    INTERRUPT_INTO("inner_handler", "after_inner"),
    ALIAS(NOP, "after_inner"),
    INTERRUPT_RET(),                   # 外层返回
    ALIAS(inner_handler, "inner_handler"),
    INTERRUPT_RET(),                   # 内层返回
)

comp = (
    main_start
    >> INTERRUPT_INTO("outer_handler", "after_outer")
    >> ALIAS(NOP, "after_outer")
    >> after_all
    >> GOTO("done")
    >> handlers
    >> ALIAS(NOP, "done")
)
```

---

## 与外部中断的关系

| 机制                               | 来源     | 工作方式                                |
| ---------------------------------- | -------- | --------------------------------------- |
| `call_sub(interrupt=True)`         | **外部** | 外部代码在节点边界注入子程序            |
| `INTERRUPT_INTO` / `INTERRUPT_RET` | **内部** | `>>` 链中的指令执行上下文保存/跳转/恢复 |

外部机制请参见[外部中断调用](/zh/guide/advanced/external_interrupt)。

---

## 注意事项

1. **IF 分支内不能使用 INTERRUPT_INTO**：`pc.if_flag == True` 时抛出 `IllegalState`。
2. **显式 ret_to**：使用 `INTERRUPT_INTO` 时必须始终提供返回目标别名。
3. **返回时 if_flag 被清除**：`INTERRUPT_RET` 后 `pc.if_flag` 始终重置为 `False`。
4. **INTERRUPT_RET 执行 jump_to**：与其他跳转指令一样，设置 `_jump_marked = True`。
5. **依赖注入参数被保留**：`INTERRUPT_INTO` 始终包含 `s_args` 和 `s_kwargs`。
6. **上下文栈完整性**：确保每个 `PUSH_CONTEXT`/`INTERRUPT_INTO` 都有对应的 `INTERRUPT_RET`。
