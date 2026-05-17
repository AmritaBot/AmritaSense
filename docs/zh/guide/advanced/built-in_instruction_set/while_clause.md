# 4.5.2 WHILE 与 DO-WHILE 循环

AmritaSense 提供了两种标准循环范式：`WHILE`（先判断后执行）和 `DO-WHILE`（先执行后判断）。两者都是 `SelfCompileInstruction`，在编译期展开为包含跳转节点的固定结构，运行时完全通过指针偏移和 `jump_near` 完成循环逻辑，无需任何外部状态标志。

---

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

---

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

### continue 的等效实现

在 `action` 或 `do_node` 内部执行 `return`，即提前结束当前节点的执行。解释器自然步进到 `CheckUpNode`（WHILE）或 `DowhileNode`（DO-WHILE），然后下一轮条件检查开始。效果与 `continue` 完全一致。

---

## 循环内的 GOTO 限制

`WHILE` 和 `DO-WHILE` 的编译期结构是固定的地址偏移布局。`WhileNode` 和 `DONode` 内部依赖 `call_offset` 和 `jump_near` 的相对偏移来完成条件调用和循环体调用。

如果在循环体内部使用 `GOTO` 跳转到循环结构之外的地址：

- 循环的调用栈和返回地址不会正确清理
- `WhileNode` 或 `DONode` 内部的 `try-except BreakLoop` 无法正常捕获 `BreakLoop`
- 解释器可能进入不可预测的状态

因此，**循环内部不应使用 `GOTO` 跳出循环**。需要跳出时应使用 `BreakLoop`，需要子程序复用时应使用 `CALL`。

---

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

---

## 何时用 WHILE，何时用 DO-WHILE

| 场景                                         | 推荐       |
| -------------------------------------------- | ---------- |
| 可能一次都不需要执行循环体                   | `WHILE`    |
| 循环体至少需要执行一次（如首次请求、初始化） | `DO-WHILE` |
| 条件检查需要发生在循环体之前                 | `WHILE`    |
| 循环体执行后才具备判断条件                   | `DO-WHILE` |

---

> **条件即节点**
> 与图模型框架将条件硬编码为路由函数不同，AmritaSense 的循环条件本身就是一个 `Node[bool]`。这意味着条件可以是异步函数，可以接受依赖注入，可以在执行前被挂起检查。这是“一切皆是节点”哲学在循环结构中的直接体现。
