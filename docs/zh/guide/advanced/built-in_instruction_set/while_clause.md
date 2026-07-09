# 4.5.2 WHILE 与 DO-WHILE 循环

AmritaSense 提供了两种标准循环范式：`WHILE`（先判断后执行）和 `DO-WHILE`（先执行后判断）。两者都是 `SelfCompileInstruction`，在编译期展开为包含跳转节点的固定结构，运行时完全通过指针偏移和 `jump_near` 完成循环逻辑，无需任何外部状态标志。

## 编译期展开结构

### WHILE 循环

`WHILE(condition).ACTION(action)` 在编译期展开为：

```text
[WhileNode, condition, action, CheckUpNode, NOP]
```

| 位置   | 节点          | 职责                                   |
| ------ | ------------- | -------------------------------------- |
| 索引 0 | `WhileNode`   | 调用条件，决定进入循环体或跳出         |
| 索引 1 | `condition`   | 条件节点，返回 `bool`                  |
| 索引 2 | `action`      | 循环体节点                             |
| 索引 3 | `CheckUpNode` | 无条件跳回 `WhileNode`，开始下一轮检查 |
| 索引 4 | `NOP`         | 循环出口，跳出后从此处继续推进         |

### DO-WHILE 循环

`DO(do_node).WHILE(condition)` 在编译期展开为：

```text
[DONode, do_node, DowhileNode, condition, NOP]
```

| 位置   | 节点          | 职责                             |
| ------ | ------------- | -------------------------------- |
| 索引 0 | `DONode`      | 先执行循环体，然后跳转到条件检查 |
| 索引 1 | `do_node`     | 循环体节点（保证至少执行一次）   |
| 索引 2 | `DowhileNode` | 调用条件，决定跳回循环体或退出   |
| 索引 3 | `condition`   | 条件节点，返回 `bool`            |
| 索引 4 | `NOP`         | 循环出口                         |

> **关键区别**
> WHILE 的条件检查在循环体之前，DO-WHILE 的循环体在条件检查之前。两者最终都通过 `NOP` 作为统一的循环出口。

## 运行时执行流程

### WHILE

1. `WhileNode` 执行：通过 `call_offset` 调用 `condition` 节点
2. 若条件为 `False`：`WhileNode` 直接 `jump_near` 到 `NOP`，循环结束
3. 若条件为 `True`：`WhileNode` 通过 `call_offset` 调用 `action` 节点
4. `action` 执行完毕后，解释器步进到 `CheckUpNode`
5. `CheckUpNode` 无条件 `jump_near` 回 `WhileNode`，开始新一轮检查

### DO-WHILE

1. `DONode` 执行：通过 `call_offset` 调用 `do_node`（循环体首次执行，不检查条件）
2. `do_node` 执行完毕后，解释器步进到 `DowhileNode`
3. `DowhileNode` 通过 `call_offset` 调用 `condition` 节点
4. 若条件为 `True`：`DowhileNode` 执行 `jump_near` 回到 `DONode`，重新执行循环体
5. 若条件为 `False`：`DowhileNode` 执行 `jump_near` 到 `NOP`，循环结束

### 跳出循环：`BreakLoop`

在 `action` 或 `do_node` 内部，可以通过 `raise BreakLoop` 实现 `break` 语义。

`BreakLoop` 已在解释器初始化时被自动加入 `_exc_ignored` 元组，因此：

- 它不会被任何内层 `TRY/CATCH` 捕获
- 它会直接穿透到最外层的 `WhileNode` 或 `DONode`
- `WhileNode` 和 `DONode` 内部用 `try-except BreakLoop` 捕获该信号，然后执行 `jump_near(NOP)` 干净退出

> **v0.3.0+**：此自动加入行为可通过 `amrita_sense._unsafe` 中的 `__flags__.DISABLE_EXC_IGNORED = True` 禁用。详见 [Unsafe 特性](../unsafe.md)。

### continue 的等效实现

在 `action` 或 `do_node` 内部执行 `return`，即提前结束当前节点的执行。解释器自然步进到 `CheckUpNode`（WHILE）或 `DowhileNode`（DO-WHILE），然后下一轮条件检查开始。效果与 `continue` 完全一致。

## 循环内的 GOTO 限制

`WHILE` 和 `DO-WHILE` 的编译期结构是固定的地址偏移布局。`WhileNode` 和 `DONode` 内部依赖 `call_offset` 和 `jump_near` 的相对偏移来完成条件调用和循环体调用。

如果在循环体内部使用 `GOTO` 跳转到循环结构之外的地址：

