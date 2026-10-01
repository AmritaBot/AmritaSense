# Runtime System

The runtime system executes compiled workflow graphs, manages the program counter, handles call stacks, and performs dependency injection at node execution time. `WorkflowInterpreter` is the core execution engine in AmritaSense and is designed for step-by-step interpretation rather than bulk graph traversal.

## WorkflowInterpreter

```python
class WorkflowInterpreter(Generic[io_T]): ...
```

`WorkflowInterpreter` is the main engine for executing a rendered workflow graph. It tracks the current execution pointer using `PointerVector`, manages subroutine calls through a return address stack, and supports external interruption and streaming via a generic `object_io` interface.

### Constructor

The interpreter accepts any _rendered graph_ satisfying the contract `AbstractCompose[AddressCalculator]` — in practice this is `NodeComposeRendered` (the default implementation). See [Compose Contracts](/guide/advanced/compose-contracts).

```python
WorkflowInterpreter(
    node_compose: AbstractCompose[AddressCalculator] | SelfCompileInstruction,
    object_io: SuspendObjectStream[Any] | None = None,
    *,
    exception_ignored: tuple[type[BaseException], ...] = (),
    extra_args: tuple = (),
    extra_kwargs: dict[str, Any] | None = None,
    addr_stack: Stack[PointerVector] | None = None,
    context_stack: Stack[InterpreterContext] | None = None,
    middleware: Callable[['WorkflowInterpreter'], Awaitable[Any]] | None = None,
    parent_interpreter: WorkflowInterpreter | None = None,
)
```

Arguments:

- `node_compose`: A rendered workflow graph (an `AbstractCompose[AddressCalculator]`, typically `NodeComposeRendered`) or a self-compiling instruction.
- `object_io`: Optional external I/O object. Defaults to a new `SuspendObjectStream`.
- `exception_ignored`: Exception types to bypass `Try`/`CATCH` blocks.
- `extra_args` / `extra_kwargs`: Additional runtime values available for dependency injection.
- `addr_stack`: Optional return address stack.
- `context_stack`: Optional pre-initialized interpreter context stack for save/restore workflows. Defaults to a new empty `Stack[InterpreterContext]`.
- `middleware`: Optional async callable that receives the `WorkflowInterpreter` instance. When set, `run_step_by()` and `call_sub()` delegate to the middleware instead of calling nodes directly. The middleware can decide whether and how to execute nodes, transform results, or inject custom logic around every step.
- `parent_interpreter`: Optional parent `WorkflowInterpreter` for building an interpreter tree. Set automatically by `fork_interpreter()` — rarely needed directly.

### Panic / Recover

When an unhandled exception escapes the main execution loop, the interpreter enters a **panic** state: it preserves the exception (`_panic_exc`), the current pointer position, and all stack state so that the crash site can be inspected and execution can be resumed.

This is distinct from the `Try`/`CATCH` mechanism:

| Aspect          | Try-Catch                                | Panic / Recover                                                 |
| --------------- | ---------------------------------------- | --------------------------------------------------------------- |
| **Scope**       | Local, predictable business errors       | Global, unexpected crashes                                      |
| **Overhead**    | Low (instruction-level interception)     | High (preserves full interpreter state)                         |
| **After crash** | CATCH block handles, execution continues | Interpreter dumps, retains crash site                           |
| **Recovery**    | Automatic inside CATCH                   | Call `run()` / `run_step_by()` again to resume from crash point |
| **Use case**    | Node-level retry, fallback, rollback     | Debugging, audit, post-crash continuation                       |

To recover from a panic, simply call `run()` (or `run_step_by()`) again on the same interpreter — the pointer is still at the crash location, and execution will resume from there. The interpreter logs "Recovered from panic" and clears `_panic_exc` on the next run.

### Key attributes

- `_graph`: The compiled workflow graph being executed.
- `_pointer`: Current `PointerVector` execution address.
- `_ret_addr_stack`: Return address stack for subroutine calls.
- `_flags`: The status register — a `Flags` `IntFlag` holding the `IF`, `HLT` and `JMP` bits.
- `_interpret_lock`: Async lock used to guarantee one-node-at-a-time execution.
- `_context_stack`: LIFO stack of `InterpreterContext` snapshots used by PUSH_CONTEXT/POP_CONTEXT and INT/IRET.
- `object_io`: External I/O stream used for suspend/resume and streaming output.

### Interpreter Tree

Interpreters form a tree: a top-level interpreter may have child interpreters created via `fork_interpreter()`, and those children may have their own children.

`id: str` — Unique UUID string identifying this interpreter instance.

