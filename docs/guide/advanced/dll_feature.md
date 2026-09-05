# Dynamic Linking Feature

In the previous chapters we systematically covered locating and addressing. Usually that is more than enough. In practice, however, the existing functionality is not fully flexible: if we need to modify part of a workflow, the standard route — without "hacking" — requires walking an entire pipeline: dump interpreter state → modify the source composition (ADT) → create a new interpreter instance → rebase the interpreter. _That is cumbersome and heavyweight_.

Consider how real operating systems work: dynamically loading a library from outside does not require recompiling the whole program, and can even be **hot-reloaded at runtime**. Inspired by this, AmritaSense introduces a brand-new feature in v0.7.0 — **dynamic linking**.

Before we get to usage and internals, one thing must be made clear up front: dynamic linking causes a **dynamic structural change of the compiled artifact**, and the previous chapters never explained the nature of the address space in a visual way. So this chapter first explores an alternative model of orchestration output, and only then moves to the main topic.

## Orchestration is an Orthogonal Topological Structure

You may feel this contradicts what was said earlier — we previously described AmritaSense orchestration as an instruction _sequence_ rather than a topology graph, so why introduce a topological structure here?

Because to understand dynamic linking we need a **spatial structure**. AmritaSense orchestration is not a blob of "bytecode" — it is ordinary Python objects: a `NodeCompose` can hold executable nodes directly, or hold another `NodeCompose`, which is recursively expanded at compile time to occupy one **space slot** (Space Slot). The compiled artifact is therefore naturally a **nested tree structure**, not a one-dimensional byte stream. For example:

```python
# The parenthesized (b >> c) occupies one space slot (Space Slot) in the middle of the linear chain
workflow = a >> (b >> c) >> d
```

![Diagram](/AmritaSense_Compose_Space_Graph.svg)

The **position** of a space slot matters: when placed at the head of the cascade (e.g. `(b >> c) >> a`), it is expanded in place and degrades into executable nodes — the nesting disappears; to keep nesting, the space slot must appear in the **middle or tail** of the chain — the example above is in the middle.

Expanded by address, the top level has three slots: `[0]` is `a`, `[1]` is the space slot (Space Slot), `[2]` is `d`; the space slot internally expands into `[1,0]` (`b`) and `[1,1]` (`c`).

The pointer visits the four leaves in **depth-first** order: `[0] -> [1,0] -> [1,1] -> [2]` (i.e. `a -> b -> c -> d`). The advancement rule is: on hitting a Compose, descend into its `0`-th child; when the same level is exhausted, move right; at the end, backtrack along the way to find the next sibling — this is exactly the advancement rule of `AddressCalculator.advance()`.

An analogy: treat the whole Compose as a "maze", and the pointer as **walking along a wall** — it always traverses the maze, but the path it takes (the order and pattern of derivation) is decided by the wall's layout (the graph's nesting structure). After compilation this "wall" is fixed, so the pointer's walk is deterministic and predictable.

### Injection = Hijacking a Slot

This gives us the feasible basis for **DLL injection**:

> Hijack a space slot node and you control the entire address space beneath that slot.

For example, continuing with the `a >> (b >> c) >> d` above — replace the space slot (Space Slot) at `[1]` with a DLL placeholder container, and every address prefixed with `[1]` (`[1]`, `[1, 0]`, `[1, 1, ...]`, etc.) falls inside the DLL's addressing range, whose content can be rebased as a whole at runtime; the graph's other slots (`a` at `[0]`, `d` at `[2]`) are completely unaffected.

## Loading & Dynamic Compilation

Enough talk — let's write a real example.

```python
import asyncio

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.instructions import NOP
from amrita_sense.node import DLLCompose


@Node()
def a():
    print("A node")


@Node()
def b():
    print("B node")


dll = DLLCompose(b.as_compose())
comp = a >> dll >> NOP
r_comp = comp.render()

if __name__ == "__main__":
    asyncio.run(WorkflowInterpreter(r_comp).run())
```

The console prints `A node` and `B node`. Note that you must **keep a reference to `dll`** — otherwise you cannot modify its content, and dynamic linking loses its purpose.

The DLL usage in this section is equivalent to:

```python
a >> b.as_compose() >> NOP
```

### Hot-Patching with `dll.apply()`

![Slot diagram](/DLL_In_Compose.svg)

Now let's modify it dynamically. Hot-patch it with `dll.apply()`:

```python
# Before: DLLCompose(b.as_compose())
dll.apply(b >> a)
```

After the rebase, `r_comp`'s content is equivalent to (note that `b >> a` occupies the original space slot as a whole, so the parentheses must be kept):

```python
a >> (b >> a) >> NOP
```

The mechanism of `apply()` is called **address rebase**: the rendered graph's structure stays unchanged — only the content beneath the DLL slot is replaced, and symbols in the new content are re-registered under the **original slot prefix** — just like relinking a shared library back to its original load address.

