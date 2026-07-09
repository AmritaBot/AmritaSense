# WHILE & DO-WHILE Loops

AmritaSense provides two standard loop paradigms: `WHILE` (check before executing) and `DO-WHILE` (execute before checking). Both are `SelfCompileInstruction` and expand at compile time into a fixed structure containing jump nodes. At runtime, the loop semantics are implemented entirely through pointer offsets and `jump_near`, without any external state flags.

## Compile-time expansion structure

### WHILE loop

`WHILE(condition).ACTION(action)` expands at compile time to:

```text
[WhileNode, condition, action, CheckUpNode, NOP]
```

| Position | Node          | Responsibility                                   |
| -------- | ------------- | ------------------------------------------------ |
| index 0  | `WhileNode`   | call the condition and decide whether to enter   |
| index 1  | `condition`   | condition node returning `bool`                  |
| index 2  | `action`      | loop body                                        |
| index 3  | `CheckUpNode` | unconditional jump back to `WhileNode`           |
| index 4  | `NOP`         | loop exit; continue from here after leaving loop |

### DO-WHILE loop

`DO(do_node).WHILE(condition)` expands at compile time to:

```text
[DONode, do_node, DowhileNode, condition, NOP]
```

| Position | Node          | Responsibility                                  |
| -------- | ------------- | ----------------------------------------------- |
| index 0  | `DONode`      | execute loop body first, then jump to condition |
| index 1  | `do_node`     | loop body node (executes at least once)         |
| index 2  | `DowhileNode` | call the condition and decide whether to loop   |
| index 3  | `condition`   | condition node returning `bool`                 |
| index 4  | `NOP`         | loop exit                                       |

> **Key difference**
> WHILE checks the condition before the loop body; DO-WHILE executes the loop body before the condition. Both use `NOP` as the unified loop exit.

## Runtime execution flow

### WHILE

1. `WhileNode` executes: it calls the `condition` node using `call_offset`.
2. If the condition is `False`: `WhileNode` jumps to `NOP` and the loop ends.
3. If the condition is `True`: `WhileNode` calls the `action` node using `call_offset`.
4. After `action` completes, the interpreter advances to `CheckUpNode`.
5. `CheckUpNode` unconditionally jumps back to `WhileNode` to begin the next iteration.

### DO-WHILE

1. `DONode` executes: it calls `do_node` first using `call_offset`.
2. After `do_node` completes, the interpreter advances to `DowhileNode`.
3. `DowhileNode` calls `condition` using `call_offset`.
4. If the condition is `True`: `DowhileNode` jumps back to `DONode` and repeats the body.
5. If the condition is `False`: `DowhileNode` jumps to `NOP` and exits the loop.

### Breaking out of the loop: `BreakLoop`

Within `action` or `do_node`, you can `raise BreakLoop` to implement `break` semantics.

`BreakLoop` is automatically added to `_exc_ignored` during interpreter initialization, so:

- it will not be caught by any inner `TRY/CATCH`
- it will directly propagate to the outer `WhileNode` or `DONode`
- `WhileNode` and `DONode` catch it and jump to `NOP` to exit cleanly

### Equivalent of `continue`

Returning early from `action` or `do_node` ends the current node execution. The interpreter then naturally advances to `CheckUpNode` (for `WHILE`) or `DowhileNode` (for `DO-WHILE`), starting the next iteration. This behavior is equivalent to `continue`.

## `GOTO` restrictions inside loops

The compile-time structure of `WHILE` and `DO-WHILE` is fixed. `WhileNode` and `DONode` rely on `call_offset` and `jump_near` relative offsets to perform condition checks and body execution.

If a `GOTO` inside the loop body jumps outside the loop structure:

- the call stack and return address may not be cleaned correctly
- `WhileNode` or `DONode` cannot properly catch `BreakLoop`
- the interpreter may enter unpredictable states

Therefore, **do not use `GOTO` to jump out of a loop**. Use `BreakLoop` to exit the loop, and use `CALL` for reusable subroutine execution.