- 循环的调用栈和返回地址不会正确清理
- `WhileNode` 或 `DONode` 内部的 `try-except BreakLoop` 无法正常捕获 `BreakLoop`
- 解释器可能进入不可预测的状态

因此，**循环内部不应使用 `GOTO` 跳出循环**。需要跳出时应使用 `BreakLoop`，需要子程序复用时应使用 `CALL`。

## 使用示例

```python
from amrita_sense.instructions import WHILE, DO
from amrita_sense.exceptions import BreakLoop
from amrita_sense.node import Node

@Node()
def has_more() -> bool:
    return len(queue) > 0

@Node()
def process_one():
    item = queue.pop(0)
    if item == "stop":
        raise BreakLoop      # 跳出循环
    if item == "skip":
        return               # 等效 continue
    handle(item)

# WHILE：先判断，再执行
loop = WHILE(has_more).ACTION(process_one)

# DO-WHILE：至少执行一次
@Node()
def fetch():
    data = request()
    if data is None:
        raise BreakLoop
    store(data)

retry = DO(fetch).WHILE(has_more)
```

## Squashed Loop 模式（v0.4.3+）

默认情况下，`WHILE` 和 `DO-WHILE` 循环使用**步进式**执行模型：解释器逐节点推进 `WhileNode`/`DONode` → condition → action → `CheckUpNode`/`DowhileNode`，每一步都经过完整的 `run_step_by()` 循环（指针推进、锁获取/释放、跳转操作）。

设置 `__flags__.SQUASHED_LOOP = True` 切换到**压扁式**执行：整个循环在单个解释器步骤内作为一个原生 Python `while` 循环运行。

### 工作原理

在压扁模式下，`WhileNode._while_worker()` 和 `DONode._do_worker()` 被替换为等价逻辑：

**WHILE 压扁后：**

```python
while await pc.call_offset(self._condi_offset):
    await pc.call_offset(self._do_offset)
    if pc._jump_marked:
        break
pc.jump_near(self._else_addr)
```

**DO-WHILE 压扁后：**

```python
try:
    while True:
        await pc.call_offset(self._do_offset)
        if ptr.jump_marked:
            return
        if not await ptr.call_sub(condi_addr):
            return ptr.jump_near(self._break_addr)
except BreakLoop:
    return ptr.jump_near(self._break_addr)
```

### 对比

| 方面            | 正常（步进式）                          | 压扁式                                |
| --------------- | --------------------------------------- | ------------------------------------- |
| **指针操作**    | 每次迭代多次（进入、退出、跳转）        | 每次迭代一次（body 的 `call_offset`） |
| **锁获取**      | 每个子步骤一次（condition、body、jump） | 整个循环一次                          |
| **外部中断**    | 可在任意子步骤之间                      | 仅在 body 边界（`call_offset`）       |
| **`BreakLoop`** | 由 WhileNode/DONode 捕获                | 由原生 except 捕获                    |
| **性能**        | 基准线                                  | 每次迭代开销更低                      |

### 何时使用

| 场景                             | 推荐模式   |
| -------------------------------- | ---------- |
| 需要在循环步内进行精确的外部中断 | **正常**   |
| 具有大量迭代的热内层循环         | **压扁式** |
| 与循环外部的 `GOTO` 跳转兼容     | **正常**   |
| 紧循环的最大吞吐量               | **压扁式** |

> **注意**：在压扁模式下，`jump_marked` 会在每次 body 执行后检查。这意味着通过 `GOTO` 或 `CALL` 设置跳转标记的跳转仍然被支持——循环会中断，跳转目标在下一步执行。但是，`InterruptNotice` 和通过 `object_io` 的外部中断只能在 `call_offset` 边界注入，不能在循环子步骤之间。

## 何时用 WHILE，何时用 DO-WHILE

| 场景                                         | 推荐       |
| -------------------------------------------- | ---------- |
| 可能一次都不需要执行循环体                   | `WHILE`    |
| 循环体至少需要执行一次（如首次请求、初始化） | `DO-WHILE` |
| 条件检查需要发生在循环体之前                 | `WHILE`    |
| 循环体执行后才具备判断条件                   | `DO-WHILE` |

> **条件即节点**
> 与图模型框架将条件硬编码为路由函数不同，AmritaSense 的循环条件本身就是一个 `Node[bool]`。这意味着条件可以是异步函数，可以接受依赖注入，可以在执行前被挂起检查。这是“一切皆是节点”哲学在循环结构中的直接体现。