`parent: WorkflowInterpreter | None` — The parent interpreter, or `None` if this is the top-level interpreter.

`top_interpreter: WorkflowInterpreter` — The root of the interpreter tree.

`sub_interpreters: dict[str, WorkflowInterpreter]` — Dict of direct child interpreters, keyed by their IDs.

`all_sub_interpreters: dict[str, WorkflowInterpreter]` — (Top-level only) All descendant interpreters in the entire tree.

`is_running: bool` — `True` if the interpreter's main loop is currently executing. After the workflow completes (or terminates), returns `False`.

`pending_stop: bool` — `True` if `terminate()` has been called on this interpreter.

`outer_interpreting: bool` (read-only) — `True` while a subroutine call (`call_sub`) is executing. Set unconditionally at subroutine entry and restored to `False` in the `finally` block when the call returns. `INT` consults this flag to decide the default return address when `ret_to` is `None`: inside a call (flag `True`) it reuses the top of `_ret_addr_stack` (pushed by the parent), otherwise it uses the current pointer. `CALL` does not consult it: `from_adr=None` always resolves to the current pointer, so the pushed return address is the `CALL` node itself either way.

`wait: asyncio.Future[None]` — A future that resolves when the interpreter finishes execution. Raises `IllegalState` if the interpreter is not running.

`get_exception() -> Exception | None` — Return the last panic exception, or `None` if the interpreter finished normally or has never crashed. Available immediately after a panic for diagnostic purposes.

`_di_cache: DICache` — Internal DI result cache. Stores `(static_kwargs, non_cacheable_factories)` keyed by `hash((id(node.func), args_hash))` (the pointer position is not part of the key). The payload is an `LRUCache` with max 2048 entries. See `args_hash` and `args_hash_trustable` for cache invalidation.

`args_hash_trustable: bool` (read-only) — A cache-validity gate: returns `True` if the cached args hash is known to be valid. Set to `False` whenever `_ava_args` or `_ava_kwargs` are modified. Call `rehash_args()` to restore trust. While `False`, the LRU payload is neither read nor written.

`args_hash: int` (read-only) — Returns the current args hash used as part of the DI cache key. Computed by `_fingerprint_args()`.

`rehash_args() -> None` — Recompute the args hash from the current `_ava_args` and `_ava_kwargs`. Sets `hash_trustable = True`. If the new hash differs from the old value, the entire DI cache payload is cleared.

`_rslv_node(node, ava_args, ava_kwargs) -> dict[str, Any]` internal) — Resolve dependencies for a single node. Calls `MatcherFactory._resolve_dependencies()` and `MatcherFactory._do_runtime_resolve()` in sequence. Returns the resolved keyword arguments dictionary. Raises `DependsResolveFailed` or `DependsInjectFailed` on failure.

`_rslv_node_static(node, ava_args, ava_kwargs) -> tuple[dict[str, Any], dict[str, Any]]` internal) — Resolve static dependencies and `cacheable=True` factories for a node, returning `(static_kwargs, non_cacheable_factories)`. Used by `_call()` and the preload mechanism. `cacheable=False` factories are returned as-is and re-resolved on every call.

`_refresh_di_cache_full() -> None` internal) — Walk the entire workflow graph and pre-resolve DI for every node, storing `(static_kwargs, non_cacheable_factories)` results in `_di_cache` under key `hash((id(node.func), args_hash))`. Nodes are resolved in concurrent batches of size `WORKFLOW_DI_PRELOAD_BATCH`. Only called during `run()` initialization when `WORKFLOW_DI_PRELOAD_CACHE` is enabled. Raises `DependsResolveFailed` if `hash_trustable` is `False`.

### Important methods

#### `async run() -> None`

Execute the entire workflow to completion. This method internally iterates over `run_step_by()` and consumes all generated results.

#### `async run_step_by() -> AsyncGenerator[Any, None]`

Execute the workflow step by step, yielding the result of each node execution. This is the main entry point for external monitoring and cooperative suspension.

The generated sequence includes:

- waiting for `object_io` suspend signals at the global `WorkflowInterpreter::each_node` checkpoint
- acquiring `_interpret_lock`
- executing the current node via `_call()`
- advancing the pointer unless a jump was marked

#### `jump_to(addr: list[int])`

Perform an absolute jump to a new address. This sets the current pointer using a full `PointerVector` replacement.

#### `jump_near(addr: int)`

Replace the last dimension of the current pointer within the current scope.

#### `jump_offset(offset: int)`

Apply a relative offset to the current pointer position.

#### `jump_to_top(addr: int)`

Jump to an address at the top-level workflow.

#### `jump_offset_top(offset: int)`

Apply a relative offset at the top level and reset nested dimensions.

