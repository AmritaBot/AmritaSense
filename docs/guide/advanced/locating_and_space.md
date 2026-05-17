# Locating & Scope

In AmritaSense, a workflow is not a static graph of node connections; it is a **nonlinear execution flow over a linear node array**. Understanding “locating and scope” means understanding how to precisely mark targets on that array, compute offsets, and establish scope boundaries so that instructions like GOTO can perform accurate jumps.

This chapter dives into the core mechanisms that make up this addressing system: compile-time alias binding, runtime address resolution, and Bubble scope isolation.

---

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