Note that dynamic modification is not guaranteed to be thread-safe. Choose the timing carefully — for example, call `apply()` at a suspension point where the interpreter is not yet addressing. Two kinds of misuse raise different exceptions: calling `apply()` on a DLL that was **never built** (there is no slot path to relink) raises **GraphBuildError**; while looking up a **nonexistent address at runtime** (including old symbols already cleaned up by a rebase) raises an **NPE** (`NullPointerException`).

## What Happens Internally

`DLLCompose` is a **source container** (source composition): it holds a `NodeCompose` to be linked and tells the renderer via `get_builder()` — build me a **placeholder container** (proxy). The renderer therefore does not statically expand the DLL's content into the graph; instead it places a placeholder container at the DLL's slot, and that container compiles the source Compose into an ordinary rendered graph when it is built.

> For the relationship between source compositions and the rendered-graph contract, revisit the previous chapter, [Compose Contracts](./compose-contracts). A DLL is not part of the contract itself — it merely wraps a "source composition" in a **rebasable container**: the same instance can be `apply()`-ed repeatedly, and each time it recompiles in place and re-locates symbols under the original prefix.

The full `apply()` flow:

1. Remove the symbols **previously registered by this DLL** from the top-level `alias2vector_map` (do not clear the whole table).
2. Compile the new composition into the same slot; during compilation, aliases in the new content are re-registered into the top-level `alias2vector_map` **prefixed with the DLL slot**.
3. Record the symbols added this time, as the cleanup list for the next `apply()`.
4. Re-run the `_post_compile` hooks collected during the build.

Before the rebase (after the first render), suppose the DLL occupies slot `[1]` and its content registered two symbols via `ALIAS` (with other DLL-unrelated aliases outside). The top-level symbol table (`alias2vector_map`) is then:

```python
# Before rebase
alias2vector_map = {
    "a": [0],          # outer symbol (before the DLL), unrelated to the DLL
    "x": [1, 0],       # prefix [1] means "inside the DLL"
    "y": [1, 1],
}
```

After rebasing with `dll.apply(ALIAS(y, "y") >> ALIAS(x, "x"))`, old symbols are removed and aliases in the new content are re-registered under the **same slot prefix**:

```python
# After rebase
alias2vector_map = {
    "a": [0],          # outer symbol unaffected
    "y": [1, 0],       # re-registered under the same prefix — absolute address [1, 0] now points to y
    "x": [1, 1],
}
```

Here lies a trap: **absolute addresses inside a DLL are unreliable** — after a rebase the same absolute address may point to a completely different node, so do not hard-code absolute addresses at runtime, or undefined consequences may follow.

Conversely, the following reference styles are safe:

- **alias / tag lookup**: aliases are automatically relocated by the prefix mechanism and remain valid after a rebase.
- **Relative addressing within the same space slot (`jump_near`, etc.)**: they describe "relative positions inside the same space slot" rather than an absolute prefix, so they do not break when the slot prefix changes.

### Usage Limits

Given the placeholder-container mechanism, a few boundaries follow naturally:

- **Must be embedded in a host slot**: the placeholder container needs the host rendered graph to supply the address path (`current_path`) and top-level scope (`top`) to complete the build. Therefore a `DLLCompose` cannot `render()` on its own, detached from a host — that raises a GraphBuildError.
- **Bound once**: when the renderer first encounters a `DLLCompose`, it creates and binds a placeholder container for it; **the same `DLLCompose` instance cannot be rendered a second time** (e.g. composed into two trees, or appearing twice in one tree) — that raises a RuntimeError. The correct way to hot-update is to hold the instance and only `apply()` it, never re-render it.
- **Constructor argument**: `DLLCompose(...)` only accepts a `NodeCompose` (the result of `as_compose()`), not a bare node; the new composition passed to `apply()` must likewise be a `NodeCompose`.

## Summary

This chapter introduced the topological view of orchestration space (the pointer = a DFS cursor that walks along a wall), the principle of DLL injection (hijacking a slot hijacks the entire address space beneath it), and how to hot-patch with `dll.apply()`.

Keep in mind:

- **Thread safety**: `apply()` concurrent with a running interpreter is unsafe — modify at suspension points.
- **Null references & invalid addresses**: calling `apply()` on an unbuilt DLL raises **GraphBuildError** (there is no bound placeholder container or slot path to relink); only **runtime** lookups of nonexistent addresses or old symbols cleaned up by a rebase cause an **NPE**.
- **Single binding**: a `DLLCompose` instance can only be rendered and bound once — hot-update by repeatedly `apply()`-ing the same instance rather than re-rendering it.
- **Compilation timing**: the source Compose inside a DLL is compiled only when the placeholder container is built (render / apply), so `_post_compile` hooks re-run after every rebase — do not assume they run only once.
- **Address stability**: hard-coded absolute addresses are discouraged and unstable; use aliases / relative addressing.