#### `jump_far_ptr(offset: list[int])`

Perform a multi-dimensional absolute jump. Replaces the entire `_pointer` with the given address vector via `far_to()`. This is a `@markup`-decorated jump — it sets `JMP` so the main loop does not advance afterwards, and clears `HLT`. Used by `CONTINUE` / `BREAK_LOOP` to jump back to the loop head or sentinel (not by `RET`, which uses `rebase_ptr` instead).

#### `jump_offset_far(offset: list[int])`

Apply a multi-dimensional offset to the current pointer position. Unlike `jump_offset()` which only adjusts the innermost dimension, this applies an offset vector across all nesting levels.

#### `async call_sub(addr, /, *extra_arg, interrupt: bool = False, **extra_kwargs)`

Call a subroutine at the specified address. It pushes the current pointer onto the return address stack, switches execution to the subroutine, and restores the pointer after the call.

- `interrupt=True` acquires the interpreter lock during the call, making it safe for external injection.
- `interrupt=False` is the normal internal call path.

While the subroutine executes, `outer_interpreting` is `True` — the flag is set unconditionally on entry and cleared in the `finally` block. It lets `INT` (with `ret_to = None`) resolve the default return address from the parent's stack entry; `CALL` (with `from_adr = None`) always resolves to the current pointer instead.

#### `async call_near(addr: int, *ag, interrupt: bool = False, **kw)`

Call a subroutine within the current scope using a relative near address.

#### `async call_offset(offset: int, *ag, interrupt: bool = False, **kw)`

Call a subroutine by applying a relative offset to the current pointer.

#### `async call_offset_far(offset: list[int], *ag, interrupt: bool = False, **kw)`

Call a subroutine at a multi-dimensional offset from the current position. Applies `offset_far()` to compute the target address, then delegates to `call_sub()`. Useful for invoking nodes across nested scopes.

#### `fork_interpreter(compose=None, middleware=UNSET, object_io=None) -> WorkflowInterpreter`

Create a child interpreter in the interpreter tree. By default inherits the parent's graph and middleware.

