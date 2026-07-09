# Type System

AmritaSense uses a small set of custom runtime types to represent workflow addresses and execution stacks. The most important types are `PointerVector` and `Stack`.

## PointerVector

`PointerVector` represents a multi-dimensional address in a workflow graph. It is the interpreter's program counter and supports nested workflows by storing a list of indices for each level of nesting.

Key operations:

- `offset(offset: int)`: Add a relative value to the last dimension.
- `near_to(short_offset: int)`: Replace the last dimension with an absolute value.
- `far_to(addr: list[int])`: Replace the entire address vector.
- `offset_far(offset: list[int])`: Apply a multi-dimensional offset.
- `append(node_ip: int)`: Enter a nested container by appending a new coordinate.
- `pop()`: Exit a nested level.
- `copy()`: Create a deep copy of the pointer vector.

`PointerVector` supports addition and subtraction with other `PointerVector` instances, making it easier to compute target addresses and relative offsets.

## Stack

`Stack` is a thread-safe generic LIFO stack used for return address management and other runtime stacks.

Key operations:

- `push(item)`: Push an item to the stack.
- `pop()`: Pop the top item from the stack.
- `clear()`: Remove all items from the stack.
- `resize(size: int)`: Change the maximum capacity.

The stack is protected by a lock and raises `OverflowError` if capacity is exceeded.

## InterpreterContext (v0.4.x+)

`InterpreterContext` is a dataclass that stores a complete snapshot of the interpreter's execution state. It is used by `PUSH_CONTEXT`/`POP_CONTEXT` and `INTERRUPT_INTO`/`INTERRUPT_RET` for save/restore workflows.

```python
@dataclass
class InterpreterContext:
    ptr: PointerVector
    exception_ignored: tuple[type[BaseException], ...]
    s_args: tuple | None = None
    s_kwargs: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    stack: Stack[PointerVector] | None = None
    exception: Exception | None = None
```

Fields:

- `ptr`: Snapshot of the execution pointer (`PointerVector`).
- `exception_ignored`: Snapshot of exception types that bypass TRY/CATCH.
- `s_args` / `s_kwargs`: Snapshot of dependency injection parameters. `None` if excluded during `dump_interpreter()`.
- `extra`: Extension data dictionary for custom use.
- `stack`: Snapshot of the return-address stack. `None` if excluded.
- `exception`: Snapshot of the panic exception, or `None` if no panic occurred.

## DICache (v0.4.2+)

`DICache` is a dataclass that manages the dependency injection result cache within the `WorkflowInterpreter`. It combines args fingerprinting with an LRU cache to avoid redundant DI resolution.

```python
@dataclass
class DICache:
    args_hash: int
    hash_trustable: bool
    payload: LRUCache[int, dict[str, Any]] = field(
        default_factory=lambda: LRUCache(1024)
    )
```

Fields:

- `args_hash`: Integer hash of the current DI argument types, computed by `_fingerprint_args()`. Used as part of the composite cache key `hash((hash(pointer), args_hash))`.
- `hash_trustable`: Boolean indicating whether `args_hash` is guaranteed to match the current `_ava_args` / `_ava_kwargs`. Set to `False` whenever those arguments are modified; restored by `rehash_args()`.
- `payload`: An `LRUCache` (from `cachetools`) mapping composite cache keys to resolved keyword argument dictionaries. Maximum 1024 entries with least-recently-used eviction.

## Event Types

### BaseEvent

`BaseEvent` is the abstract base class for all events in AmritaSense's event system. It is a generic dataclass parameterized by a string subtype (`stringSub_T`). Subclasses must implement both `event_type` (property) and `get_event_type()` (method) to return the event's type identifier.

### ConstructableEvent

`ConstructableEvent` extends `BaseEvent` with a `constructor()` class method that enables on-demand event construction during workflow execution. It is used with the `TRIGGER_EVENT` instruction.

```python
@dataclass
class ConstructableEvent(BaseEvent):
    @abstractmethod
    @classmethod
    def constructor(cls, *args, **kwargs) -> Self | Awaitable[Self]: ...
```

Subclasses must implement `constructor()`, which can return either a synchronous or asynchronous result. The runtime calls this method to build the event instance before dispatching it through `MatcherFactory.trigger_event()`.
