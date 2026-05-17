# 流程控制

在了解寻址空间、指针向量与节点跳转的基础概念之后，我们正式深入 AmritaSense 引擎的**流程控制**能力体系。这是 AmritaSense 作为通用工作流编排引擎的核心竞争力——它提供了一套完备的、图灵完备的控制流指令集，让你可以用接近编程语言的直觉来编排任意复杂的异步任务。

---

## 3.3.1 条件分支

AmritaSense 是原生图灵完备的运行时，因此拥有原生设计的完整条件分支语法。与基于图的工作流引擎需要“路由函数 + 字符串映射”的模拟方式不同，AmritaSense 将条件分支直接内建为一级指令。

### 基本用法

`IF` 指令支持以下标准写法：

```python
IF(condi, do)                        # 纯 IF，条件成立则执行 do
IF(condi, do).ELSE(else_do)          # IF-ELSE 双分支
IF(condi, do).ELIF(condi2, do2)      # IF-ELIF 链
IF(condi, do).ELIF(condi2, do2).ELSE(else_do)  # 完整 IF-ELIF-ELSE 链
```

它完整复刻了 Python 式的 `elif` 链式写法，语法链中 `ELIF` 的数量不受限制，可以无限扩展。每一个 `ELIF` 都会在编译期被自动展开为标准的地址跳转三元组，运行时无需任何字符串匹配或字典查找。

### 关键特性

- **条件的统一底层类型为 `Node[bool]`**：条件表达式本身也是一个节点。这意味着条件可以是简单函数、异步函数、甚至是带有依赖注入的复杂节点。这种设计保证了“一切皆是节点”的哲学贯穿始终。
- **同步与异步无缝混用**：不论条件是同步返回 `bool` 的函数，还是异步返回 `Awaitable[bool]` 的协程，引擎都会自动归一化为统一的执行接口，无需开发者做任何额外适配。
- **编译期地址静态计算**：所有分支的跳转偏移量在 `render()` 阶段就已计算完毕，运行时只是一次指针向量的算术操作，没有图遍历或字符串哈希的开销。

---

## 3.3.2 循环体

AmritaSense 原生内置节点级循环原语，支持两种标准循环范式：`WHILE` 和 `DO-WHILE`。两者都与经典编程语言的语义完全对齐，且循环条件本身也是一个可编排的节点。

### WHILE 语句

语义逻辑与 Python 的 `while ...:` 条件循环完全一致：先检查条件，条件为真则执行循环体，执行完再次检查条件，如此往复。

```python
WHILE(condition).ACTION(action_node)
```

关键点：**循环判定条件本身，也是一个独立可编排的节点**。这与其他需要将条件硬编码在路由函数中的框架截然不同——你的条件可以是任意复杂的异步逻辑，可以接受依赖注入，可以在执行前被挂起检查。

### DO-WHILE 语句

Python 中没有原生的 `do-while` 语法，但其逻辑行为与 C 语言的 `do-while` 语句完全等价。核心语义是：**保证 `DO` 包裹的执行块至少会被完整运行一次**，然后才进行条件检查。

```python
DO(do_node).WHILE(condition)
```

这在需要“先执行、后判断”的场景中非常有用——例如先发起一次网络请求，根据响应结果决定是否需要重试。

### 跳出循环

如果需要主动终止循环（等价于传统语言的 `break`），只需要在 `ACTION` 或 `DO` 的执行节点内部，主动抛出 `BreakLoop` 标记。外层的 `WHILE` 或 `DO-WHILE` 会自动捕获该信号，干净、安全地终止整个循环实例。

```python
@Node()
def early_exit():
    if some_condition:
        raise BreakLoop
    do_something()
```

### continue 的等效实现

Sense 循环没有设计原生的 `continue` 关键字，但提供了零开销的等效实现：只需要在当前节点中执行 `return` 提前结束本轮节点执行，解释器就会自然推进到下一轮循环的条件检查（或循环体开始），实现与 `continue` 完全一致的“跳过剩余逻辑、直接进入下一轮循环”的效果。

---

## 3.3.3 异常处理

AmritaSense 原生提供了**节点域的 TRY/CATCH 异常捕获体系**。这是传统工作流引擎普遍缺失的能力——在 AmritaSense 中，异常处理和条件分支、循环一样，是一等公民。

### 完整用法

```python
TRY(do).CATCH(exc, handler)                              # 捕获特定异常
TRY(do).FINALLY(cleanup)                                  # 仅定义清理块
TRY(do).CATCH(exc, handler).FINALLY(cleanup)              # 捕获 + 清理
TRY(do).THEN(success).CATCH(exc, handler).FINALLY(cleanup) # 完整四段式
TRY(do).CATCH(exc, handler).THEN(success)                 # 捕获 + 成功分支
TRY(do).CATCH(exc1, handler1).CATCH(exc2, handler2).FINALLY(cleanup)  # 多异常捕获
```

整体逻辑与 Python 的 `try-except-else-finally` 高度对齐，差异点在于：

- 使用 `CATCH` 声明要捕获的异常类型和对应的处理节点
- 使用 `THEN` 等价于 Python 的 `else` 分支——仅在 `TRY` 块无异常、正常执行完毕时才执行

### 语法约束

1. `TRY` 之后必须跟随至少一个 `CATCH` 或 `FINALLY`
2. 单个 `TRY` 结构中，`FINALLY` 和 `THEN` 最多只能各定义一个
3. `CATCH` 可以定义多个，引擎采用**从上到下、短路优先**的匹配规则——第一个匹配到异常类型的 `CATCH` 处理节点会被执行，后续的 `CATCH` 不再检查

### 特殊异常穿透规则

与通用编程语言的行为不同：AmritaSense 引入了一套**异常穿透**机制。如果在 `WorkflowInterpreter` 初始化时，通过 `exception_ignored` 参数标记了某些异常类型，那么当这些异常在 `TRY` 块中抛出时，当前层级的任何 `CATCH` 都会直接跳过该异常——**异常不会在这一层被捕获，而是向上穿透，直达顶层全局异常处理器**。

```python
pc = WorkflowPC(nd, exception_ignored=(CriticalError,))
```

这种设计让开发者可以标记“不可恢复”或“需要全局处理”的异常类型，确保它们不会被某个中间的 `CATCH` 误吞。这在构建复杂多层工作流时尤为重要——内层的通用容错逻辑不应该拦截外层的紧急信号。

---

### 小结

AmritaSense 的流程控制体系，从条件分支、循环结构到异常处理，完整覆盖了结构化编程的所有核心范式。这些能力不是通过外部 DSL 或图拓扑“模拟”出来的，而是直接编码在指令集和解释器中的一等公民。在下一章中，我们将探讨这些流程在运行时的执行机制与中断控制。
