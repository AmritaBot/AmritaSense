# NOP Sentinel & INTERRUPT Forced Termination

`NOP` and `INTERRUPT` are two special atomic instructions in AmritaSense’s instruction set. They are not `SelfCompileInstruction` and have no compile-time expansion. Instead, they exist as individual nodes in the workflow, and their behavior is defined purely at runtime.

## NOP sentinel instruction

`NOP` (No Operation) is an **empty sentinel node**. Its significance is not in doing work, but in **standing in place** to provide a valid jump target.

### Implementation

```python
@_node_fun(wrap_to_async=False, address_able=True)
def _no_operation() -> None:
    pass

NOP: _Node[None] = _no_operation
```

### Key attributes

- `address_able=True`: this is its most important property. An addressable node can be tagged with `ALIAS` and become a target for `GOTO` or `CALL`. `NOP` makes this role explicit.
- `wrap_to_async=False`: it is a pure synchronous function that returns immediately, with almost zero overhead.

### Typical uses

**As a convergence point for jumps**: in conditional branches, different paths can converge on the same `NOP`.

```python
IF(cond, GOTO("then")) >> ... >> ALIAS(NOP, "end_if")
```

`NOP` provides a common continuation address for different control flow paths.

**As a subroutine return point**: subroutines archived in `ARCHIVED_NODES` often end with `NOP`. After the subroutine finishes, the interpreter steps to `NOP`, and `call_sub` then pops the return address.

**As an empty ELSE branch**: `IF(cond, do).ELSE(NOP)` expresses “do nothing when the condition is false” explicitly.

## INTERRUPT forced termination instruction

`INTERRUPT` is the workflow’s **emergency stop button**. When executed, the workflow terminates immediately and unconditionally.

### Implementation

```python
@_node_fun(wrap_to_async=False, address_able=False)
def _interrput_operation() -> NoReturn:
    raise InterruptNotice("Interrupt Node")

INTERRUPT: _Node[NoReturn] = _interrput_operation
```

### Execution mechanism

1. **Raise `InterruptNotice`**: this exception is a subclass of `BaseException`, not a regular `Exception`.
2. **Global catch**: the interpreter’s main loop catches `InterruptNotice` at the top level and enters cleanup.
3. **Clean termination**: it clears `_ret_addr_stack`, resets `_pointer`, clears `_jump_marked`, and exits.

### Key attributes

- `address_able=False`: it is a terminator, so it should never be a jump target. Jumping to a node that immediately terminates is meaningless.
- `NoReturn` return type: the type system makes it clear that code after `INTERRUPT` is unreachable.

### Exception penetration rules

`InterruptNotice` inherits from `BaseException`. In Python, `except Exception` does not catch `BaseException` subclasses, so **workflow `TRY/CATCH` blocks do not catch `InterruptNotice` by default**. It naturally penetrates upward.

The only exception is when `InterruptNotice` is explicitly included in the `exception_ignored` tuple during `WorkflowInterpreter` initialization, at which point it becomes catchable. However, that is rarely necessary — `INTERRUPT` is designed to be an “uncatchable” emergency stop.

### Usage scenarios

- **External signal response**: when an external system issues a termination signal, the next node boundary can trigger `INTERRUPT`.
- **Emergency safety stop**: insert `INTERRUPT` in the workflow when an unrecoverable error or dangerous condition occurs.
- **Timeout handling**: a node can check timeout conditions before execution and raise `INTERRUPT` to force termination.

## Comparison summary

|                  | NOP                                       | INTERRUPT                      |
| ---------------- | ----------------------------------------- | ------------------------------ |
| Responsibility   | placeholder, convergence, return point    | emergency termination          |
| Addressable      | yes                                       | no                             |
| Return type      | `None`                                    | `NoReturn`                     |
| Control impact   | none, execution continues                 | terminates entire workflow     |
| Typical position | ALIAS target, branch tail, subroutine end | error branch end, timeout path |

`NOP` is the silent scaffolding for complex control flow, while `INTERRUPT` is the final safety valve. Together, they form the foundation of AmritaSense’s execution control system.
