# REPL 调试

AmritaSense v0.5.0 引入了一个专用的调试器模块 `amrita_sense.debugger`，提供纯函数式的 REPL 优先调试工具包。它利用解释器内置的 Panic/Recover 机制、中间件注入和步进执行，让你在 Python REPL 中像调试本地程序一样调试工作流——无需额外工具、无需 IDE 插件。

> **前置阅读**
> 建议先了解 [执行与中断](/zh/guide/concepts/exec_and_interrupt) 中的步进执行和挂起机制，以及 [外部中断调用](/zh/guide/advanced/external_interrupt) 中的 `call_sub(interrupt=True)` 原理。本文依赖这些基础设施构建完整的调试体验。

## 设计哲学

调试器遵循三个核心原则：

1. **REPL 优先** — 所有函数都是同步的（`step(inter)`，不用 `await`），可直接在 `python`、`ipython` 或 VS Code 原生 REPL 中输入
2. **纯函数式** — 无包装类、无状态封装。每个函数接收 `WorkflowInterpreter` 作为第一参数：`from amrita_sense.debugger import *`
3. **非侵入** — 断点通过组合式中间件注入，不修改核心运行时。调试代码不与业务逻辑耦合

```python
>>> from amrita_sense.debugger import *
>>> inspect(inter)       # 查看状态
>>> step(inter)          # 执行一个节点
>>> break_at_tag(inter, "my_node")
>>> cont(inter)          # 继续到断点
```

## 状态检查

调试的第一步永远是"看清楚现在在哪"。调试器提供了一套完整的状态检查工具。

### `where(inter)` — 当前位置

一行摘要，快速确认当前停在哪：

```
📍 [0, 2]  crash_here  stack_depth=0
```

显示：当前地址、节点标签、返回地址栈深度。

### `inspect(inter)` — 完整状态

美化打印解释器的全部内部状态：

- 🆔 解释器 ID、父关系和根节点
- 📍 当前指针位置和节点信息（tag、函数名）
- 🏃 运行状态和终止标记
- 📚 返回地址栈（深度 + 全部内容）
- 📦 上下文栈（深度 + 每个上下文的指针和异常）
- ⚠️ Panic 异常（如果有崩溃）
- 👶 子解释器树（每个子解释器的状态和指针）

```python
>>> inspect(inter)
══════════════════════════════════════════════════════════
🆔  Interpreter: a1b2c3d4e5f6…
📍 Pointer:      [0, 2]
🔍 Node:         crash_here
   Function:     crash_node
🏃 Running:      no
🚩 Pending stop: no
📚 Return stack: depth=0
📦 Context stack: depth=0
⚠️  Panic:        RuntimeError: planned crash for demo
👶 Sub-interpreters: 0
══════════════════════════════════════════════════════════
```

### `backtrace(inter)` — 调用链

展开完整调用链：解释器树（Root → … → Current）、返回地址栈、上下文栈、当前节点。

```python
>>> backtrace(inter)
Interpreter → a1b2c3d4e5f6… [Root] [Current] at 0x7f8a1c00d000

Returning Stack:
    0. [0, 2] (Current)

Context Stack:
    (EMPTY_STACK)

Current node: crash_here -> crash_node
```

### `list_nodes(inter)` — 节点清单

遍历编译图的 `_graph` 树，打印所有节点的地址、tag 和函数名。类似标准库的 `dis.dis()`，用于了解工作流的整体结构：

```
   [0, 0]  start             start_node
   [0, 1]  middle            middle_node
   [0, 2]  crash_here        crash_node
   [0, 3]  never_reached     never_reached
```

