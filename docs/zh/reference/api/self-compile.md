# 自编译指令

自编译指令是 AmritaSense 实现高级控制流的核心机制。它们在工作流渲染阶段自动展开为标准的底层节点组合，使得开发者可以像使用内置指令一样，使用自己封装的复杂编排模式。

## SelfCompileInstruction

```python
class SelfCompileInstruction(ABC):
    """Abstract base class for all self-compiling instructions.

    Self-compiling instructions are expanded into NodeCompose structures during
    the workflow rendering phase. This allows for compile-time optimization
    and static address calculation without requiring changes to the interpreter.
    """
```

`SelfCompileInstruction` 是所有自编译指令的抽象基类。它的核心职责只有一个：将高级语义映射为底层节点组合。这个映射发生在 `render()` 阶段，因此所有地址计算、结构展开都在执行前完成，运行时没有任何额外开销。

**核心方法**

- `extract() -> NodeCompose`：将指令展开为底层节点组合。必须返回一个 `NodeCompose` 实例，该实例会被框架自动递归渲染。
- `__rshift__(other) -> NodeCompose`：支持 `>>` 运算符，使自编译指令可以直接与普通节点组合。语法糖：`instruction >> node` 等价于 `NodeCompose(instruction, node)`。

**设计理念**

自编译指令是 AmritaSense 扩展性的基石。内置的 `IF`、`WHILE`、`TRY` 等全部实现自这一接口，而开发者可以通过继承它来创建自己的控制流原语——封装的是**编排模式**，而非具体业务逻辑。

## 内置自编译指令

AmritaSense 的内置指令集全部是 `SelfCompileInstruction` 的子类。以下仅列出它们在编译期展开的空间结构，详细语法和运行时行为请参见 `第 4.5 节：内置指令集`。

### 条件分支指令

- **`IFClause`**：`IF(cond, do)` -> `[ConditionJumpNode, condition, do, NOP]`
- **`ELIFClause`**：在 `IFClause` 基础上扩展 ELIF 链，每个 ELIF 追加一组 `[ConditionJumpNode, condition, do]`，最终 NOP 作为统一出口
- **`ELSEClause`**：在 IF 或 IF-ELIF 链后追加 `[ELSENode, else_do, NOP]`

### 循环指令

- **`WhileClause`**：`WHILE(condition).ACTION(action)` -> `[WhileNode, condition, action, CheckUpNode, NOP]`
- **`DoWhileClause`**：`DO(do).WHILE(condition)` -> `[DONode, do, DowhileNode, condition, NOP]`

### 异常处理指令

- **`TryClause`**：展开为 `[TryNode, try_body, ...catch_handler_i, catch_body_i..., FinNode(可选), fin_body, NOP]`。`TryNode` 管理整条异常处理链的运行时逻辑。

### 子程序存储指令

- **`SubprogramStorage`**（`ARCHIVED_NODES` 的底层实现）：展开为 `[SubprogramJumpNode, node_1, node_2, ..., NOP]`。接收任意 `BaseNode`（不限于 `ALIAS`），`SubprogramJumpNode` 在正常执行流中无条件跳过整个存储区。内部节点可通过 `CALL` 或 `GOTO` 寻址访问（若使用 `ALIAS` 标记）。

### 注意：CALL 不是自编译指令

`CALL` 指令对应的 `CallNode` 直接继承自 `BaseNode`，是一个**普通节点**。它在编译期不展开，只是作为单个节点存在于工作流数组中，编译时通过 `_post_compile` 解析别名，执行时通过 `pc.call_sub` 完成调用。这与 `GOTO`（`JumpNode`）的设计一致——两者都是"原子"跳转节点，而非自编译结构。

## 自定义自编译指令

### 实现步骤

1. **继承 `SelfCompileInstruction`**
2. **在 `__init__` 中接收构造参数**：这些参数决定了展开后的节点组合
3. **实现 `extract() -> NodeCompose`**：在此方法内完成所有地址计算和节点组合，返回最终的 `NodeCompose`

### 简单示例

```python
class LoggedNode(SelfCompileInstruction):
    """在执行节点前后各加一条日志"""
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

使用：`LoggedNode(process_data, "数据处理")` 等价于手写 `log_start >> process_data >> log_end`。

### 设计原则

**编译期 vs 运行时**

- **编译期**：`extract()` 内完成地址计算、结构展开、静态优化。所有跳转偏移量在此阶段确定
- **运行时**：展开后的普通节点由解释器正常执行，没有额外的编译开销

**地址计算策略**

- 展开后的结构如果包含跳转（如 `ConditionJumpNode`），地址偏移量需要在 `extract()` 内根据节点列表长度静态计算
- 如果展开结构复用了 `IF`、`WHILE` 等内置指令，地址计算由内置指令自行完成，无需手动管理

**封装模式，而非封装逻辑**

自定义指令应封装反复出现的**编排模式**（如重试、超时、条件执行），而非具体业务逻辑。业务逻辑应留在节点函数内部。

**错误处理**

- 参数验证放在 `__init__` 中，尽早失败
- `extract()` 中抛出的异常会阻止工作流渲染

**可组合性**

自定义指令内部可以包含其他自编译指令（包括内置指令），嵌套深度没有限制。
