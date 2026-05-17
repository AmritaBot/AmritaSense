# 异常系统

AmritaSense 定义了一套精简且职责明确的异常体系，用于处理工作流执行过程中的各种错误与中断。每种异常类型都有清晰的语义边界和使用约束。

---

## InterruptNotice

```python
class InterruptNotice(BaseException):
    """Special exception for immediate workflow termination.

    Raised by the INTERRUPT node or external systems. As a BaseException
    subclass, it bypasses regular CATCH blocks and penetrates directly to
    the interpreter's top-level handler, ensuring clean and unconditional
    termination.
    """
```

**为什么继承 `BaseException`**

Python 的 `except Exception` 不会捕获 `BaseException` 的子类。因此，工作流中的任何 `TRY/CATCH` 块默认无法拦截 `InterruptNotice`。这是设计上的刻意选择——`INTERRUPT` 必须是“不可捕获”的紧急终止信号。唯一的例外是显式将 `InterruptNotice` 加入 `exception_ignored`，此时它变为可被 CATCH 捕获的普通异常。

**触发方式**

- **编排层面**：工作流执行到 `INTERRUPT` 节点时自动抛出
- **外部注入**：外部系统直接 `raise InterruptNotice()`，解释器在下一次节点边界捕获并终止

**解释器响应**

当解释器主循环捕获到 `InterruptNotice` 时：
1. 记录当前指针位置和通知消息
2. 清空 `_ret_addr_stack`（调用栈）
3. 重置 `_pointer`（指针向量）
4. 重置 `_jump_marked` 标记
5. 工作流干净退出，不留下残留状态

---

## NullPointerException

```python
class NullPointerException(Exception):
    """Raised when a node cannot be located at a given address.

    This occurs when jump operations reference non-existent nodes,
    invalid address vectors, or aliases that failed to resolve.
    """
```

**触发场景**

- `GOTO`、`CALL` 等跳转指令的目标地址在 `NodeComposeRendered` 中不存在
- 别名解析时在 `alias2vector_map` 中找不到对应条目（此时 `JumpNode` 和 `CallNode` 的 `_pre_check` 会先抛出带有拼写建议的 `RuntimeError` 或 `ValueError`，而非直接抛出此异常）
- 运行时通过 `find_addr` 访问越界的索引

**与别名校验的关系**

`NullPointerException` 是运行时地址失效时的兜底异常。在实际使用中，如果通过 `ALIAS` + `GOTO`/`CALL` 正常寻址，拼写错误会在 `_pre_check` 阶段被拦截并提供纠错建议。裸地址 `list[int]` 直接使用时，若地址无效才会在运行时抛出此异常。

---

## BreakLoop

```python
class BreakLoop(Exception):
    """Exception used to break out of WHILE or DO-WHILE loop constructs.

    When raised within a loop body, the loop terminates immediately and
    execution continues after the loop's NOP exit point.
    """
```

**自动穿透机制**

`BreakLoop` 在 `WorkflowInterpreter` 初始化时被自动加入 `_exc_ignored` 元组。这意味着：
- 循环体内部的任何 `TRY/CATCH` 块**不能**捕获 `BreakLoop`
- 它会穿透中间所有异常处理层，直达最内层的 `WhileNode` 或 `DONode`
- 循环节点捕获到 `BreakLoop` 后执行 `jump_near(NOP)`，干净退出

**使用方式**

在循环体的 `ACTION` 或 `DO` 节点内部直接抛出即可：

```python
@Node()
def process_item():
    if item is None:
        raise BreakLoop   # 无更多数据，跳出循环
    if item.should_skip:
        return            # 等效 continue
    handle(item)
```

**注意**：开发者**不应**手动将 `BreakLoop` 加入 `exception_ignored`——它在解释器初始化时已自动加入。如果额外添加，不会产生新效果；如果试图移除，会导致循环内的 CATCH 块意外捕获 `BreakLoop`，破坏循环语义。

---

## DependsException 及其子类

依赖注入过程中的异常统一继承自 `DependsException`。

```python
class DependsException(Exception):
    """Base class for all dependency injection related exceptions."""
```

### DependsResolveFailed

```python
class DependsResolveFailed(Exception):
    """Raised when a node's dependencies cannot be resolved.

    This occurs when required parameters in the function signature
    cannot be matched to any available dependency source.
    """
```

**触发条件**

- 节点的函数签名中存在无法匹配的参数（没有对应类型的依赖源，也没有默认值）
- 多个依赖源匹配到同一参数，且无法消歧

### DependsInjectFailed

```python
class DependsInjectFailed(Exception):
    """Raised when runtime dependency injection fails during node execution.

    This typically occurs when a Depends factory function raises an
    exception that is not in the exception_ignored tuple.
    """
```

**触发条件**

- `Depends` 工厂函数在运行时抛出异常，且该异常不在 `_exc_ignored` 中
- 并发解析多个依赖时，所有失败异常被收集进 `ExceptionGroup` 并重新抛出

**关键行为：`Depends` 返回 `None` 直接终止**

与事件系统的“返回 `None` 则跳过处理器”不同，在节点执行中，如果某个 `Depends` 声明的依赖工厂返回了 `None`，工作流会**直接抛出异常并终止**。节点是原子执行单元，依赖解析失败意味着节点无法运行——这不是可以“跳过”的场景。因此，为节点设计的依赖工厂函数应始终返回有效值（或在无法提供时抛出明确的异常，而非返回 `None`）。

---

## 异常层次结构

```text
BaseException
└── InterruptNotice          # 继承 BaseException，默认不可被 CATCH 捕获

Exception
├── NullPointerException      # 地址无效
├── BreakLoop                 # 循环跳出信号
└── DependsException          # 依赖注入基类
    ├── DependsResolveFailed   # 依赖无法解析
    └── DependsInjectFailed    # 依赖注入过程异常
```

**设计原则**：
- `InterruptNotice` 继承 `BaseException`，实现天然的不可捕获性
- `BreakLoop` 继承 `Exception`，但通过自动加入 `_exc_ignored` 获得等效的穿透能力
- 依赖相关异常继承同一个基类 `DependsException`，允许用户按需捕获整个依赖类别的错误