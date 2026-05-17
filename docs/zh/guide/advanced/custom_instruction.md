# 4.7 自定义指令集

AmritaSense 的内置指令集已经覆盖了条件分支、循环、异常处理等核心控制流。但当这些基本指令的组合反复出现、形成固定模式时，就可以通过 `SelfCompileInstruction` 将其封装为**新的指令**。这种扩展不侵入解释器，只在编译期展开为标准节点组合，运行时与内置指令完全等效。

---

## 4.7.1 自编译指令接口：SelfCompileInstruction

`SelfCompileInstruction` 是一个抽象基类，定义了所有自编译指令的统一入口：

```python
from abc import ABC, abstractmethod
from amrita_sense.node.core import NodeCompose

class SelfCompileInstruction(ABC):
    @abstractmethod
    def extract(self) -> NodeCompose:
        """将自定义指令展开为底层节点组合"""
        pass
```

### 核心概念

- **编译期展开**：`extract()` 在 `render()` 阶段被调用，不是在运行时。展开后的 `NodeCompose` 被递归渲染，最终生成与手写编排完全相同的 `NodeComposeRendered`
- **透明性**：对工作流的其他部分而言，自定义指令和内置指令没有区别。它们共享同一套别名系统、同一套寻址机制
- **组合性**：自定义指令内部可以包含其他指令（包括其他自定义指令），嵌套深度没有限制

### 实现要求

1. 必须实现 `extract()` 方法
2. `extract()` 只能依赖编译期已知的信息（构造参数）
3. 如果展开后的结构包含跳转，地址计算必须在 `extract()` 内完成
4. 返回的 `NodeCompose` 会被自动递归渲染，无需手动调用 `render()`

---

## 4.7.2 实现模式：extract() 与地址计算

实现自定义指令的核心工作，是将一个“意图”映射为一个“节点数组”。这个映射包括三个步骤：

### 步骤一：确定节点列表

将指令的语义拆解为具体的节点序列。例如，一个“重试”指令可以拆解为：执行节点 → 检查结果 → 若失败且未达上限则跳回 → 若成功或达上限则继续。

### 步骤二：计算跳转地址

如果展开后的结构包含跳转（`GOTO`、`ConditionJumpNode` 等），需要在 `extract()` 内根据节点列表的长度计算偏移量。所有地址必须是静态确定的整数。

### 步骤三：返回 NodeCompose

将节点列表包装为 `NodeCompose(*nodes)` 返回。框架会自动处理后续的递归渲染。

### 简单示例：带日志的节点包装器

```python
class LoggedNode(SelfCompileInstruction):
    def __init__(self, node: BaseNode, name: str):
        self._node = node
        self._name = name

    def extract(self) -> NodeCompose:
        @Node()
        def log_start():
            print(f"[{self._name}] 开始执行")

        @Node()
        def log_end():
            print(f"[{self._name}] 执行完毕")

        return NodeCompose(log_start, self._node, log_end)
```

使用：

```python
workflow = start >> LoggedNode(process_data, "数据处理") >> end
```

等价于手写：

```python
workflow = start >> log_start >> process_data >> log_end >> end
```

---

## 4.7.3 案例一：重试器

将一个可能失败的节点包装为支持重试的逻辑，是自编译指令的典型应用场景。

### 需求

- 执行目标节点
- 若节点抛出异常，自动重试
- 超过最大重试次数后，抛出最终异常或执行降级节点

### 实现

```python
from amrita_sense.instructions import IF, TRY
from amrita_sense.exceptions import BreakLoop

class RetryClause(SelfCompileInstruction):
    def __init__(self, node: BaseNode, max_retries: int = 3, fallback: BaseNode | None = None):
        self._node = node
        self._max = max_retries
        self._fallback = fallback

    def extract(self) -> NodeCompose:
        @Node()
        def attempt():
            pass  # 占位，实际逻辑由 TRY 块内的 self._node 执行

        @Node()
        def on_error():
            nonlocal retries
            retries += 1
            if retries >= self._max:
                raise BreakLoop   # 跳出重试循环，进入降级或向上抛异常

        retries = 0

        retry_body = TRY(self._node).CATCH(Exception, on_error)

        if self._fallback:
            return NodeCompose(
                WHILE(lambda: retries < self._max).ACTION(retry_body),
                self._fallback,
                NOP
            )
        else:
            return NodeCompose(
                WHILE(lambda: retries < self._max).ACTION(retry_body),
                NOP
            )
```

使用：

```python
RetryClause(call_api, max_retries=3, fallback=use_cache)
```

展开后等价于：

```python
WHILE(condition).ACTION(TRY(call_api).CATCH(Exception, on_error)) >> use_cache >> NOP
```

### 关键点

- `extract()` 内部使用了 `WHILE` 和 `TRY` 两个内置指令，展示了自编译指令的**组合性**
- 跳转地址由内置指令自动计算，`RetryClause` 无需手动管理偏移量
- 用户看到的只是 `RetryClause(...)`，底层展开细节完全透明

---

## 4.7.4 案例二：条件执行包装器

将“条件满足时执行某节点，否则跳过”这个常见模式封装为单一指令。

### 具体实现

```python
class ExecuteWhen(SelfCompileInstruction):
    def __init__(self, condition: Node[bool], action: BaseNode):
        self._cond = condition
        self._action = action

    def extract(self) -> NodeCompose:
        return NodeCompose(
            IF(self._cond, self._action).ELSE(NOP)
        )
```

使用：

```python
ExecuteWhen(has_data, process_data)
```

等价于 `IF(has_data, process_data).ELSE(NOP)`，但语义更明确——“当条件满足时执行”。

### 扩展：带否则分支的版本

```python
class ExecuteWhenElse(SelfCompileInstruction):
    def __init__(self, condition: Node[bool], action: BaseNode, otherwise: BaseNode):
        self._cond = condition
        self._action = action
        self._other = otherwise

    def extract(self) -> NodeCompose:
        return NodeCompose(
            IF(self._cond, self._action).ELSE(self._other)
        )
```

---

## 自定义指令的设计原则

1. **封装模式，而非封装逻辑**：自定义指令应封装反复出现的**编排模式**（如重试、条件执行、超时保护），而非具体的业务逻辑。业务逻辑应留在节点内部

2. **利用现有指令**：优先通过组合 `IF`、`WHILE`、`TRY` 等内置指令来构建自定义指令，而非直接管理跳转偏移。只有在内置指令无法表达所需控制流时，才需要手动计算地址

3. **保持透明**：自定义指令展开后的结构应与手写编排一致，不影响调试、挂起、中断等机制的正常工作

4. **命名语义化**：指令名称应直接传达其控制流意图（如 `Retry`、`Timeout`、`Parallel`），让编排链读起来像自然语言
