# Runtime System

The runtime system executes compiled workflow graphs, manages the program counter, handles call stacks, and performs dependency injection at node execution time. `WorkflowInterpreter` is the core execution engine in AmritaSense and is designed for step-by-step interpretation rather than bulk graph traversal.

## WorkflowInterpreter

```python
class WorkflowInterpreter(Generic[io_T]):
    ...
```

`WorkflowInterpreter` is the main engine for executing a rendered workflow graph. It tracks the current execution pointer using `PointerVector`, manages subroutine calls through a return address stack, and supports external interruption and streaming via a generic `object_io` interface.

### Constructor

```python
WorkflowInterpreter(
    node_compose: NodeComposeRendered | SelfCompileInstruction,
    object_io: SuspendObjectStream[Any] | None = None,
    *,
    exception_ignored: tuple[type[BaseException], ...] = (),
    extra_args: tuple = (),
    extra_kwargs: dict[str, Any] | None = None,
    addr_stack: Stack[PointerVector] | None = None,
    middleware: Callable[['WorkflowInterpreter'], Awaitable[Any]] | None = None,
)
```

Arguments:

- `node_compose`: A rendered workflow graph or a self-compiling instruction.
- `object_io`: Optional external I/O object. Defaults to a new `SuspendObjectStream`.
- `exception_ignored`: Exception types to bypass TRY/CATCH blocks.
- `extra_args` / `extra_kwargs`: Additional runtime values available for dependency injection.
- `addr_stack`: Optional return address stack.
- `middleware`: Optional async callable that receives the `WorkflowInterpreter` instance. When set, `run_step_by()` and `call_sub()` delegate to the middleware instead of calling nodes directly. The middleware can decide whether and how to execute nodes, transform results, or inject custom logic around every step.

### Key attributes

- `_graph`: The compiled workflow graph being executed.
- `_pointer`: Current `PointerVector` execution address.
- `_ret_addr_stack`: Return address stack for subroutine calls.
- `_jump_marked`: Flag indicating whether a jump operation occurred.
- `_interpret_lock`: Async lock used to guarantee one-node-at-a-time execution.
- `object_io`: External I/O stream used for suspend/resume and streaming output.

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

Perform a multi-dimensional absolute jump. Replaces the entire `_pointer` with the given address vector via `far_to()`. Used by `RET_FAR` to return from nested scopes.

#### `jump_offset_far(offset: list[int])`

Apply a multi-dimensional offset to the current pointer position. Unlike `jump_offset()` which only adjusts the innermost dimension, this applies an offset vector across all nesting levels.

#### `async call_sub(addr, /, *extra_arg, interrupt: bool = False, **extra_kwargs)`

Call a subroutine at the specified address. It pushes the current pointer onto the return address stack, switches execution to the subroutine, and restores the pointer after the call.

- `interrupt=True` acquires the interpreter lock during the call, making it safe for external injection.
- `interrupt=False` is the normal internal call path.

#### `async call_near(addr: int, *ag, interrupt: bool = False, **kw)`

Call a subroutine within the current scope using a relative near address.

#### `async call_offset(offset: int, *ag, interrupt: bool = False, **kw)`

Call a subroutine by applying a relative offset to the current pointer.

#### `async call_offset_far(offset: list[int], *ag, interrupt: bool = False, **kw)`

Call a subroutine at a multi-dimensional offset from the current position. Applies `offset_far()` to compute the target address, then delegates to `call_sub()`. Useful for invoking nodes across nested scopes.

#### `find_addr_alias(alias: str) -> list[int]`

Resolve an alias to its absolute address vector. Raises `NullPointerException` if the alias does not exist.

#### `find_addr(addr: list[int]) -> BaseNode | NodeComposeRendered`

Find a node or rendered composition by absolute address.

#### `find_node_alias(alias: str) -> BaseNode | NodeComposeRendered`

Resolve an alias and return the corresponding node object.

#### `advance_pointer(ptr: PointerVector | None = None) -> bool`

Advance the execution pointer to the next node in the workflow graph. This method implements the logic for navigating through nested workflow structures, handling both sequential execution and hierarchical traversal.

**Parameters**

- `ptr`: Optional external pointer vector to advance. When provided, the method advances this pointer **without modifying the interpreter's own `_pointer`**. Defaults to `None`, in which case `self._pointer` is advanced. This enables external systems to preview pointer advancement paths without disturbing interpreter state.

**Returns**

- `True` if the pointer was successfully advanced to the next node.
- `False` if the end of the workflow has been reached.

**Algorithm**

1. Starting from `ptr` (or `self._pointer`), traverse `base_addr` layer-by-layer to locate the container of the current node.
2. If the current node is a **non-empty `NodeComposeRendered`** → enter the nested container (`append(0)`), return `True`.
3. If the current node has a **next sibling**:
   - Sibling is a non-empty `NodeComposeRendered` → enter that nested container, return `True`.
   - Otherwise → move to the sibling node, return `True`.
4. If no next sibling → **backtrack up** the pointer stack layer-by-layer, looking for a parent container's next sibling.
5. If a next sibling is found during backtracking → apply the same logic, return `True`.
6. If backtracking reaches the top level with no more siblings → return `False` (end of workflow).

**Deprecation**

The `_advance_pointer` property is deprecated since v0.3.0. Use `advance_pointer()` instead. The old property exists only as a compatibility shim and will be removed in a future version.

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
