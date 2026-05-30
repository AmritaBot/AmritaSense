# 4.5.5 Try / CATCH / THEN / FIN 异常处理

AmritaSense 提供了完整的异常处理指令体系，与 Python 的 `try-except-else-finally` 高度对齐。但在使用之前，需要先回答一个问题：**什么时候应该用指令编排异常处理，什么时候应该在节点内部写 try-catch？**

## 两种异常处理模式的选择

### 节点内部 try-catch（Inline 模式）

当异常处理的逻辑**与当前节点强耦合**，或者处理逻辑极其简单时，直接在节点函数内部写 Python 原生的 try-catch：

```python
@Node()
async def fetch_data():
    try:
        response = await http_get("/api/data")
        return response.json()
    except TimeoutError:
        return get_cached_data()   # 降级逻辑，与 fetch 逻辑紧密相关
```

**适用场景**：

- 异常处理逻辑与正常逻辑紧密耦合，拆成独立节点反而降低可读性
- 处理逻辑极其简单（如返回默认值、记录日志后继续）
- 异常类型是 Python 标准异常，不需要依赖注入或中断控制

### 指令编排模式（TRY/CATCH/THEN/FIN 指令）

当异常处理是一个**独立的、可复用的流程步骤**，或者需要利用 AmritaSense 的能力（如依赖注入、挂起中断、异常穿透）时，使用指令编排：

```python
TRY(call_api).CATCH(TimeoutError, use_cache).CATCH(AuthError, refresh_token).FINALLY(cleanup)
```

**适用场景**：

- 异常处理本身是一个独立的节点，需要在不同工作流中复用
- 处理逻辑需要依赖注入（如数据库连接、日志服务）
- 需要在异常处理节点执行前挂起（中断检查）
- 需要利用 `exception_ignored` 控制异常的穿透行为
- 多个 CATCH 分支，每个分支的处理逻辑复杂，值得独立封装

### 决策原则

| 场景                                | 推荐模式                                 |
| ----------------------------------- | ---------------------------------------- |
| 处理逻辑 1-2 行，与正常逻辑紧密相关 | 节点内部 try-catch                       |
| 处理逻辑是独立步骤，可能被复用      | 指令编排 TRY/CATCH                       |
| 需要依赖注入到异常处理节点          | 指令编排                                 |
| 需要挂起/中断控制                   | 指令编排                                 |
| 异常类型需要穿透（不可捕获）        | 指令编排 + `exception_ignored`           |
| 简单的资源清理（关闭连接、释放锁）  | 节点内部 try-finally 或 TRY/FINALLY 均可 |

> **核心原则**
> 当异常处理是“节点内部的事”，用 Python。当异常处理是“工作流级别的事”，用指令。两者可以混用——TRY 块内部的节点本身也可以有自己的 try-catch。

## 指令语法与语义

### 完整语法

```python
TRY(do).CATCH(exc, handler)                              # 捕获特定异常
TRY(do).FINALLY(cleanup)                                  # 仅清理块
TRY(do).CATCH(exc, handler).FINALLY(cleanup)              # 捕获 + 清理
TRY(do).THEN(success).CATCH(exc, handler).FINALLY(cleanup) # 完整四段式
TRY(do).CATCH(exc, handler).THEN(success)                 # 捕获 + 成功分支
TRY(do).CATCH(exc1, handler1).CATCH(exc2, handler2).FINALLY(cleanup)  # 多异常
```

### 语义映射

| 指令                  | Python 对应           | 执行条件               |
| --------------------- | --------------------- | ---------------------- |
| `TRY(do)`             | `try: do`             | 总是首先执行           |
| `CATCH(exc, handler)` | `except exc: handler` | 匹配到对应异常时执行   |
| `THEN(node)`          | `else: node`          | TRY 块无异常完成时执行 |
| `FINALLY(node)`       | `finally: node`       | 无论是否有异常都执行   |

### 语法约束

