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

少数标志（列于 `_writeables` 集合中）是**可重复写入**的——可以随时修改。当前包括 `WORKFLOW_DI_PRELOAD_BATCH` 和 `WORKFLOW_DI_NO_CACHE`。关于互斥标志的规则，参见[标志冲突检测](#标志冲突检测)。

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

### `SQUASHED_LOOP`（v0.4.3+）

```python
SQUASHED_LOOP: bool = False
```

启用后，`WHILE` 和 `DO-WHILE` 循环以单个原生 Python `while` 循环执行，不再通过重复的 `call_offset`/`jump_near` 调用在 `WhileNode`/`DONode` → condition → action → `CheckUpNode`/`DowhileNode` 之间跳跃。整个循环体在单个解释器步骤内运行，避免了每次迭代的指针推进、锁获取和跳转操作的开销。

**适用场景**：热循环场景（具有大量迭代的紧内层循环），迭代间开销可测量且不需要在外层中断单个循环子步骤。注意在压扁模式下，`BreakLoop` 和 `jump_marked` 仍然被正确处理——不支持跳转到循环结构之外的地址。

### `NO_ADDRESSING_CACHE`（v0.4.3+）

```python
NO_ADDRESSING_CACHE: bool = False
```

禁用 `advance_pointer()` 中的 `_ptr_cache`。默认 `False` 时，解释器缓存指针推进的结果——若同一指针位置被再次访问，直接复用缓存的 `base_addr`，避免嵌套工作流中 O(D²) 的回溯遍历。

设为 `True` 后，强制解释器每次从头在图中计算下一指针位置，完全绕过缓存。

**适用场景**：调试期间，或工作流图结构在运行时动态变化导致缓存结果可能过时。禁用缓存也会减少内存使用，但以性能为代价。

### `WORKFLOW_DI_NO_CACHE`（v0.4.2+）

```python
WORKFLOW_DI_NO_CACHE: bool = False
```

禁用工作流执行的 DI 结果缓存。默认 `False` 时，解释器按节点地址缓存依赖注入结果——若同一节点在相同指针位置且 DI 参数类型相同时被再次访问，直接复用缓存的 kwargs，避免重复依赖解析。

设为 `True` 后，每次节点调用都从头重新解析依赖，完全绕过 `_di_cache`。

**适用场景**：依赖提供者有副作用、每次调用都必须执行；或参数频繁变化、缓存命中率预期很低。注意此标志在 `_writeables` 中，可在运行时切换。

### `WORKFLOW_DI_PRELOAD_CACHE`（v0.4.2+）

```python
WORKFLOW_DI_PRELOAD_CACHE: bool = False
```

启用后，解释器在 `run()` 初始化阶段为工作流中**所有节点**预解析依赖注入，在第一个节点执行前即填满 `_di_cache`。这使所有 DI 解析工作前置，主循环中的每次 `_call()` 都是缓存命中，零解析开销。

**适用场景**：DI 解析昂贵（如复杂类型匹配、节点数量多）且期望可预测的低延迟逐节点执行。代价是与工作流图大小成正比的一次性启动开销。

> **⚠️ 冲突**：此标志与 `NO_DEPENDENCY_META_CACHE` 冲突，同时设置会抛出 `RuntimeError`。

### `WORKFLOW_DI_PRELOAD_BATCH`（v0.4.2+）

```python
WORKFLOW_DI_PRELOAD_BATCH: int = 10
```

控制 `WORKFLOW_DI_PRELOAD_CACHE` 启用时 DI 预加载的批量大小。`_refresh_di_cache_full()` 中以 `asyncio.gather()` 并发批量解析节点。较大批量增加并行度但可能压垮事件循环；较小批量更平缓但总耗时更长。

**适用场景**：需要平衡预加载速度与事件循环响应性时调整此值。此标志在 `_writeables` 中，可在调用 `run()` 之前随时调整。

### 标志冲突检测（v0.4.2+）

某些标志组合互斥。引擎在赋值时强制检测——设置会产生冲突的标志将抛出 `RuntimeError`，消息列出冲突标志。

定义了以下冲突：

| 标志 A                      | 标志 B                      | 原因                                  |
| --------------------------- | --------------------------- | ------------------------------------- |
| `WORKFLOW_DI_NO_CACHE`      | `WORKFLOW_DI_PRELOAD_CACHE` | 预加载填充缓存却被立即禁用            |
| `WORKFLOW_DI_PRELOAD_CACHE` | `NO_DEPENDENCY_META_CACHE`  | 预加载依赖缓存的元数据进行高效批量 DI |

冲突检测在每次标志赋值时运行。它评估每个冲突组：若赋值后组内所有标志都为 truthy，则拒绝该赋值。

## 与其他系统的交互

多个内置指令和匹配器系统在关键决策点读取标志：

| 标志                        | 影响的系统                                                                       |
| --------------------------- | -------------------------------------------------------------------------------- |
| `DISABLE_EXC_IGNORED`       | `TryNode._call()`、`MatcherFactory._resolve()`、`WorkflowInterpreter.__init__()` |
| `ALLOW_CALL_NODECOMPOSE`    | `WorkflowInterpreter._call()`                                                    |
| `NO_DEPENDENCY_META_CACHE`  | `WorkflowInterpreter._call()`、`MatcherFactory._prepare()`                       |
| `FORCE_NOT_WRAP_TO_ASYNC`   | `WorkflowInterpreter._call()`                                                    |
| `NO_SHARED_MIDDLEWARE`      | `WorkflowInterpreter.fork_interpreter()`                                         |
| `SQUASHED_LOOP`             | `WhileNode._while_worker()`、`DONode._do_worker()`                               |
| `NO_ADDRESSING_CACHE`       | `WorkflowInterpreter.advance_pointer()`                                          |
| `WORKFLOW_DI_NO_CACHE`      | `WorkflowInterpreter._call()`                                                    |
| `WORKFLOW_DI_PRELOAD_CACHE` | `WorkflowInterpreter.run()`、`WorkflowInterpreter._call()`                       |
| `WORKFLOW_DI_PRELOAD_BATCH` | `WorkflowInterpreter._refresh_di_cache_full()`                                   |

## 汇总

| 标志                        | 默认值  | 效果                             |
| --------------------------- | ------- | -------------------------------- |
| `FORCE_NOT_WRAP_TO_ASYNC`   | `False` | 强制同步节点保持同步             |
| `DISABLE_EXC_IGNORED`       | `False` | 禁用异常自动穿透                 |
| `ALLOW_CALL_NODECOMPOSE`    | `False` | 允许直接调用 `NodeCompose`       |
| `NO_DEPENDENCY_META_CACHE`  | `False` | 每次调用重新解析依赖元数据       |
| `NO_SHARED_MIDDLEWARE`      | `False` | fork 时不继承父中间件            |
| `SQUASHED_LOOP`             | `False` | 将 while/do-while 压扁为原生循环 |
| `NO_ADDRESSING_CACHE`       | `False` | 禁用指针推进缓存                 |
| `WORKFLOW_DI_NO_CACHE`      | `False` | 禁用 DI 结果缓存（可重复写入）   |
| `WORKFLOW_DI_PRELOAD_CACHE` | `False` | 启动时预解析所有节点的 DI        |
| `WORKFLOW_DI_PRELOAD_BATCH` | `10`    | DI 预加载批量大小（可重复写入）  |
