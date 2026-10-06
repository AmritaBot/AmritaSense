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

## InterpreterContext

`InterpreterContext` is a dataclass that stores a complete snapshot of the interpreter's execution state. It is used by `PUSH_CONTEXT`/`POP_CONTEXT` and `INT`/`IRET` for save/restore workflows.

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
    flags: Flags = Flags.NONE
```

Fields:

- `ptr`: Snapshot of the execution pointer (`PointerVector`).
- `exception_ignored`: Snapshot of exception types that bypass `Try`/`CATCH`.
- `s_args` / `s_kwargs`: Snapshot of dependency injection parameters. `None` if excluded during `dump_interpreter()`.
- `extra`: Extension data dictionary for custom use.
- `stack`: Snapshot of the return-address stack. `None` if excluded.
- `exception`: Snapshot of the panic exception, or `None` if no panic occurred.
- `flags`: Snapshot of the status register. `dump_interpreter()` strips `HLT` when it builds the snapshot, because a snapshot records the state to come back to and "the loop is parked on this node" is not part of it. Restoring therefore never resurrects a halt.

`ptr` and `exception_ignored` are required positional fields; every other field has a default, so an instance can also be built by hand and pushed onto `pc.context_stack` directly.

The canonical producer is `WorkflowInterpreter.dump_interpreter()` (called by `PUSH_CONTEXT` and `INT`) and the canonical consumer is `WorkflowInterpreter.rebase_context()` (called by `IRET`). Both `PUSH_CONTEXT` and `INT` build the snapshot first and then **overwrite** `ptr` with their resolved return address, so the snapshot's `ptr` is the address execution resumes at — not necessarily the pointer at snapshot time.

## Flags

`Flags` is an `IntFlag` holding the interpreter's discrete control-flow state. Keeping the bits in one register makes snapshotting, restoring and clearing them a single assignment.

| Member | Meaning                                                                |
| ------ | ---------------------------------------------------------------------- |
| `NONE` | No bit set                                                             |
| `IF`   | Inside an interrupt handler; `INT` is rejected while set               |
| `HLT`  | Halted on a node; the next run steps past it before executing anything |
| `JMP`  | A jump already moved the pointer; the main loop must not advance it    |

`amrita_sense.runtime.types` also exports `FLAG_IF`, `FLAG_HLT` and `FLAG_JMP`: plain-int mirrors of those three bits, derived from the enum at import time so they cannot drift out of sync. Hot code should test `int(flags) & FLAG_HLT` rather than `flags & Flags.HLT`. The latter goes through `Flag.__and__`, which re-wraps the result via `EnumType.__call__` / `__new__` -- measured 930 ns against 80 ns for the int form -- and the interpreter tests `HLT` and `JMP` on every step.

## DICache

`DICache` is a dataclass that manages the dependency injection result cache within the `WorkflowInterpreter`. It combines args fingerprinting with an LRU cache to avoid redundant DI resolution.

```python
@dataclass
class DICache:
    args_hash: int
    hash_trustable: bool
    payload: LRUCache[int, tuple[dict[str, Any], dict[str, Any]]] = field(
        default_factory=lambda: LRUCache(2048)
    )
```

Fields:

- `args_hash`: Integer fingerprint of the current DI argument types, computed by `_fingerprint_args()`. Used as part of the cache key `hash((id(node.func), args_hash))`.
- `hash_trustable`: A **cache-validity gate** (not a hash-correctness assertion) indicating whether `args_hash` is guaranteed to match the current `_ava_args` / `_ava_kwargs`. Set to `False` whenever those arguments are modified; restored by `rehash_args()`. While `False`, the LRU payload is neither read nor written.
- `payload`: An `LRUCache` (from `cachetools`) mapping cache keys to a `(static_kwargs, non_cacheable_factories)` tuple. Maximum 2048 entries with least-recently-used eviction. `cacheable=True` factory results are merged into `static_kwargs`; `cacheable=False` factories are re-resolved per call.

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