## Usage example

```python
from amrita_sense.instructions import WHILE, DO
from amrita_sense.exceptions import BreakLoop
from amrita_sense.node import Node

@Node()
def has_more() -> bool:
    return len(queue) > 0

@Node()
def process_one():
    item = queue.pop(0)
    if item == "stop":
        raise BreakLoop
    if item == "skip":
        return
    handle(item)

# WHILE: check before executing
loop = WHILE(has_more).ACTION(process_one)

# DO-WHILE: execute at least once
@Node()
def fetch():
    data = request()
    if data is None:
        raise BreakLoop
    store(data)

retry = DO(fetch).WHILE(has_more)
```

## Squashed Loop Mode (v0.4.3+)

By default, `WHILE` and `DO-WHILE` loops use a **stepping** execution model: the interpreter advances through `WhileNode`/`DONode` → condition → action → `CheckUpNode`/`DowhileNode` one node at a time, with each step going through the full `run_step_by()` cycle (pointer advance, lock acquire/release, jump operations).

Setting `__flags__.SQUASHED_LOOP = True` switches to **squashed** execution: the entire loop runs as a native Python `while` loop inside a single interpreter step.

### How it works

In squashed mode, `WhileNode._while_worker()` and `DONode._do_worker()` are replaced with equivalent logic:

**WHILE squashed:**

```python
while await pc.call_offset(self._condi_offset):
    await pc.call_offset(self._do_offset)
    if pc._jump_marked:
        break
pc.jump_near(self._else_addr)
```

**DO-WHILE squashed:**

```python
try:
    while True:
        await pc.call_offset(self._do_offset)
        if ptr.jump_marked:
            return
        if not await ptr.call_sub(condi_addr):
            return ptr.jump_near(self._break_addr)
except BreakLoop:
    return ptr.jump_near(self._break_addr)
```

### Comparison

| Aspect                 | Normal (stepping)                          | Squashed                                   |
| ---------------------- | ------------------------------------------ | ------------------------------------------ |
| **Pointer operations** | Multiple per iteration (enter, exit, jump) | One per iteration (the body `call_offset`) |
| **Lock acquire**       | Per sub-step (condition, body, jump)       | Once for the entire loop                   |
| **External interrupt** | Possible between any sub-step              | Only at body boundaries (`call_offset`)    |
| **`BreakLoop`**        | Caught by WhileNode/DONode                 | Caught by native except                    |
| **Performance**        | Baseline                                   | Lower overhead per iteration               |

### When to use

| Scenario                                              | Recommended Mode |
| ----------------------------------------------------- | ---------------- |
| Need precise external interruption within a loop step | **Normal**       |
| Hot inner loops with many iterations                  | **Squashed**     |
| Compatibility with `GOTO` jumping outside the loop    | **Normal**       |
| Maximum throughput for tight loops                    | **Squashed**     |

> **Note**: In squashed mode, `jump_marked` is checked after each body execution. This means jumps via `GOTO` or `CALL` that set the jump marker are still respected — the loop will break and the jump target will execute next. However, `InterruptNotice` and external interruption via `object_io` can only be injected at `call_offset` boundaries, not between loop sub-steps.

## When to use WHILE vs DO-WHILE

| Scenario                                            | Recommended |
| --------------------------------------------------- | ----------- |
| The loop body may not need to execute at all        | `WHILE`     |
| The loop body must execute at least once            | `DO-WHILE`  |
| The condition must be evaluated before the body     | `WHILE`     |
| The condition only becomes available after the body | `DO-WHILE`  |

> **Condition nodes are nodes**
> Unlike graph model frameworks that hardcode conditions into routing functions, AmritaSense treats the loop condition itself as a `Node[bool]`. That means the condition can be asynchronous, can accept dependency injection, and can be suspended before evaluation. This is the direct embodiment of the “everything is a node” philosophy in loop structures.
