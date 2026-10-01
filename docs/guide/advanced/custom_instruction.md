# Custom Instruction Set

AmritaSense’s built-in instruction set already covers core control flow such as conditionals, loops, and exception handling. But when those basic instructions repeatedly appear in fixed patterns, you can encapsulate them as **new instructions** with `SelfCompileInstruction`. This extension does not modify the interpreter; it only expands into standard node compositions at compile time, and at runtime it behaves exactly like built-in instructions.

## Selfcompiled instruction interface: `SelfCompileInstruction`

`SelfCompileInstruction` is an abstract base class that defines the unified entry for all self-compiled instructions:

```python
from abc import ABC, abstractmethod
from amrita_sense.node.abc_base import AbstractComposeOriginal


class SelfCompileInstruction(ABC):
    @abstractmethod
    def extract(self) -> AbstractComposeOriginal:
        """Expand the custom instruction into a lower-level node composition."""
        pass
```

The contract only says "return _some_ source composition" (`AbstractComposeOriginal`). In practice your `extract()` returns the default implementation `NodeCompose` — the framework recursively renders whatever composition you hand back, exactly as it does for hand-written graphs.

### Core concepts

- **Compile-time expansion**: `extract()` is called during the `render()` phase, not at runtime. The returned `NodeCompose` is recursively rendered, producing the same `NodeComposeRendered` output as a hand-written composition.
- **Transparency**: other workflow parts see custom instructions the same way they see built-in instructions. They share the same alias system and addressing mechanism.
- **Composability**: custom instructions can contain other instructions, including other custom instructions, with no nesting depth limit.

### Implementation requirements

1. Implement `extract()`.
2. `extract()` may only depend on information available at compile time (constructor parameters).
3. If the expanded structure includes jumps, address calculation must be handled inside `extract()`.
4. The returned `NodeCompose` is automatically rendered; you do not need to call `render()` manually.

## Implementation pattern: `extract()` and address calculation

The core task in implementing a custom instruction is mapping an “intention” to a concrete sequence of nodes. This mapping involves three steps:

### Step 1: determine the node list

Decompose the instruction’s semantics into a concrete node sequence. For example, a retry instruction can be broken down into: execute target node -> check result -> if failure and retry count remains, jump back -> otherwise continue.

### Step 2: calculate jump addresses

If the expanded structure contains jumps (`JMP`, `ConditionJumpNode`, etc.), calculate offsets based on the node list length inside `extract()`. All addresses must be statically determinable integers.

### Step 3: return `NodeCompose`

Wrap the node sequence in `NodeCompose` and return it. The framework will handle recursive rendering.

### Simple example: logged node wrapper

```python
class LoggedNode(SelfCompileInstruction):
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

Usage:

```python
workflow = start >> LoggedNode(process_data, "data") >> end
```

This is equivalent to writing:

```python
workflow = start >> log_start >> process_data >> log_end >> end
```

## Example 1: retry wrapper

Wrapping a potentially failing node with retry logic is a typical use case for self-compiled instructions.

### Requirement

- execute the target node
- if the node raises an exception, retry
- if the maximum retry count is exceeded, execute a fallback node

### Implementation

```python
from amrita_sense.instructions import IF, NATIVE_WHILE, Try


class RetryClause(SelfCompileInstruction):
    def __init__(
        self, node: BaseNode, max_retries: int = 3, fallback: BaseNode | None = None
    ):
        self._node = node
        self._max = max_retries
        self._fallback = fallback

    def extract(self) -> NodeCompose:
        retries = 0
        ok = False

        @Node()
        def under_max() -> bool:
            return not ok and retries < self._max

        @Node()
        def on_error() -> None:
            nonlocal retries
            retries += 1

        @Node()
        def on_success() -> None:
            nonlocal ok
            ok = True

        @Node()
        def failed() -> bool:
            return not ok

        # The body is a composition, so the loop must be NATIVE_WHILE (WHILE takes one node).
        body = Try(self._node).CATCH(Exception, on_error).THEN(on_success)
        loop = NATIVE_WHILE(under_max).ACTION(body)

        if self._fallback is not None:
            return loop >> IF(failed, self._fallback)
        return loop.extract()
