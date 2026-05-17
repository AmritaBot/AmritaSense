# 核心节点类

AmritaSense 的节点系统是整个工作流引擎的基础。所有工作流元素——无论是业务函数、控制流指令还是编排容器——最终都是节点的实例或组合。

---

## BaseNode

`BaseNode` 是所有节点的抽象基类。它定义了节点在 AmritaSense 运行时中的通用接口和最小元数据集。开发者通常不直接继承 `BaseNode`，而是使用 `@Node()` 装饰器或继承 `Node`，但在实现自定义指令的底层跳转节点时可能会用到。

```python
class BaseNode:
    func: Callable[..., Any]
    tag: str
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: inspect.Signature
```

### 属性

- `func`：底层可调用对象。执行节点时解释器最终调用的就是它
- `tag`：节点的字符串标识。同时作为流程挂起的断点名称——外部可以通过 `wait_to_suspend(tag)` 在该节点执行前挂起。若创建时未指定，默认为 `NodeSuspend::{函数名}`
- `wrap_to_async`：若为 `True` 且 `func` 是同步函数，解释器会自动使用 `asyncio.to_thread` 在线程池中执行，避免阻塞事件循环
- `address_able`：若为 `True`，该节点可被 `ALIAS` 引用。只有可寻址的节点才能成为 `GOTO`、`CALL` 等跳转指令的目标
- `fun_sign`：由 `inspect.signature(func)` 提取的函数签名，供依赖注入系统在运行时解析参数
- `fun_frame`：节点创建时的栈帧对象，主要用于调试和日志定位

### 方法

- `_pre_check(pointer: WorkflowInterpreter) -> None`：执行前的钩子。每次节点执行前被解释器调用，可在此完成编译期验证和地址缓存。`CallNode` 和 `JumpNode` 正是在此方法中完成别名查表和拼写纠错
- `_init(func, tag, wrap_to_async, address_able, frame)`：内部构造方法，统一设置节点的元数据
- `__call__(*args, **kwargs)`：抽象方法，子类必须实现。定义节点的执行行为

**重要**：`BaseNode` 及其子类使用 `__slots__` 定义属性，避免了默认的 `__dict__` 开销，让每个节点实例尽可能紧凑。这对于可能包含数百上千个节点的工作流来说，内存优势会非常明显。

---

## Node

`Node` 是 `BaseNode` 的泛型具体实现，也是开发者最常接触的节点类型。使用 `@Node()` 装饰器创建的节点就是 `Node` 实例。它将一个普通的 Python 函数或协程包装为工作流的基本执行单元。

```python
class Node(BaseNode, Generic[NODE_T]):
    ...
```

### 创建方式

```python
@Node(tag="custom_tag", wrap_to_async=True, address_able=True)
def my_function(arg1: str) -> str:
    return arg1.upper()
```

### 构造参数

- `tag: str | None`：节点的断点标签。默认自动生成
- `wrap_to_async: bool`：若为 `True` 且函数是同步的，在线程池中执行。默认 `True`
- `address_able: bool`：是否可被 `ALIAS` 绑定。默认 `True`

### 特性

- 泛型参数 `NODE_T` 保留原函数的返回类型，类型检查器可以追踪
- 在 `>>` 链式编排中可与任何 `BaseNode`、`NodeCompose` 或 `SelfCompileInstruction` 串联
- 如果节点函数签名中声明了 `WorkflowInterpreter` 类型的参数（通过 `POINTER_DEPENDS` 注入），节点在执行时将获得当前解释器实例的完全访问权
- 节点的 `__call__` 属性直接返回原始函数对象，使得 `node(...)` 等价于 `func(...)`

---

## NodeCompose

`NodeCompose` 是节点编排的容器。它维护一个有序的节点列表，并通过 `__rshift__` 支持 `>>` 链式追加。`NodeCompose` 同时也是 `SelfCompileInstruction.extract()` 的标准返回类型——自编译指令最终都将自身的语义展开为一个 `NodeCompose`。

```python
class NodeCompose:
    _graph: list[BaseNode | NodeCompose | SelfCompileInstruction]
```

### 特性

- **链式追加**：`compose >> new_node` 等价于 `compose._graph.append(new_node)`
- **嵌套能力**：`_graph` 中的元素本身也可以是 `NodeCompose`，这是 Bubble 作用域的数据基础
- **编译入口**：调用 `render()` 方法触发编译流程，生成 `NodeComposeRendered`

### 方法

- `__rshift__(other)`：实现 `>>` 运算符，将 `other` 追加到内部列表并返回 `self`
- `render() -> NodeComposeRendered`：编译当前编排结构。所有 `SelfCompileInstruction` 在此阶段被展开，递归的 `NodeCompose` 被解析为嵌套的 `NodeComposeRendered`，最终生成带地址映射的可执行图

### 使用示例

```python
workflow = NodeCompose(node_a, node_b)
# 或更简洁的写法：
workflow = node_a >> node_b >> node_c
```

---

## NodeComposeRendered

`NodeComposeRendered` 是编译的最终产物——一个完整解析、优化、带地址映射的可执行工作流图。`WorkflowInterpreter` 接受的正是此类型的实例。

```python
class NodeComposeRendered:
    _graph: list[BaseNode | NodeComposeRendered]
    alias2vector_map: dict[str, list[int]]
```

### 编译过程

`render()` 调用触发 `_build()` 递归遍历原始的 `NodeCompose` 结构：

1. 展开所有 `SelfCompileInstruction`（调用其 `extract()` 方法）
2. 将嵌套的 `NodeCompose` 递归渲染为 `NodeComposeRendered`
3. 为每个节点分配 `PointerVector` 地址
4. 收集所有 `AliasNode`，将别名与地址的映射存入 `alias2vector_map`

### 主要属性

- `_graph: list[BaseNode | NodeComposeRendered]`：编译后的节点序列。元素可能是具体节点或子容器
- `alias2vector_map: dict[str, list[int]]`：别名到指针向量的映射表。GOTO、CALL 等跳转指令在 `_pre_check` 阶段从此表查地址
- `__bool__()`：检查 `_graph` 是否已构建，用于判断编译是否完成

### 获取方式

```python
rendered = workflow.render()
# workflow 可以是 NodeCompose 或任何 SelfCompileInstruction
```

**重要**：`NodeComposeRendered` 是不可变的——一旦编译完成，其结构和地址映射不应再被修改。运行时所有状态由 `WorkflowInterpreter` 管理，`NodeComposeRendered` 仅作为只读的“代码段”存在。
