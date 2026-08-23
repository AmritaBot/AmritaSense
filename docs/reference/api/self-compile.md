# Self-Compile Instructions

Self-compile instructions are the core mechanism through which AmritaSense implements high-level control flow. They automatically expand into standard low-level node compositions during the workflow rendering phase, allowing developers to use their own encapsulated complex composition patterns just like built-in instructions.

## SelfCompileInstruction

```python
class SelfCompileInstruction(ABC):
    """Abstract base class for all self-compiling instructions.

    Self-compiling instructions are expanded into NodeCompose structures during
    the workflow rendering phase. This allows for compile-time optimization
    and static address calculation without requiring changes to the interpreter.
    """
```

`SelfCompileInstruction` is the abstract base class for all self-compiling instructions. Its single core responsibility is to map high-level semantics to low-level node compositions. This mapping occurs during the `render()` phase, so all address calculations and structural expansion happen before execution, leaving zero runtime overhead.

**Core methods**

- `extract() -> NodeCompose`: Expands the instruction into a low-level node composition. Must return a `NodeCompose` instance, which the framework will recursively render automatically.
- `__rshift__(other) -> NodeCompose`: Supports the `>>` operator so that self-compile instructions can be composed directly with regular nodes. Syntactic sugar: `instruction >> node` is equivalent to `NodeCompose(instruction, node)`.

**Design philosophy**

Self-compile instructions are the cornerstone of AmritaSense's extensibility. Built-in instructions like `IF`, `WHILE`, and `TRY` all implement this interface, and developers can create their own control flow primitives by subclassing it — encapsulating **composition patterns**, not concrete business logic.

## Built-in Self-Compile Instructions

All of AmritaSense's built-in instructions are subclasses of `SelfCompileInstruction`. The following lists only their compile-time expansion structure; for detailed syntax and runtime behavior, see Section 4.5: Built-in Instruction Set.

### Conditional branching instructions

- `IFClause`: `IF(cond, do)` → `[ConditionJumpNode, condition, do, NOP]`
- `ELIFClause`: Extends `IFClause` with an ELIF chain. Each ELIF appends a `[ConditionJumpNode, condition, do]` group; the final `NOP` serves as the unified exit.
- `ELSEClause`: Appends `[ELSENode, else_do, NOP]` after an IF or IF-ELIF chain.

### Loop instructions

- `WhileClause`: `WHILE(condition).ACTION(action)` → `[WhileNode, condition, action, CheckUpNode, NOP]`
- `DoWhileClause`: `DO(do).WHILE(condition)` → `[DONode, do, DowhileNode, condition, NOP]`

### Exception handling instructions

- `TryClause`: Expands to `[TryNode, try_body, ...catch_handler_i, catch_body_i..., FinNode(optional), fin_body, NOP]`. `TryNode` manages the runtime logic of the entire exception handling chain.

### Subprogram storage instructions

- `SubprogramStorage` (the underlying implementation of `ARCHIVED_NODES`): Expands to `[SubprogramJumpNode, node_1, node_2, ..., NOP]`. Accepts arbitrary `BaseNode` instances (not limited to `ALIAS`). `SubprogramJumpNode` unconditionally skips the entire storage block during normal execution. Internal nodes can be accessed via `CALL` or `GOTO` (if tagged with `ALIAS`).
- `ARCHIVED_SEGMENT`: A `NodeCompose` wrapper (`[JMP 2, Payload, NOP]`) for archiving a full node composition as a skip-over segment. It is the building block for `FN` / `INTER_FN` function blocks — see [Function Block Call](../guide/advanced/function-block-call) for the modern call patterns.

### Note: CALL is not a self-compile instruction

The `CallNode` corresponding to the `CALL` instruction inherits directly from `BaseNode` — it is a **regular node**. It does not expand at compile time but exists as a single node in the workflow array. Aliases are resolved at compile time via `_post_compile`, and the call is executed at runtime via `pc.call_sub`. This is consistent with the design of `GOTO` (`JumpNode`) — both are "atomic" jump nodes rather than self-compiling structures.

## Custom Self-Compile Instructions

### Implementation steps

1. **Subclass `SelfCompileInstruction`**
2. **Accept construction parameters in `__init__`**: These parameters determine how the node composition will expand.
3. **Implement `extract() -> NodeCompose`**: Perform all address calculation and node assembly inside this method; return the final `NodeCompose`.

### Simple example

```python
class LoggedNode(SelfCompileInstruction):
    """Add a log message before and after a node's execution."""

    def __init__(self, node: BaseNode, name: str):
        self._node = node
        self._name = name

    def extract(self) -> NodeCompose:
        @Node()
        def log_start():
            print(f"[{self._name}] start")

        @Node()
        def log_end():
            print(f"[{self._name}] done")

        return NodeCompose(log_start, self._node, log_end)
```

Usage: `LoggedNode(process_data, "data processing")` is equivalent to writing `log_start >> process_data >> log_end` by hand.

### Design principles

**Compile-time vs. runtime**

- **Compile-time**: Address calculation, structure expansion, and static optimization all happen inside `extract()`. All jump offsets are finalized during this phase.
- **Runtime**: The expanded regular nodes are executed normally by the interpreter with no additional compilation overhead.

**Address calculation strategy**

- If the expanded structure contains jumps (e.g., `ConditionJumpNode`), address offsets must be statically calculated inside `extract()` based on the length of the node list.
- If the expanded structure reuses built-in instructions like `IF` or `WHILE`, address calculation is handled by those instructions automatically — no manual management required.

**Encapsulate patterns, not logic**

Custom instructions should encapsulate recurring **composition patterns** (such as retry, timeout, conditional execution), not concrete business logic. Business logic should remain inside node functions.

**Error handling**

- Validate parameters in `__init__`; fail early.
- Exceptions raised inside `extract()` will prevent workflow rendering.

**Composability**

Custom instructions can contain other self-compile instructions (including built-in ones) with no nesting depth limit.
