# 类型系统

AmritaSense 的类型系统提供了工作流执行所需的核心数据结构。

## Stack

```python
class Stack(Generic[T]):
    """A thread-safe, bounded stack implementation used for managing execution
    state in the workflow engine.

    This stack is used for both the execution pointer stack and the return
    address stack, providing LIFO operations with overflow protection.
    """
```

**核心特性**:

- **线程安全**: 使用内部锁确保并发安全
- **溢出保护**: 默认最大容量为 1024 个元素
- **类型安全**: 泛型实现，支持任意类型

**主要方法**:

- `push(item: T) -> None`: 压入元素
- `pop() -> T`: 弹出元素（栈为空时抛出异常）
- `peek() -> T`: 查看栈顶元素（不弹出）
- `clear() -> None`: 清空栈
- `is_empty() -> bool`: 检查栈是否为空

**使用场景**:

- 执行指针栈（`_pointer`）
- 返回地址栈（`_ret_addr_stack`）

## PointerVector

```python
class PointerVector:
    """This class represents a multi-dimensional address vector used to navigate
    through nested workflow structures.

    Each dimension in the vector represents a level in the nested hierarchy,
    allowing precise addressing of nodes within complex workflow graphs.
    """
```

**核心特性**:

- **多维地址**: 支持嵌套工作流的精确寻址
- **不可变性**: 地址向量一旦创建就不能修改
- **数学运算**: 支持地址向量的加减运算

**主要属性**:

- `vector`: 底层的整数列表，表示多维地址

**主要方法**:

- `__add__(other: PointerVector) -> PointerVector`: 地址向量加法
- `__sub__(other: PointerVector) -> PointerVector`: 地址向量减法
- `__eq__(other) -> bool`: 相等性比较
- `copy() -> PointerVector`: 创建副本

**地址示例**:

- `[0]`: 第0层的第0个元素
- `[0, 2, 1]`: 第0层第0个，第1层第2个，第2层第1个元素

**寻址模式**:

- **绝对寻址**: 使用完整的地址向量
- **相对寻址**: 在同一层级内进行偏移
- **近寻址**: 修改当前层级索引，保持其他层级不变

## DICache（v0.4.2+）

`DICache` 是管理 `WorkflowInterpreter` 中依赖注入结果缓存的数据类。它将参数指纹与 LRU 缓存结合，避免重复 DI 解析。

```python
@dataclass
class DICache:
    args_hash: int
    hash_trustable: bool
    payload: LRUCache[int, dict[str, Any]] = field(
        default_factory=lambda: LRUCache(2048)
    )
```

字段说明：

- `args_hash`：当前 DI 参数类型的整数哈希，由 `_fingerprint_args()` 计算。作为复合缓存键 `hash((hash(pointer), args_hash))` 的一部分。
- `hash_trustable`：布尔值，指示 `args_hash` 是否保证与当前 `_ava_args` / `_ava_kwargs` 匹配。修改这些参数时置为 `False`；调用 `rehash_args()` 恢复。
- `payload`：来自 `cachetools` 的 `LRUCache`，将复合缓存键映射到已解析的关键字参数字典。最大 2048 条，按最近最少使用策略淘汰。

## 事件类型

### BaseEvent

`BaseEvent` 是 AmritaSense 事件系统中所有事件的抽象基类。它是一个泛型数据类，由字符串子类型（`stringSub_T`）参数化。子类必须实现 `event_type`（属性）和 `get_event_type()`（方法）来返回事件的类型标识。

### ConstructableEvent

`ConstructableEvent` 继承自 `BaseEvent`，额外定义了一个 `constructor()` 类方法，使事件能够在工作流执行期间按需构造。它与 `TRIGGER_EVENT` 指令配合使用。

```python
@dataclass
class ConstructableEvent(BaseEvent):
    @abstractmethod
    @classmethod
    def constructor(cls, *args, **kwargs) -> Self | Awaitable[Self]: ...
```

子类必须实现 `constructor()`，可返回同步或异步结果。运行时调用此方法构建事件实例，然后通过 `MatcherFactory.trigger_event()` 分发。