```

Usage:

```python
RetryClause(call_api, max_retries=3, fallback=use_cache)
```

### Key points

- The loop body is a **composition** — `Try(...).CATCH(...).THEN(...)` — so the loop must be `NATIVE_WHILE`. The `call_sub`-based `WHILE` accepts a **single node** only; see [single-node loop body](/guide/advanced/built-in_instruction_set/while_clause#single-node-loop-body).
- Native loops wrap no `try/except` around the body, so the loop exits through its **condition** instead of `BreakLoop`: `under_max` turns false as soon as `on_success` sets `ok`, or `on_error` exhausts the retry budget.
- `IF(failed, ...)` runs the fallback only when every attempt failed.
- Jump addresses are handled by the built-in instructions, so `RetryClause` does not need to manage offsets manually.
- Users see only `RetryClause(...)`, while the expansion remains transparent.

## Example 2: conditional execution wrapper

Encapsulate the common pattern “execute a node when a condition is true, otherwise skip it” as a single instruction.

### Implementation

```python
class ExecuteWhen(SelfCompileInstruction):
    def __init__(self, condition: Node[bool], action: BaseNode):
        self._cond = condition
        self._action = action

    def extract(self) -> NodeCompose:
        # IF without ELSE is perfectly valid — when the condition is false
        # the branch simply falls through. No ELSE(NOP) needed.
        return IF(self._cond, self._action).extract()


# Usage:

ExecuteWhen(has_data, process_data)
```

This is equivalent to `IF(has_data, process_data)` — when the condition is false the workflow just skips the action (no `ELSE(NOP)` needed).

### Extended version with else branch

```python
class ExecuteWhenElse(SelfCompileInstruction):
    def __init__(self, condition: Node[bool], action: BaseNode, otherwise: BaseNode):
        self._cond = condition
        self._action = action
        self._other = otherwise

    def extract(self) -> NodeCompose:
        return NodeCompose(IF(self._cond, self._action).ELSE(self._other))
```

## Disassembly annotation: `__sdb_dis__` / `__sdb_cmt__`

A custom instruction expands into nodes the user never wrote, so a debugger listing shows framework internals by default. A node can describe its own line with two **soft-constraint magic attributes** read by the REPL debugger's disassembler:

| Attribute     | Effect                                                                         |
| ------------- | ------------------------------------------------------------------------------ |
| `__sdb_dis__` | The mnemonic shown in the instruction column.                                  |
| `__sdb_cmt__` | When not `None`, overrides the comment after `;` (defaults to the node `tag`). |

Both are read through a plain `getattr` at disassembly time — the input is an _already compiled_ graph, so an operand such as a jump target is resolved by then. Prefer a `@property` when the value depends on compilation: it re-reads instance state on every listing, so nothing has to be re-assigned after a recompile.

```python
class RetryJump(BaseNode):
    """Jump back to the body while the counter is below the limit."""

    __sdb_cmt__ = "retry back-edge"

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._body: list[int] = []
        self._init(self.__call__, tag=None, wrap_to_async=False, address_able=True)

    @property
    def __sdb_dis__(self) -> str:
        #  re-read every listing, so a recompile needs no re-assignment step
        return f"RETRY {self._limit} -> {self._body or '?'}"

    def __call__(self, pc: WorkflowInterpreter) -> None: ...

    def _post_compile(self, compose: NodeComposeRendered) -> None:
        #  operands are resolved here — the property picks the value up for free
        self._body = compose.calc.resolve_alias("body")
```

Four details are worth remembering:

- A `@property` is a data descriptor, so the node rejects `self.__sdb_dis__ = ...` — that is what keeps the value single-sourced. Use a class attribute for a fixed mnemonic, or an instance attribute when the operand only exists inside a closure (`PUSH_RET`, `INT`, …).
- Neither name is subject to name mangling (two trailing underscores), so `self.__sdb_dis__ = ...` inside a class body is safe.
- `_post_compile` runs again after every DLL `apply()` rebase, and a property picks up the new operand automatically — so a mnemonic that embeds an address stays correct when the slot is relinked.
- A node never knows its own address, so an operand relative to its own segment must be written as `#N` (a `near_to` slot) or `+N` (an `offset` delta) instead of a full address.

See [REPL Debugging](../practice/repl-debugging#disassembly-view) for the listing format and the mnemonics the built-in instruction set declares.

## Design principles for custom instructions

1. **Encapsulate patterns, not logic**: custom instructions should encapsulate recurring composition patterns (retry, conditional execution, timeout protection), not concrete business logic. Business logic belongs inside nodes.
2. **Leverage existing instructions**: prefer composing built-in primitives like `IF`, `WHILE`, and `TRY` rather than manually managing jump offsets. Only calculate addresses manually when built-in instructions cannot express the needed flow.
3. **Keep it transparent**: the expanded structure should match a hand-written composition and should not break debugging, suspension, or interruption behavior.
4. **Use semantic naming**: instruction names should convey the control flow intent clearly (for example, `Retry`, `Timeout`, `Parallel`), so the composition reads like natural language.
5. **Annotate the mnemonic**: give your node a `__sdb_dis__` so a debugger listing shows `RETRY 3 -> [1, 0]` instead of an anonymous internal node — custom instructions are exactly the ones that most need it.