1. `TRY` 之后必须跟随至少一个 `CATCH` 或 `FINALLY`
2. 单个 `TRY` 结构中，`FINALLY` 和 `THEN` 最多各定义一个
3. `CATCH` 可以定义多个，采用从上到下、短路优先匹配

## 运行时执行逻辑

`TryClause` 是 `SelfCompileInstruction`，在编译期展开为：

```text
[TryNode, try_body, ..., CatchHandler_1, catch_body_1, ..., FinNode(可选), fin_body(可选), NOP(escape)]
```

末尾的 `NOP` 是一个 **escape 哨兵节点**——所有执行路径（成功、捕获、未捕获、finally）最终都通过 `pc.jump_near(self._escape_addr)` 跳转到这里。这确保控制流永远不会错误地落入外层编排中的下一条指令。

`TryNode` 是整条异常处理链的入口。它的运行时逻辑如下：

1. **执行 TRY 块**：通过 `call_near` 调用 `try_body`
2. **无异常时**：
   - 若有 `THEN`，通过 `call_near` 调用 `then_body`
3. **有异常时**：
   - `TryNode` 的 `except BaseException` 捕获异常
   - 若异常在 `_exc_ignored` 中，直接 `raise` 穿透
   - 遍历 `_catch_addr_chain`，用 `isinstance` 匹配异常类型
   - 第一个匹配到的 CATCH 块被执行（通过 `call_near`）
   - 未匹配到的异常继续向上传播
4. **无论是否有异常**：`finally` 块始终执行（通过 `call_near` 调用 `fin_body`）
5. **所有块执行完毕后**：通过 `pc.jump_near(self._escape_addr)` 跳转到 escape 哨兵 NOP。

## 异常穿透规则

在 `WorkflowInterpreter` 初始化时，通过 `exception_ignored` 标记的异常类型不会被任何 `CATCH` 块捕获：

```python
pc = WorkflowInterpreter(
    workflow,
    exception_ignored=(CriticalError, InterruptNotice, BreakLoop)
)
```

当 `TryNode` 捕获到这些异常时，会直接 `raise`，让异常穿透当前层级，继续向上传播。这种机制确保了：

- **`InterruptNotice`** 始终能终止整个工作流，不被某个 TRY 块误吞
- **`BreakLoop`** 始终能跳出最内层循环，不被中间的异常处理拦截
- **关键业务异常** 可以绕过局部容错逻辑，直达顶层全局处理器

## 使用示例

### 指令编排：API 调用容错

```python
@Node() async def call_api(): return await http_get("/api")
@Node() async def use_cache(): return get_cached()
@Node() async def cleanup(): http_client.close()

api_flow = TRY(call_api).CATCH(TimeoutError, use_cache).FINALLY(cleanup)
```

### 节点内部：简单降级

```python
@Node()
async def call_api_simple():
    try:
        return await http_get("/api")
    except TimeoutError:
        return get_cached()  # 一行降级，不值得拆成独立节点
```

### 多异常分类处理

```python
TRY(risky_op)\
    .CATCH(ValueError, handle_value)\
    .CATCH(TypeError, handle_type)\
    .CATCH(Exception, handle_unknown)\
    .FINALLY(cleanup)
```

### 确保资源清理（即使无异常）

```python
TRY(acquire_resource).FINALLY(release_resource)
```

## 异常处理节点中的依赖注入

CATCH、THEN、FINALLY 块中的节点可以正常使用 `Depends` 声明依赖。被捕获的异常对象本身也可以通过依赖注入传入处理节点——这是指令编排相较于节点内部 try-catch 的独特优势：异常处理节点可以获得完整的依赖注入上下文。

> **关于 `Depends` 返回 `None`**
> 如果异常处理节点通过 `Depends` 声明了某个依赖，而该依赖的工厂函数返回了 `None`，工作流会**直接抛出异常并终止**。节点的依赖解析失败不是可以“跳过”的场景。因此，异常处理节点中使用的依赖应保证在所有执行路径下都能成功解析。
