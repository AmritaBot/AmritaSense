# Custom Instruction Set

AmritaSense’s built-in instruction set already covers core control flow such as conditionals, loops, and exception handling. But when those basic instructions repeatedly appear in fixed patterns, you can encapsulate them as **new instructions** with `SelfCompileInstruction`. This extension does not modify the interpreter; it only expands into standard node compositions at compile time, and at runtime it behaves exactly like built-in instructions.

---

## 4.7.1 Selfcompiled instruction interface: `SelfCompileInstruction`

`SelfCompileInstruction` is an abstract base class that defines the unified entry for all self-compiled instructions:

```python
from abc import ABC, abstractmethod
from amrita_sense.node.core import NodeCompose

class SelfCompileInstruction(ABC):
    @abstractmethod
    def extract(self) -> NodeCompose:
        """Expand the custom instruction into a lower-level node composition."""
        pass
```

### Core concepts

- **Compile-time expansion**: `extract()` is called during the `render()` phase, not at runtime. The returned `NodeCompose` is recursively rendered, producing the same `NodeComposeRendered` output as a hand-written composition.
- **Transparency**: other workflow parts see custom instructions the same way they see built-in instructions. They share the same alias system and addressing mechanism.
- **Composability**: custom instructions can contain other instructions, including other custom instructions, with no nesting depth limit.

### Implementation requirements

1. Implement `extract()`.
2. `extract()` may only depend on information available at compile time (constructor parameters).
3. If the expanded structure includes jumps, address calculation must be handled inside `extract()`.
4. The returned `NodeCompose` is automatically rendered; you do not need to call `render()` manually.

---

## 4.7.2 Implementation pattern: `extract()` and address calculation

The core task in implementing a custom instruction is mapping an “intention” to a concrete sequence of nodes. This mapping involves three steps:

### Step 1: determine the node list

Decompose the instruction’s semantics into a concrete node sequence. For example, a retry instruction can be broken down into: execute target node → check result → if failure and retry count remains, jump back → otherwise continue.

### Step 2: calculate jump addresses

If the expanded structure contains jumps (`GOTO`, `ConditionJumpNode`, etc.), calculate offsets based on the node list length inside `extract()`. All addresses must be statically determinable integers.

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

---

## 4.7.3 Example 1: retry wrapper

Wrapping a potentially failing node with retry logic is a typical use case for self-compiled instructions.

### Requirement

- execute the target node
- if the node raises an exception, retry
- if the maximum retry count is exceeded, raise the final exception or execute a fallback node

### Implementation

```python
from amrita_sense.instructions import IF, TRY
from amrita_sense.exceptions import BreakLoop

class RetryClause(SelfCompileInstruction):
    def __init__(self, node: BaseNode, max_retries: int = 3, fallback: BaseNode | None = None):
        self._node = node
        self._max = max_retries
        self._fallback = fallback

    def extract(self) -> NodeCompose:
        @Node()
        def attempt():
            pass  # placeholder; self._node will be executed inside the TRY block

        @Node()
        def on_error():
            nonlocal retries
            retries += 1
            if retries >= self._max:
                raise BreakLoop

        retries = 0

        retry_body = TRY(self._node).CATCH(Exception, on_error)

        if self._fallback:
            return NodeCompose(
                WHILE(lambda: retries < self._max).ACTION(retry_body),
                self._fallback,
                NOP
            )
        else:
            return NodeCompose(
                WHILE(lambda: retries < self._max).ACTION(retry_body),
                NOP
            )
```

Usage:

```python
RetryClause(call_api, max_retries=3, fallback=use_cache)
```

This expands into:

```python
WHILE(lambda: retries < self._max).ACTION(TRY(call_api).CATCH(Exception, on_error)) >> use_cache >> NOP
```

### Key points

- `extract()` uses built-in instructions `WHILE` and `TRY`, demonstrating the composability of custom instructions.
- Jump addresses are handled by the built-in instructions, so `RetryClause` does not need to manage offsets manually.
- Users see only `RetryClause(...)`, while the expansion remains transparent.

---

## 4.7.4 Example 2: conditional execution wrapper

Encapsulate the common pattern “execute a node when a condition is true, otherwise skip it” as a single instruction.

### Implementation

```python
class ExecuteWhen(SelfCompileInstruction):
    def __init__(self, condition: Node[bool], action: BaseNode):
        self._cond = condition
        self._action = action

    def extract(self) -> NodeCompose:
        return NodeCompose(
            IF(self._cond, self._action).ELSE(NOP)
        )


# Usage:

ExecuteWhen(has_data, process_data)
```

This is equivalent to `IF(has_data, process_data).ELSE(NOP)`, but the semantic intent is clearer: “execute when the condition is met.”

### Extended version with else branch

```python
class ExecuteWhenElse(SelfCompileInstruction):
    def __init__(self, condition: Node[bool], action: BaseNode, otherwise: BaseNode):
        self._cond = condition
        self._action = action
        self._other = otherwise

    def extract(self) -> NodeCompose:
        return NodeCompose(
            IF(self._cond, self._action).ELSE(self._other)
        )
```

---

## Design principles for custom instructions

1. **Encapsulate patterns, not logic**: custom instructions should encapsulate recurring composition patterns (retry, conditional execution, timeout protection), not concrete business logic. Business logic belongs inside nodes.
2. **Leverage existing instructions**: prefer composing built-in primitives like `IF`, `WHILE`, and `TRY` rather than manually managing jump offsets. Only calculate addresses manually when built-in instructions cannot express the needed flow.
3. **Keep it transparent**: the expanded structure should match a hand-written composition and should not break debugging, suspension, or interruption behavior.
4. **Use semantic naming**: instruction names should convey the control flow intent clearly (for example, `Retry`, `Timeout`, `Parallel`), so the composition reads like natural language.