- `compose`: Optional rendered graph (`AbstractCompose[AddressCalculator]`, typically `NodeComposeRendered`) for the child. If `None`, uses the parent's graph.
- `middleware`: `UNSET` (inherit parent's), `None` (no middleware), or a custom callable.
- `object_io`: Optional `SuspendObjectStream`. If `None`, shares the parent's `object_io`. `SuspendObjectStream` is concurrency-safe via the CLCA signal design pattern.

#### `async terminate(eol: bool = True)`

Mark this interpreter for graceful stop. Sets `pending_stop = True` and awaits the `wait` future. If `eol=True`, removes the interpreter from the tree after termination.

#### `terminate_all_forks(eol: bool = True, exclude_self: bool = False) -> asyncio.Future`

Mark all direct child interpreters for termination. Returns a future that resolves when all children have terminated.

#### `async terminate_all(eol: bool = True, exclude_self: bool = False)`

Top-level only: mark this interpreter and all descendants for termination. Raises `IllegalState` if called on a non-top-level interpreter.

#### `async wait_all_forks(return_exc=False, exclude_self=False)`

Wait for all direct child interpreters to finish. If `return_exc=True`, returns a list of `BaseException | None`.

#### `async wait_all(return_exc=False, exclude_self=False)`

Top-level only: wait for the entire interpreter tree to finish. Raises `IllegalState` if called on a non-top-level interpreter.

#### `get_exception() -> Exception | None`

Return the last panic exception, or `None` if the interpreter finished normally or has never crashed. Useful for checking whether a previous `run()` crashed and what went wrong.

#### `reset()`

Reset the interpreter's execution state to its initial values: clear the pointer, return address stack, pending stop flag, waiter future, panic exception, context stack, and the entire status register. This is **independent of the recovery flow** — to recover from a panic, simply call `run()` again without resetting.

`reset()` is intended for scenarios where you want to restart execution from scratch on the same workflow graph without creating a new interpreter.

#### `get_graph() -> AbstractCompose[AddressCalculator]`

Return the rendered workflow graph being executed by this interpreter. The graph's `calc` property provides the `AddressCalculator` with methods `resolve_alias()`, `find_addr()`, `find_addr_safe()`, and `advance()`.

#### `flags` property

Returns the interpreter's status register.

**Type**: `Flags` — an `IntFlag` with three members:

| Bit   | Meaning                                                                |
| ----- | ---------------------------------------------------------------------- |
| `IF`  | Inside an interrupt handler; `INT` is rejected while set               |
| `HLT` | Halted on a node; the next run steps past it before executing anything |
| `JMP` | A jump already moved the pointer; the main loop must not advance it    |

#### `jump_marked` property

Whether the `JMP` bit is set.

**Type**: `bool`

#### `unmarkup() -> None`

Clear the `JMP` bit, so the main loop advances the pointer again.

#### `resume_from_halt() -> bool`

Clear `HLT` and advance the pointer past the node the interpreter halted on. Returns `False` when nothing follows. This is the single implementation shared by the main loop and the debugger's `step`, so stepping past a suspend behaves exactly like running past it.

#### `if_flag` property

Get or set the `IF` bit. The setter validates that the value is a boolean. When `True`, `INT` cannot be called (raises `IllegalState`).

**Type**: `bool`

#### `context_stack` property

Returns the interpreter's context stack — a `Stack[InterpreterContext]` used for save/restore workflows.

**Type**: `Stack[InterpreterContext]`

#### `dump_interpreter(exclude_deps=True, exclude_stack=True) -> InterpreterContext`

Export a complete snapshot of the current interpreter state. Used by `PUSH_CONTEXT` and `INT`. `HLT` is stripped from the exported `flags`: a snapshot records the state to come back to, and "the loop is parked on this node" is not part of it.

**Parameters**

- `exclude_deps`: If `True` (default), dependency args/kwargs are excluded from the snapshot.
- `exclude_stack`: If `True` (default), the return-address stack is excluded.

**Returns**: An `InterpreterContext` dataclass with `ptr`, `exception_ignored`, optional `s_args`/`s_kwargs`, optional `stack`, `extra`, `exception`, and `flags` fields.

#### `rebase_context(ctx: InterpreterContext) -> None`

Restore the interpreter state from an `InterpreterContext` snapshot. Sets the pointer, exception-ignore list, dependency args, return-address stack, panic exception, and status register from the context. Every bit the snapshot carries is restored as-is; `HLT` cannot reappear because `dump_interpreter` strips it when the snapshot is taken.

**Parameters**

- `ctx`: The `InterpreterContext` to restore from.

#### `find_node_alias(alias: str) -> BaseNode | AbstractCompose[AddressCalculator]`

Resolve an alias and return the corresponding node object.

#### `advance_pointer(ptr: PointerVector | None = None) -> bool`

Advance the execution pointer to the next node in the workflow graph. This method delegates to `AddressCalculator.advance()` on the compiled graph. It handles navigation through nested workflow structures, supporting both sequential execution and hierarchical traversal.

**Parameters**

- `ptr`: Optional external pointer vector to advance. When provided, the method advances this pointer **without modifying the interpreter's own `_pointer`**. Defaults to `None`, in which case `self._pointer` is advanced. This enables external systems to preview pointer advancement paths without disturbing interpreter state.

**Returns**

- `True` if the pointer was successfully advanced to the next node.
- `False` if the end of the workflow has been reached.

**Algorithm**

1. Starting from `ptr` (or `self._pointer`), traverse `base_addr` layer-by-layer to locate the container of the current node.
2. If the current node is a **non-empty rendered composition** (an `AbstractCompose`) -> enter the nested container (`append(0)`), return `True`.
3. If the current node has a **next sibling**:
   - Sibling is a non-empty rendered composition -> enter that nested container, return `True`.
   - Otherwise -> move to the sibling node, return `True`.
4. If no next sibling -> **backtrack up** the pointer stack layer-by-layer, looking for a parent container's next sibling.
5. If a next sibling is found during backtracking -> apply the same logic, return `True`.
6. If backtracking reaches the top level with no more siblings -> return `False` (end of workflow).

### Execution behavior

`WorkflowInterpreter` preserves execution atomicity by holding `_interpret_lock` while a single node is executed. It only checks suspend points at safe boundaries:

- before each node execution via the global checkpoint `WorkflowInterpreter::each_node`
- before each individual node via the node’s tag

The `object_io` implementation is responsible for coordinating suspension and resumption.

### Example

```python
from amrita_sense.node.core import Node
from amrita_sense.runtime.workflow import WorkflowInterpreter


@Node()
async def a():
    return 1


@Node()
async def b():
    return 2


compose = a >> b
rendered = compose.render()
pc = WorkflowInterpreter(rendered)
await pc.run()
```

::: tip REPL Debugger
AmritaSense ships a dedicated `amrita_sense.debugger` module that wraps step-by-step execution, state inspection, and breakpoint management into a complete debugging experience — no manual `run_step_by()` loops required. Import everything with `from amrita_sense.debugger import *`; all functions are callable synchronously in a REPL (no `await` needed). See [REPL Debugging](/guide/practice/repl-debugging) for details.
:::
