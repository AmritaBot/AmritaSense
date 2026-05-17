# Addressing & Data Structures

Before diving into AmritaSense’s control flow, you must understand how it organizes and locates nodes. It is not a flat graph; it is a deep, precisely addressable address space.

---

## 3.2.1 Address space: Bubble and hierarchical structure

In AmritaSense, node placement and location are not a flat one-layer structure. Instead, it is a **multi-layer nested address space**.

Each layer is called a **Bubble**.

A Bubble has its own `near` address space, which is essentially the linear index of nodes within that layer. When we wrap a group of nodes with parentheses `()`, we create a new Bubble — an inner execution space. Nodes inside that Bubble have their own independent address index and are not directly interfered with by external linear counting.

This design makes logical partitioning extremely natural: you do not need to manually manage complex subgraph references. You simply use parentheses to define scope, and jump and call semantics are automatically limited to that local space.

---

## 3.2.2 Pointer vectors: variable-dimensional high-dimensional indices

Since the address space is multi-layered, how can we pinpoint any node precisely?

This brings us to AmritaSense’s core data structure: the **PointerVector**.

As the name suggests, a pointer vector is a **variable-dimensional high-dimensional vector**. Its number of dimensions corresponds one-to-one with the node’s nesting depth: if the node is at the top level, the pointer is one-dimensional `[i]`; if it is inside two nested Bubbles, the pointer is two-dimensional `[i, j]`; and so on. Each value in a dimension corresponds to the absolute offset index within that layer.

**Note:** the vector is only its external representation, not its underlying semantic essence. The dimensionality and magnitude of the vector do not carry execution semantics by themselves — it is just a data structure.

Its real pointer behavior appears in runtime logic:

In the `WorkflowInterpreter` main loop, the engine always treats the address pointed to by the pointer vector as the current execution node. After each iteration, the interpreter executes the current node and then advances the pointer to the next position. The pointer vector is effectively the workflow’s “program counter.” It determines **who executes next**.

When nested execution is needed, the interpreter appends a new dimension to the pointer vector (entering a Bubble). When the Bubble is finished, it pops that dimension (exiting the Bubble) and returns to the previous layer.

---

## 3.2.3 Location and jumps: the ALIAS symbol aliasing system

After understanding the address space and pointer vector layout, the next step is node location and flow jump capability.

Suppose you have the following base execution flow:

```python
IF(...) >> node1 >> node2
```

If you want to implement conditional branch jumping — **if the IF condition is true, jump to node2; otherwise continue sequentially** — you need AmritaSense’s **symbol alias mechanism**.

ALIAS works similarly to a symbolic link in Linux, except it does not point to a file path. Instead, it binds directly to a physical node address inside the engine. By attaching a globally unique symbol tag to a target node, other places in the workflow can jump to that target by its symbol, without knowing the exact pointer vector numeric values.

With this syntax, you can realize precise jumps:

```python
IF(condition, GOTO("tag")) >> node1 >> ALIAS(node2, "tag")
```

In this example:

- `"tag"` is the alias label, bound to the physical address of `node2` at compile time.
- `ALIAS` is a dedicated tagging primitive used to attach a symbol alias to the target node.
- `GOTO("tag")` performs a runtime alias lookup and jumps directly to the target address.
- During preprocessing, the interpreter completes alias registration and address mapping.

**The core advantage of this addressing system is that it completely separates “data layout” (structured node arrays) from “execution path” (pointer jumps).** The workflow is stored in memory as a linear sequence of nodes, but the interpreter can use symbol lookup and pointer rewriting to realize arbitrary nonlinear control flow within that linear space. This is a direct mapping of the von Neumann architecture’s core idea into a workflow engine.