若想要带助记符与当前程序计数器的分段视图，请改用 [`dis()`](#反汇编视图)。

### `list_sub_intp(inter)` — 子解释器树

递归展开整个解释器树，显示每个子解释器的运行状态、当前指针和异常：

```
🟢 a1b2c3...  ptr=[0, 1]
  ⏸️ d4e5f6...  ptr=[0, 1]  exc=RuntimeError
  🟢 g7h8i9...  ptr=[1, 2]
```

## 反汇编视图

渲染后的工作流图**本身就是**一份带地址的指令序列——`[1, 0]` 是地址，指针向量就是程序计数器。`dis()` 像 GDB 展示机器码那样展示它，用「段」代替缩进树：

```
segment [root]:
=>[0] (top) ALIAS top; alias for Alpha
  [1]       CALL top -> [0]; CallNode
  [2]       *segment [2]
  [3]       JMP [0]; GOTO 'top'
  [4]       NOP; no operation

segment [2]:
  [2, 0] JMPIF; ConditionJumpNode
  [2, 1] Cond; Cond
  [2, 2] Beta; Beta
  [2, 3] NOP; no operation
```

- `=>` 标记程序计数器，与 GDB 一致。
- 嵌套容器在父段中显示为 `*segment [n]` 引用行，并另起一块输出——因此再深的图也是平的，不会长成缩进树。
- `;` 分隔助记符与注释。地址旁的 `(name)` 是通过 `ALIAS` 注册的符号。
- 非默认渲染图的容器会显示其类名，例如 `segment [1] <DLLComposeProxy>:`——提示该槽位下方的全部内容会随 `dll.apply()` 变基而移动。

### `dis(inter, *, around=5)` — 打印清单

`dis()` 打印程序计数器周围的一段指令窗口。传入 `around=None` 输出整张图；也可以用 `disassemble()` 拿到同样内容的字符串：

```python
>>> dis(inter)                 # PC 前后各 5 行
>>> dis(inter, around=None)    # 整份工作流
>>> text = disassemble(inter)  # 同样内容，返回 str
```

`step()` / `step_over()` / `step_out()` / `cont()` 会自动打印清单，因此每次停下都能看到自己在哪里：

```
>>> step(inter)
segment [1]:
  [1, 0] Beta; Beta
=>[1, 1] Gamma; Gamma
```

`step_over()` 与 `step_out()` 只在整段移动结束后打印一次。把 `amrita_sense.debugger.code_disp.AUTO_DIS` 设为 `False` 可以关闭自动打印，`dis()` 仍可手动调用。

### 着色

当 stdout 是终端时，清单通过 [colorama](https://pypi.org/project/colorama/) 着色：`=>` 标记为亮绿色，地址青色，别名为绿色，助记符加粗，操作数黄色，注释灰暗，段头亮紫色。把输出重定向到文件或分页器时会自然得到纯文本。

```python
>>> from amrita_sense.debugger import code_disp
>>> code_disp.COLOR = True    # 强制开启（即使被重定向）
>>> code_disp.COLOR = False   # 强制关闭
>>> code_disp.COLOR = None    # 自动检测（默认）
```

颜色是在**列宽填充之后**才施加的，因此开启着色不会移动指令列。调色板的每一项都是模块常量（`code_disp.C_PC`、`C_ADDR`、`C_MNEMONIC`、`C_OPERAND` 等），换主题只需重新赋值。

### 魔术属性：`__sdb_dis__` 与 `__sdb_cmt__`

助记符来自节点上的**软约束魔术属性**，指令可以自己描述自己：

| 属性          | 作用                                                          |
| ------------- | ------------------------------------------------------------- |
| `__sdb_dis__` | 指令列的文本。                                                |
| `__sdb_cmt__` | 非 `None` 时覆盖 `;` 后的注释内容（默认为 `tag`）。            |

两者都通过普通 `getattr` 在**反汇编时**读取——输入是*已编译*的产物，因此像跳转目标这样的操作数此时早已解析完毕。三种声明形式都支持：

| 形式           | 适用场景                                                                     |
| -------------- | ---------------------------------------------------------------------------- |
| **类属性**     | 所有实例共用的固定助记符。                                                   |
| **`@property`** | 由实例状态推导的值——每次列清单都重新读取，重编译后无需任何重新赋值。         |
| **实例属性**   | 工厂创建的指令，其操作数只存在于闭包中（`PUSH_STACK`、`INTERRUPT_INTO` 等）。 |

两个名字都有双尾下划线，不会触发名字改写，因此在类体内写 `self.__sdb_dis__ = ...` 是安全的。不过 property 是**数据描述符**，声明了 property 的节点会主动拒绝 `self.__sdb_dis__ = ...`——这正是让取值保持单一来源的机制。

```python
from amrita_sense.node.core import BaseNode, NodeComposeRendered


class MyJump(BaseNode):
    """自定义指令：展示已解析的跳转目标。"""

    __sdb_cmt__ = "custom jump"

    def __init__(self, alias: str) -> None:
        self._alias = alias
        self._target: list[int] = []
        self._init(self.__call__, tag=None, wrap_to_async=False, address_able=True)

    @property
    def __sdb_dis__(self) -> str:
        #  property 每次重新读取状态，因此重编译后依然正确
        return f"MYJMP {self._target or '?'}"

    def _post_compile(self, compose: NodeComposeRendered) -> None:
        self._target = compose.calc.resolve_alias(self._alias)
```

节点什么都没声明时，视图回退到它的 `tag`（会剥掉 `__NAME__` 装饰，因此 `__RET_FAR__` 显示为 `RET_FAR`）；若 tag 是自动生成的 `NodeSuspend::…`，则回退到被包装的函数名。

### 操作数记法

节点永远不知道自己的地址，因此相对于所在段的目标无法写成完整地址。操作数的写法与它所用的指针操作一一对应：

| 记法        | 含义                         | 指针操作  |
| ----------- | ---------------------------- | --------- |
| `[1, 0]`    | 绝对地址                     | `far_to`  |
| `#3`        | **节点所在段内**的第 3 个槽位 | `near_to` |
| `+2` / `-1` | **节点所在段内**的相对偏移    | `offset`  |

内置指令集统一使用这套记法，因此框架控制流的清单读起来像汇编：

```
segment [2]:
  [2, 0] JMPIF then=#3 else=+3; ConditionJumpNode
  [2, 1] Cond; Cond
  [2, 2] Beta; Beta
  [2, 3] NOP; no operation

segment [3]:
  [3, 0] WHILE checkup=#3 else=#4; WhileNode
  [3, 3] WHILE.CHECK back=#0; CheckUpNode

segment [4]:
  [4, 0] TRY catch=ValueError#2; finally=#3 escape=#4
```

其它会看到的内置助记符：`JMP [0]`（`GOTO`）、`CALL sym -> [0]`（`CALL`）、`CALL.FAR from -> to`（`PUSH_AND_GOTO`）、`PUSH [0]`（`PUSH_STACK`）、`PUSHCTX` / `INTINTO` / `INT.KEEP`（中断类）、`DO loop=#3 break=#5`、`DO.CHECK back=#0 exit=#3`，以及 native 快速路径的 `NJMPIF` / `NWHILE` / `NDO.CHECK` / `NENTER`。

### 寻址模式与契约安全

清单是沿 `AbstractCompose` **契约**遍历生成的，而不是按具体类判断——因为渲染图可能是 `DLLComposeProxy`，也可能是自定义实现（见 [Compose 契约](../advanced/compose-contracts)）。两个值得知道的推论：

- 拒绝被读取的容器（未构建的 DLL 占位容器会抛 `NullPointerException`）会显示为 `(unreadable)` 段，而不会让整份清单崩掉。
- 符号表（`alias2vector_map`）**不在**契约内，因此别名是软特性：没有符号表的图会退化为纯地址显示。

由于 DLL 变基会让绝对地址不可靠（见 [动态链接](../advanced/dll_feature)），读清单时请优先看别名——别名列会告诉你哪些地址是符号。

## 步进控制

步进控制允许你精确控制每次执行一个节点。提供了两种 API 风格：

| 风格     | 函数                                                                 | 适用场景                    |
| -------- | -------------------------------------------------------------------- | --------------------------- |
| **同步** | `step()` `step_over()` `step_out()` `cont()`                         | Python REPL（无需 `await`） |
| **异步** | `step_async()` `step_over_async()` `step_out_async()` `cont_async()` | 已有事件循环的程序中        |

### `step(inter)` — 单步执行

执行**恰好一个**节点然后停住。是最核心的原语：

```python
>>> step(inter)
  [start] running…
>>> where(inter)
📍 [0, 1]  middle  stack_depth=0
```

内部原理：`step()` 在步进期间将 `stepping` 标志置为 `True`，断点检查被跳过——所以单步调试时不会触发断点。

每次步进还会打印新程序计数器处的[反汇编视图](#反汇编视图)，因此你能确切看到下一条要执行的指令。

### `step_over(inter)` — 单步越过

执行节点，但**不进入**子程序调用（`call_sub` / `CALL`）。内部监控 `_ret_addr_stack` 的深度——只要深度大于起始值就继续执行，直到回到同一栈帧。

```python
>>> step_over(inter)  # 如果当前节点调用了 call_sub，
                       # 子程序也会执行完，但不会在子程序里停住
```

### `step_out(inter)` — 跳出当前帧

执行直到返回地址栈变浅——即跳出当前子程序调用帧：

```python
>>> step_out(inter)   # 从 call_sub 深处一层层执行，直到返回调用方
```

### `cont(inter)` — 继续执行

继续执行直到遇到断点或工作流结束。清除 `stepping` 标志，断点检查恢复生效：

```python
>>> cont(inter)
⏸️  Hit breakpoint: tag='my_node' hits=1
```

断点会在其节点**执行之前**停下，因此下一次 `cont()` 会执行该节点并继续前进：

```python
>>> cont(inter)   # 执行到 'my_node' 之前停下
>>> cont(inter)   # 'my_node' 执行，然后继续到下一个断点
```

只有实际停下的那个地址会被跳过，因此更后面的第二个断点依然会触发。工作流跑完后，下一次 `cont()` 会从第一条指令重新开始。

`cont()` 同样会在停下处打印[反汇编视图](#反汇编视图)——无论是命中断点还是工作流结束。

### 异常处理

所有步进函数都优雅处理三类可预见场景：

| 场景                   | 行为                                                     |
| ---------------------- | -------------------------------------------------------- |
| 命中 `BreakpointHit`   | 打印 `⏸️  Hit breakpoint: ...`                           |
| 键盘按下 `Ctrl+C`      | 打印 `⏸️  Stop at: [addr]`                               |
| 节点内抛出异常（崩溃） | 打印 `⚠️  Node crashed: ... Panic saved, use inspect().` |

崩溃后执行不会丢失——`_panic_exc`、`_pointer`、`_ret_addr_stack` 全部保留，可以用 `inspect()` 查看完整现场。

## 断点系统

断点通过**组合式中间件**注入到解释器。核心设计：

```text
debug_middleware(pc):
    1. 检查断点 → 命中则抛出 BreakpointHit
    2. 调用用户原始中间件（如果存在）
    3. 否则直接调用 pc._call()
```

「命中」意味着当前地址上的节点**即将**执行——此时还没有任何代码跑过。调试器会记住该地址，使下一次 `cont()` 跳过检查一次、让该节点执行；否则同一个断点会在节点有机会执行之前再次触发，`cont()` 将永远无法前进。显式调用 `step()` 会丢弃待续的恢复点，因为步进本就不做断点检查。

::: details 中间件注入细节
设置第一个断点时，调试器会：

1. 保存 `inter._middleware` 当前值（用户的原始中间件，如有）
2. 构造组合中间件：`断点检查 → 用户中间件 → _call()`
3. 将 `inter._middleware` 替换为组合中间件

用户原有中间件始终被尊重，断点检查作为前置步骤插入。清除所有断点不会移除组合中间件——如需恢复原始状态，重新创建解释器即可。
:::

### `break_at_tag(inter, tag, *, condition=None)` — 按标签设置断点

在**所有** `tag` 匹配的节点上设置断点。`tag` 是 `@Node(tag="...")` 中指定的标签：

```python
>>> break_at_tag(inter, "crash_here")
🔴 Breakpoint: tag='crash_here' hits=0
```

### `break_at_addr(inter, addr, *, condition=None)` — 按地址设置断点

在精确地址上设置断点。`addr` 可以是：

- **别名**（`str`）：通过 `AddressCalculator.resolve_alias()` 解析
- **原始地址**（`list[int]`）：如 `[0, 2]`

```python
>>> break_at_addr(inter, [0, 1])
🔴 Breakpoint: addr=[0, 1] hits=0

>>> break_at_addr(inter, "my_alias")
🔴 Breakpoint: addr=[2, 0] hits=0
```

### 条件断点

`condition` 参数接收一个 `(WorkflowInterpreter) -> bool` 的可调用对象：

```python
>>> break_at_tag(inter, "middle", condition=lambda pc: len(pc._ret_addr_stack) > 0)
🔴 Breakpoint: tag='middle' hits=0 cond
```

只有当条件返回 `True` 时断点才会触发。条件求值异常时静默跳过（不触发断点）。

### 管理断点

```python
>>> list_breaks(inter)                  # 列出所有断点
  1. TAG  'crash_here'  hits=1
  2. ADDR  [0, 1]  hits=0

>>> clear_break_tag(inter, "crash_here")  # 按标签清除
✖  Removed: tag='crash_here' hits=1

>>> clear_break_addr(inter, [0, 1])       # 按地址清除
✖  Removed: addr=[0, 1] hits=0
```

### `BreakpointHit` — 断点异常

`BreakpointHit` 继承自 `BaseException`（不是 `Exception`），因此**永远不会**被 Panic/Recover 机制捕获，不会将解释器置为 panic 状态。

```python
>>> bp = Breakpoint(target="test", kind="tag")
>>> isinstance(BreakpointHit(bp), BaseException)  # True
>>> isinstance(BreakpointHit(bp), Exception)      # False
```

## 崩溃恢复

AmritaSense 的 Panic/Recover 机制是调试器的核心能力之一。当节点抛出未处理异常时，解释器不会丢失状态。

### 典型流程

```python
# 1. 执行到会崩溃的节点
>>> step(inter)
  [crash_here] about to explode 💥
⚠️  Node crashed: RuntimeError('planned crash for demo'). Panic saved, use inspect().

# 2. 查看崩溃现场
>>> inspect(inter)  # 显示完整状态：_panic_exc = RuntimeError,
                     # _pointer 停在 crash_here, 栈完整保留

# 3. 手动跳过崩溃节点
>>> inter.advance_pointer()

# 4. 设置断点在恢复后的节点
>>> break_at_tag(inter, "never_reached")

# 5. 继续执行（内部从 panic 恢复）
>>> cont(inter)
  [never_reached] recovered successfully! 🎉
```

**恢复原理**：`step()` / `cont()` 的内部 `_step_one()` 在每次执行前检查 `_panic_exc`，如果非 `None` 则清除（recover），然后正常执行当前指针指向的节点。由于你已手动 `advance_pointer()` 跳过了崩溃节点，恢复后执行的是下一个节点。

## 完整示例

项目中的 `demos/21_debug_repl.py` 提供了一个端到端的 REPL 调试演示，覆盖了上述所有功能：

```bash
python demos/21_debug_repl.py
```

演示流程：

```mermaid
flowchart TD
    A[inspect 初始状态] --> B[list_nodes 查看结构]
    B --> C[step 执行 start_node]
    C --> D[step_over 越过 middle_node]
    D --> E[step 进入 crash_node 💥]
    E --> F[inspect 查看崩溃现场]
    F --> G[advance_pointer 跳过崩溃]
    G --> H[break_at_tag + cont 断点恢复]
    H --> I[设置多个断点 + list_breaks]
    I --> J[cont 命中 + clear_break]
    J --> K[backtrace 查看调用链]
    K --> L[list_sub_intp 子解释器树]
```

你也可以在 REPL 中手动操作：

```python
>>> from amrita_sense.debugger import *
>>> from demos.21_debug_repl import inter
>>> inspect(inter)
>>> step(inter)     # 不需 await！
```

## 安全注意事项

### 解释器 ID 泄露

`inspect()` 和 `list_sub_intp()` 默认截断显示解释器 UUID（`inter.id[:12]…`），避免完整 UUID 泄露到日志或终端。
