# 中断例程与中断返回

AmritaSense v0.3.x+ 引入了一项新能力：**工作流内部的中断式控制转移**——保存完整解释器状态，跳转到处理例程，然后恢复并返回。这类似于 CPU 在向量到中断服务例程（ISR）之前保存上下文并在返回时恢复。

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

## 模式一：INTERRUPT_INTO + INTERRUPT_RET（最简模式）

最简洁的模式——适用于大多数中断场景。

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()  async def main_logic() -> None: ...
@Node()  async def error_handler() -> None:
    print("处理错误，返回时将恢复上下文")
@Node()  async def after_handler() -> None: ...

# 步骤1：在 ARCHIVED_NODES 中定义处理程序
handler_block = ARCHIVED_NODES(
    ALIAS(error_handler, "on_error"),
    INTERRUPT_RET(),  # <-- 恢复上下文并返回
)

# 步骤2：在主编排中使用 INTERRUPT_INTO
comp = (
    main_logic
    >> INTERRUPT_INTO("on_error")    # 保存状态 + 跳转
    >> after_handler                  # INTERRUPT_RET 后在此恢复执行
    >> GOTO("done")
    >> handler_block
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

**执行过程：**

1. `INTERRUPT_INTO("on_error")` 保存完整解释器状态并跳转到 `error_handler`。
2. `error_handler` 运行。然后 `INTERRUPT_RET` 恢复保存的状态（指针、异常忽略列表等）并跳回。
3. 解释器在 `after_handler` 处继续执行。

---

## 模式二：手动 PUSH_CONTEXT + GOTO + rebase_context（精细控制）

当需要在恢复前检查或修改保存的上下文时，使用手动上下文管理。

```python
from amrita_sense import ALIAS, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, POP_CONTEXT, PUSH_CONTEXT

@Node()  async def start() -> None:
    print("正在保存上下文...")

@Node()  async def sub_routine() -> None:
    print("  [子流程] 在子例程中工作")
    # 可以在此修改 pc 状态——恢复后修改可见

@Node()
async def examine_and_restore(ctx: InterpreterContext, pc: WorkflowInterpreter) -> None:
    """接收弹出的上下文，检查后恢复。"""
    print(f"  保存的指针位置: {ctx.ptr}")
    print(f"  忽略的异常: {ctx.exception_ignored}")
    # 可在恢复前选择性地修改 ctx
    pc.rebase_context(ctx)

@Node()  async def finish() -> None:
    print("回到原始流程")

comp = (
    start
    >> PUSH_CONTEXT()
    >> GOTO("sub")
    >> ALIAS(sub_routine, "sub")
    >> POP_CONTEXT()
    >> examine_and_restore
    >> finish
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

**适用场景：**

- 需要在恢复前检查保存的状态。
- 需要条件性恢复或修改上下文。
- 需要序列化上下文用于调试/审计。

---

## 模式三：配合 ARCHIVED_NODES 构建中断处理程序库

构建一组命名中断处理程序，正常执行时跳过。

```python
from amrita_sense import ALIAS, ARCHIVED_NODES, NOP, Node, WorkflowInterpreter
from amrita_sense.instructions import GOTO, INTERRUPT_INTO, INTERRUPT_RET

@Node()  async def main_flow() -> None: ...

# --- 处理程序库 ---
@Node()  async def handle_timeout() -> None:
    print("[超时处理] 正在清理...")

@Node()  async def handle_auth_failure() -> None:
    print("[认证处理] 正在刷新凭据...")

@Node()  async def health_check() -> None:
    print("[健康检查] 所有系统正常")

handler_library = ARCHIVED_NODES(
    ALIAS(handle_timeout, "timeout"),
    ALIAS(handle_auth_failure, "auth"),
    ALIAS(health_check, "health"),
    INTERRUPT_RET(),  # 所有处理程序共用返回
)

# --- 主编排 ---
comp = (
    main_flow
    >> INTERRUPT_INTO("timeout")      # 选择要调用的处理程序
    >> GOTO("done")
    >> handler_library
    >> ALIAS(NOP, "done")
)
await WorkflowInterpreter(comp.render()).run()
```

**注意：** 当多个处理程序共享一个 `INTERRUPT_RET()` 时，确保每个处理程序逻辑上都能到达该节点。需要各自返回路径的处理程序，应在各自的处理程序块内放置 `INTERRUPT_RET()`。

---

## 模式四：嵌套中断

上下文栈支持**嵌套**保存/恢复——如同 CPU 处理嵌套中断。每次 `INTERRUPT_INTO` 压入新上下文；每次 `INTERRUPT_RET` 弹出最近的一个。

```python
# 外层处理程序通过 INTERRUPT_INTO 进入
# 内层处理程序由外层处理程序内部的另一个 INTERRUPT_INTO 触发
# 返回按 LIFO 顺序展开：先内层 RET，再外层 RET

@Node()
async def outer_handler() -> None:
    print("  [外层] 开始...")
    # INTERRUPT_INTO("inner_handler") — 嵌套中断
    print("  [外层] 从内层中断返回")

@Node()
async def inner_handler() -> None:
    print("    [内层] 深度处理")

handlers = ARCHIVED_NODES(
    ALIAS(outer_handler, "outer_handler"),
    INTERRUPT_INTO("inner_handler"),  # 嵌套中断调用
    INTERRUPT_RET(),                   # 外层返回
    ALIAS(inner_handler, "inner_handler"),
    INTERRUPT_RET(),                   # 内层返回
)

comp = (
    main_start
    >> INTERRUPT_INTO("outer_handler")
    >> after_all
    >> GOTO("done")
    >> handlers
    >> ALIAS(NOP, "done")
)
```

**执行顺序：**

1. `main_start` → `INTERRUPT_INTO("outer_handler")` 保存上下文 A，跳转到 `outer_handler`。
2. `outer_handler` 运行，遇到 `INTERRUPT_INTO("inner_handler")`——保存上下文 B，跳转到 `inner_handler`。
3. `inner_handler` 运行，遇到 `INTERRUPT_RET()`——恢复上下文 B，返回到 `outer_handler`。
4. `outer_handler` 继续，遇到 `INTERRUPT_RET()`——恢复上下文 A，返回到 `after_all`。

---

## 与外部中断的关系

| 机制                               | 来源     | 工作方式                                |
| ---------------------------------- | -------- | --------------------------------------- |
| `call_sub(interrupt=True)`         | **外部** | 外部代码在节点边界注入子程序            |
| `INTERRUPT_INTO` / `INTERRUPT_RET` | **内部** | `>>` 链中的指令执行上下文保存/跳转/恢复 |

两种机制**互补**：

- 外部 `call_sub` 可以调用通过 `INTERRUPT_INTO` 进入的处理程序。
- `INTERRUPT_INTO` 处理程序可存放在 `ARCHIVED_NODES` 中，通过 `call_sub(interrupt=True)` 外部调用。
- 使用 `INTERRUPT_INTO` 实现**工作流内部**中断模式；使用 `call_sub(interrupt=True)` 实现**调试器/外部代理**注入。

外部机制请参见[外部中断调用](/zh/guide/advanced/external_interrupt)。

---

## 注意事项

1. **IF 分支内不能使用 INTERRUPT_INTO**：当 `pc.if_flag == True` 时尝试 `INTERRUPT_INTO` 会抛出 `IllegalState`。这保护了条件流程的完整性。
2. **上下文栈完整性**：`INTERRUPT_RET` 无条件弹出。确保每个 `INTERRUPT_INTO` 都有对应的 `INTERRUPT_RET`（或手动 `POP_CONTEXT` + `rebase_context`）。
3. **返回时 if_flag 被清除**：`INTERRUPT_RET` 后，`pc.if_flag` 始终重置为 `False`，无论进入时设置的 `if_state` 为何值。
4. **INTERRUPT_RET 执行 jump_to**：与其他跳转指令一样，它设置 `_jump_marked = True`。解释器不会推进指针——执行在恢复的地址处继续。
5. **依赖注入参数被保留**：`INTERRUPT_INTO` 保存上下文时始终包含 `s_args` 和 `s_kwargs`。`INTERRUPT_RET` 之后的节点将看到与中断前相同的依赖注入参数。
