# Locating & Scope

In AmritaSense, a workflow is not a static graph of node connections; it is a **nonlinear execution flow over a linear node array**. Understanding “locating and scope” means understanding how to precisely mark targets on that array, compute offsets, and establish scope boundaries so that instructions like GOTO can perform accurate jumps.

This chapter dives into the core mechanisms that make up this addressing system: compile-time alias binding, runtime address resolution, and Bubble scope isolation.

## 4.2.1 Compile-time binding: the ALIAS alias system

`ALIAS` is the **compile-time foundation** of the locating system. It binds a node to a globally unique symbol name and registers it into `alias2vector_map` during render time so that GOTO and CALL can resolve it at runtime.

### Alias registration mechanism

When the workflow is compiled with `render()`, all `ALIAS` nodes store their alias and corresponding `PointerVector` address in `NodeComposeRendered.alias2vector_map` according to their position in the composed array. This dictionary remains unchanged throughout execution and is the **single source of truth for symbol-to-physical-address mapping**.

### Usage constraints

`ALIAS` cannot be attached to every node arbitrarily. It has three strict compile-time checks:

- **Uniqueness**: a duplicate alias in the same workflow throws a `RuntimeError`, preventing symbol pollution.
- **Addressability**: the aliased node must have `address_able=True`; otherwise it cannot be correctly located by a pointer vector.
- **Type restriction**: you cannot create an alias for a `SelfCompileInstruction` node because self-compiled instructions are expanded into `NodeCompose` during compile time and are no longer a single addressable node.

These constraints ensure the alias table remains clean and resolvable at runtime.

### Practical usage

```python
from amrita_sense.instructions import ALIAS, IF, GOTO
from amrita_sense.node import Node


@Node()
def action():
    print("Executing action")


# ALIAS binds action to the symbol "main_action"
# After that, GOTO("main_action") or CALL("main_action") can reference it directly.
labeled_action = ALIAS(action, "main_action")

workflow = IF(some_condition, GOTO("main_action")) >> labeled_action
```

## 4.2.2 Runtime resolution: GOTO unconditional jump

`GOTO` is the most direct control flow jump instruction in AmritaSense. At runtime, it looks up the target address from the alias table and performs a single pointer rewrite so the interpreter directly executes the target node.

### Jump target validation

`GOTO`'s `JumpNode` completes address resolution during compile-time `_post_compile`. This design allows errors to be caught **before runtime**:

- When using an alias, `_post_compile` checks whether the alias exists in `alias2vector_map`.
- If the alias is not found, `JumpNode` lists all registered aliases, performs a fuzzy match with `difflib`, and raises an error with a "did you mean X?" suggestion.
- When using an absolute address (`list[int]`), the address is directly validated to ensure it points to a valid node.

### Jump marker mechanism

All jump methods (`jump_to`, `jump_near`, `jump_offset`, etc.) use the `@markup` decorator. Its purpose is to set the `_jump_marked` flag after a jump occurs, which prevents the interpreter from performing the normal pointer advance immediately after the jump. This ensures that **jumping and stepping are mutually exclusive** — execution is either explicitly moved or automatically advanced, never both.

### Best practices

1. **Prefer aliases over raw addresses**: `GOTO("target")` is more readable than `GOTO([1, 3, 5])`, and the alias table provides uniqueness validation at compile time.
2. **Do not use GOTO as a substitute for loops**: GOTO does not push a return address onto the call stack and is not suitable for cases requiring a return. Use `CALL` for subroutine calls that need to return — this will be covered in detail in [the next chapter](./child_node.md).
3. **Mind Bubble boundaries**: GOTO can jump across any nesting level, but overusing cross-level jumps makes control flow difficult to trace. Prefer `jump_near` within the same Bubble and `jump_to` for cross-Bubble jumps.

## 4.2.3 CALL instruction: the entry point for subroutine invocation

In addition to `GOTO`'s one-way jump, AmritaSense also provides the `CALL` instruction for **calling a subroutine and automatically returning after execution**. `CALL` shares the same alias-based addressing system as `GOTO` — both rely on `ALIAS` for symbol registration, and both complete address resolution and spelling correction during the compile-time `_post_compile` phase.

### Core differences

| Feature                  | GOTO                                | CALL                                     |
| ------------------------ | ----------------------------------- | ---------------------------------------- |
| Saves return address?    | No                                  | Yes (pushes onto `_ret_addr_stack`)      |
| After-execution behavior | Continues advancing from the target | Automatically pops the stack and returns |
| Use cases                | One-way jumps, branch merging       | Subroutine reuse, interrupt handling     |

> **Further reading**
> The complete `CALL` mechanism — including call stack management, the `ARCHIVED_NODES` storage structure, `SubprogramJumpNode` skip logic, and interrupt vector table implementation — will be covered in detail in [Chapter 4.3: Calling Subroutines](./child_node.md).

## 4.2.4 Scope isolation: Bubble scopes and near addressing

AmritaSense uses `PointerVector` to manage multi-level nested address spaces. Every node group wrapped in parentheses `()` forms an independent `NodeComposeRendered` after compilation, with its own internal `near` address space — this is a **Bubble**.

### Address vector structure

`PointerVector` is a variable-length integer array. Each dimension corresponds to a nesting level, and the value at that dimension is the absolute offset index within that level. For example, `[0, 2, 1]` means: top-level element 0 → descend into its sub-Bubble → element 2 inside that sub-Bubble → descend into its sub-Bubble → element 1.

### Addressing modes

AmritaSense provides three levels of addressing operations:

| Method         | Behavior                                              | Use case                       |
| -------------- | ----------------------------------------------------- | ------------------------------ |
| `near_to(n)`   | Replace the current level's index with `n`            | Jumps within the same Bubble   |
| `offset(n)`    | Add `n` to the current level's index                  | Relative jumps within a Bubble |
| `far_to(addr)` | Replace the entire pointer with a full address vector | Cross-Bubble jumps             |

### Scope isolation

The core value of Bubble lies in **scope isolation**:

- Each Bubble has its own `near` address space. Jump instructions within a Bubble are only valid inside that Bubble and do not affect the outer scope.
- When a Bubble finishes executing, the interpreter automatically pops the last dimension of the pointer vector and returns to the parent Bubble to continue.
- Exception and interrupt propagation also follows Bubble hierarchy — they can penetrate nesting, but internal state does not leak to the outer scope.

### Application

In complex conditional chains, different branches may each contain nested workflow structures. Bubble scoping ensures that jumps inside each branch are isolated from one another:

```python
complex_flow = (
    IF(cond1, GOTO("exit")) >> ALIAS(nested_workflow, "branch_a") >> ALIAS(NOP, "exit")
)
```

`nested_workflow` is an independent Bubble; its internal GOTO, CALL, and other operations do not affect the address space of `complex_flow`. This isolation is key to AmritaSense's ability to safely handle deeply nested workflows — developers can bracket scope boundaries just like writing code, and the interpreter automatically manages entry and exit.
