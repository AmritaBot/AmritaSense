# Unsafe 特性

`amrita_sense._unsafe` 模块暴露了控制框架底层行为的内部开关。这些开关**不**适合日常使用——它们是实现细节，仅为少数无法用默认行为满足的极端场景而开放。

::: warning
这些标志**不受**语义化版本（SemVer）兼容性保证的覆盖。它们的语义、名称甚至存在本身都可能在次版本或补丁版本中无通知地变更。生产环境中应保持默认值。
:::

## `__flags__` —— 标志注册中心

所有标志都存放在一个名为 `__flags__` 的 `_Flags` 数据类实例中：

```python
from amrita_sense._unsafe import __flags__
```

### 一次性设置，永久锁定

每个标志只能设置**一次**。尝试二次赋值会抛出 `RuntimeError`。这种设计防止了运行时意外切换，确保了整个解释器生命周期内的行为一致性。

推荐做法是在应用程序入口最顶部、**任何解释器创建之前**配置标志：

```python
# ✅ 正确：在 main.py / __main__.py 最顶部
from amrita_sense._unsafe import __flags__
__flags__.ALLOW_CALL_NODECOMPOSE = True

# ... 后续应用程序代码
```

```python
# ❌ 错误：这将抛出 RuntimeError
__flags__.ALLOW_CALL_NODECOMPOSE = True
# ... 稍后 ...
__flags__.ALLOW_CALL_NODECOMPOSE = False  # RuntimeError!
```

## 标志参考

### `FORCE_NOT_WRAP_TO_ASYNC`

```python
FORCE_NOT_WRAP_TO_ASYNC: bool = False
```

默认情况下，函数为同步但 `wrap_to_async=True` 的节点会通过 `asyncio.to_thread()` 执行，以避免阻塞事件循环。将此标志设为 `True` 会强制所有这些节点在事件循环线程上同步运行。

**适用场景**：纯 CPU 密集型工作流，不想承担线程池开销，且能容忍短暂的事件循环阻塞。

### `DISABLE_EXC_IGNORED`

```python
DISABLE_EXC_IGNORED: bool = False
```

默认情况下，`InterruptNotice` 和 `BreakLoop` 会自动加入 `_exc_ignored`，使其穿透所有 `TRY/CATCH` 块。匹配器系统在依赖解析时也会遵守 `exception_ignored` 类型。将此标志设为 `True` 会禁用所有这些行为——不再有任何异常被自动忽略，匹配器将所有异常视为可捕获。

**适用场景**：需要 `TRY/CATCH` 块拦截 `BreakLoop` 或 `InterruptNotice`，或者希望完全手动控制异常穿透行为。

### `ALLOW_CALL_NODECOMPOSE`

```python
ALLOW_CALL_NODECOMPOSE: bool = False
```

默认情况下，对 `NodeCompose` 调用 `_call()` 会抛出 `RuntimeError`。将此标志设为 `True` 会抑制该错误，允许直接调用 `NodeCompose`。这在某些 `SelfCompileInstruction` 需要将渲染出的 `NodeCompose` 作为整体调用时非常有用。

**适用场景**：自定义 `SelfCompileInstruction` 需要调用 `NodeCompose` 而不通过 `FUN_BLOCK` 包装时。

### `NO_DEPENDENCY_META_CACHE`

```python
NO_DEPENDENCY_META_CACHE: bool = False
```

默认情况下，`FunctionData` 会在节点的函数对象上缓存已解析的 `DependencyMeta`（来自 `sign_func`）。将此标志设为 `True` 会在每次调用时强制重新解析 `DependencyMeta`，跳过缓存。

**适用场景**：运行时动态修改函数签名（如 monkey-patching）且需要每次重新解析。会有性能开销。

### `NO_SHARED_MIDDLEWARE`

```python
NO_SHARED_MIDDLEWARE: bool = False
```

默认情况下，`fork_interpreter()` 在 `middleware=UNSET` 时会继承父解释器的中间件。将此标志设为 `True` 会强制 `fork_interpreter()` 传入 `None` 作为中间件，除非显式覆盖。

**适用场景**：希望父子解释器之间严格隔离中间件，倾向于显式按需开启的模式。

### `JIT_OPTIMIZE`（v0.4.x+）

```python
JIT_OPTIMIZE: bool = False
```

启用后，NOP 节点（`_no_operation`）在 `_call()` 执行中被跳过，不调用完整的依赖注入路径。这避免了占位节点的 asyncio 上下文切换和锁获取/释放开销。

**适用场景**：在具有大量 NOP 汇合点的工作流中（如重度使用 IF/ELIF 分支），此标志可降低逐节点开销。

> **注意**：此标志标记为 `# TODO: more optimizations`——未来版本可能会添加更多 JIT 优化。

## 与其他系统的交互

多个内置指令和匹配器系统在关键决策点读取标志：

| 标志                       | 影响的系统                                                                       |
| -------------------------- | -------------------------------------------------------------------------------- |
| `DISABLE_EXC_IGNORED`      | `TryNode._call()`、`MatcherFactory._resolve()`、`WorkflowInterpreter.__init__()` |
| `ALLOW_CALL_NODECOMPOSE`   | `WorkflowInterpreter._call()`                                                    |
| `NO_DEPENDENCY_META_CACHE` | `WorkflowInterpreter._call()`、`MatcherFactory._prepare()`                       |
| `FORCE_NOT_WRAP_TO_ASYNC`  | `WorkflowInterpreter._call()`                                                    |
| `NO_SHARED_MIDDLEWARE`     | `WorkflowInterpreter.fork_interpreter()`                                         |
| `JIT_OPTIMIZE`             | `WorkflowInterpreter._call()`                                                    |

## 汇总

| 标志                       | 默认值  | 效果                       |
| -------------------------- | ------- | -------------------------- |
| `FORCE_NOT_WRAP_TO_ASYNC`  | `False` | 强制同步节点保持同步       |
| `DISABLE_EXC_IGNORED`      | `False` | 禁用异常自动穿透           |
| `ALLOW_CALL_NODECOMPOSE`   | `False` | 允许直接调用 `NodeCompose` |
| `NO_DEPENDENCY_META_CACHE` | `False` | 每次调用重新解析依赖元数据 |
| `NO_SHARED_MIDDLEWARE`     | `False` | fork 时不继承父中间件      |
| `JIT_OPTIMIZE`             | `False` | 执行时跳过 NOP 节点        |
