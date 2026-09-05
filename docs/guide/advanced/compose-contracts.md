# Compose Contracts: Default Implementations & Extension Points

AmritaSense distinguishes between the **concrete composition classes** you use every day and the **abstract contracts** they implement. In most code you will never see the contracts — `NodeCompose` / `NodeComposeRendered` are fully featured, exported from the package root, and are all you need. The abstract base classes exist for two narrower purposes:

1. **Mocking** — fake a rendered graph (or a source composition) in unit tests, without building a real one.
2. **Extension** — plug in a custom source composition or custom rendered graph that satisfies the contract.

This chapter explains that relationship, lists the two contracts, and shows minimal, runnable examples.

## Default implementations vs. abstract contracts

| Role                                                                                         | Default implementation (use this) | Abstract contract (mock / extend)    |
| -------------------------------------------------------------------------------------------- | --------------------------------- | ------------------------------------ |
| **Source composition** — an ordered list of nodes you build with `>>` and hand to `render()` | `NodeCompose`                     | `AbstractComposeOriginal`            |
| **Rendered graph** — the compiled, address-mapped graph executed by `WorkflowInterpreter`    | `NodeComposeRendered`             | `AbstractCompose[AddressCalculator]` |

Both default classes are **complete** — they implement the full compilation pipeline (`render()`, `_build()`, alias resolution, address calculation) and are what the public API (`WorkflowInterpreter`, `FUN_BLOCK`, `BATCH_RUN`, …) accepts. Treat the contracts as _specifications_, not replacements.

```python
# Everyday usage — no contracts involved.
from amrita_sense import Node, WorkflowInterpreter


@Node()
def node_a(): ...


@Node()
def node_b(): ...


wf = node_a >> node_b  # NodeCompose (the default implementation)
rendered = wf.render()  # NodeComposeRendered
pc = WorkflowInterpreter(rendered)
```

## A toolchain analogy: ELF / assembly / syntactic sugar

A compiler-toolchain mapping can help you remember the table above — treat it as a _memory aid_, not something to push too far:

- `AbstractCompose` (the rendered-graph contract) ≈ an **ELF executable image**: already laid out with addresses and a symbol table; load and run.
- `AbstractComposeOriginal` (the source-composition contract) ≈ **assembly / IR**: the intermediate form that says _what to execute_ — no addresses assigned yet, not directly runnable.
- The orchestration itself (`>>` chains, `NodeCompose`, `render()`) ≈ **high-level-language syntactic sugar**: this is the layer you hand-write; address assignment and symbol resolution are hidden under `render()`. You only peel the sugar off and drop to the contract layer when mocking or building a custom container.
- `WorkflowInterpreter` + `calc.advance()` ≈ **loader / CPU**: the pointer vector is the program counter; fetch and execute, step by step.

A few differences, so the analogy is not over-extended:

- The rendered graph is an **object graph**, not bytecode or a binary file; “addresses” are nested index paths (`[0, 1, 2]`), not memory offsets.
- `calc` is closer to the link-time **symbol table**: `resolve_alias()` maps an alias to an address vector at build time; `advance()` is the runtime PC advancement.
- The contracts are **specifications** (like the ELF format spec); the default implementations are what a standard toolchain emits. The runtime only ever **reads** a rendered graph, so a test fake never has to really “link” — implementing a handful of members suffices. That is why mocking is cheap.

## Where the contracts live

Both abstract classes live in `amrita_sense.node.abc_base`:

```python
from amrita_sense.node.abc_base import (
    AbstractAddressCalculator,
    AbstractCompose,
    AbstractComposeOriginal,
)
```

- `AbstractComposeOriginal` — the **source-composition** contract.
- `AbstractCompose[Calc_T]` — the **rendered-graph** contract, parameterized by the type of address calculator bound to the graph (`AbstractAddressCalculator[Compose_T]`).
- `AbstractAddressCalculator[Compose_T]` — the address-calculator contract (implemented by `AddressCalculator`).

### The source-composition contract: `AbstractComposeOriginal`

Any source composition is expected to support chaining, iteration and a builder hook:

- `__iter__()` — yield the child nodes / nested compositions / self-compile instructions.
- `__rshift__(other)` — append another element and return `self`.
- `get_builder()` (abstract classmethod) — declare which concrete rendered-graph class (an `AbstractCompose` subtype) this source composition compiles into. `NodeCompose` returns `NodeComposeRendered`.
- `render()` — build the compiled workflow graph; it is only the **top-level** entry point. When the renderer meets a nested source composition it does not call `render()` — it builds through `get_builder()` (see Example 2). `NodeCompose.render()` constructs a `NodeComposeRendered` and builds it directly.

### The rendered-graph contract: `AbstractCompose[Calc_T]`

This is the interface the runtime consumes — the interpreter, the debugger and node `_post_compile` hooks only **read** a rendered graph and never build or mutate it. The contract has two surfaces:

Read side (used at runtime and by hooks):

- `calc` — the bound address calculator (`resolve_alias()`, `find_addr()`, `find_addr_safe()`, `advance()`).
- `__getitem__(key)` / `__iter__()` / `__len__()` — indexed / sequential access to child entries.
- `__bool__()` — `False` while empty or not yet built.

Build side (used by `render()` and by the renderer when it meets a nested source composition):

- `__init__(compose)` — construct the rendered graph from its source composition.
- `_build(current_path, top)` — compile the graph in place; `current_path` / `top` stay `None` only for the top-level graph.

Both build-side members are abstract, so any source composition can be rendered through its own `get_builder()`. Mocks only need to implement what they exercise — a hook-test fake can make `_build` a no-op.

## Example 1 — Mocking a rendered graph for a `_post_compile` hook

Many built-in nodes resolve aliases or validate addresses at compile time inside `_post_compile(compose)`. When unit-testing such a node you do not want to build a whole workflow — you only need a stand-in whose `calc` answers alias lookups.

```python
from amrita_sense.node.abc_base import (
    AbstractAddressCalculator,
    AbstractCompose,
)
from amrita_sense.types import PointerVector


class FakeCalculator(AbstractAddressCalculator["FakeRendered"]):
    def __init__(self, graph: "FakeRendered"):
        self._aliases = graph._aliases

    def resolve_alias(self, alias: str) -> list[int]:
        if alias not in self._aliases:
            raise KeyError(alias)
        return list(self._aliases[alias])

    def find_addr_safe(self, addr: list[int]):
        return None

    def find_addr(self, addr: list[int]):
        raise KeyError(addr)

    def advance(self, pointer: PointerVector) -> bool:
        return False


class FakeRendered(AbstractCompose[FakeCalculator]):
    """Minimal fake rendered graph: only the runtime-read surface."""

    def __init__(self, aliases: dict[str, list[int]]):
        self._aliases = aliases
        self._calc = FakeCalculator(self)
        self._items: list = []

    @property
    def calc(self) -> FakeCalculator:
        return self._calc

    def __getitem__(self, key: int):
        return self._items[key]

    def __iter__(self):
        return iter(self._items)

    def __bool__(self) -> bool:
        return True

    def __len__(self) -> int:
        return len(self._items)

    def _build(
        self,
        current_path: list[int] | None = None,
        top: AbstractCompose | None = None,
    ) -> None:
        """No-op: hook tests never render a real graph."""
        return None
```

Feeding the fake to a node whose `_post_compile` resolves an alias through `compose.calc`:

```python
from amrita_sense.node import Node


def make_resolver(alias: str):
    addr: list[int] | None = None

    @Node()
    def call():
        return addr

    def _post_compile(compose):  # signature as the runtime passes it
        nonlocal addr
        addr = compose.calc.resolve_alias(alias)

    call._post_compile = _post_compile
    return call


node = make_resolver("target")
node._post_compile(FakeRendered({"target": [1, 2]}))
assert node() == [1, 2]
```

No workflow was built and no `NodeComposeRendered` was constructed — the fake satisfies the whole rendered-graph contract with a handful of small members (its `_build` is a no-op because hook tests never render).

## Example 2 — A custom source composition

A source composition that implements `AbstractComposeOriginal` can be embedded into a larger workflow. The renderer consumes it purely through its contract — iterating over the children and constructing the nested rendered graph via `get_builder()`; it never calls the nested composition's `render()` (that method is only the top-level entry point).

```python
from amrita_sense import Node
from amrita_sense.node.abc_base import AbstractComposeOriginal
from amrita_sense.node.core import NodeComposeRendered


@Node()
def step1(): ...


@Node()
def step2(): ...


@Node()
def step3(): ...


class RepeatTwice(AbstractComposeOriginal["NodeComposeRendered"]):
    """Minimal custom source composition: yields every child twice."""

    def __init__(self, *nodes):
        self._nodes = list(nodes)

    def __iter__(self):
        for n in self._nodes:
            yield n
            yield n

    def __rshift__(self, other):
        self._nodes.append(other)
        return self

    @classmethod
    def get_builder(cls) -> type[NodeComposeRendered]:
        return NodeComposeRendered

    def render(self) -> NodeComposeRendered:
        rendered = type(self).get_builder()(self)
        rendered._build()
        return rendered


workflow = step1 >> RepeatTwice(step2, step3)  # NodeCompose (default impl)
rendered = workflow.render()
```

`RepeatTwice(step2, step3)` is rendered as a nested bubble whose graph contains `step2, step2, step3, step3` — the renderer constructs a nested container through its `get_builder()`, so `RepeatTwice` is treated exactly like a `NodeCompose` as long as both declare the same builder.

## Relationship to `SelfCompileInstruction`

`SelfCompileInstruction` is a third extension point that _produces_ source compositions: its `extract()` returns an `AbstractComposeOriginal` (usually a `NodeCompose`). See [Custom Instruction Set](./custom_instruction) for building new instructions; the contracts in this chapter are for mocking or replacing the _composition containers_ themselves.

## Rules of thumb

- **Default path**: keep using `NodeCompose` / `NodeComposeRendered` — they are complete, exported and recommended.
- **Testing hooks / runtimes**: implement `AbstractCompose` (plus `AbstractAddressCalculator` if `calc` needs to answer lookups) with just the members under test.
- **New container kinds**: subclass `AbstractComposeOriginal` when you need a different _source_ container; implement `AbstractCompose` when you need a different _rendered_ container. Always declare `get_builder()` so the renderer knows which rendered class your source composition compiles into.
- **Read side stays minimal**: only implement the members a test actually exercises. Because `__init__` / `_build` are now part of the rendered-graph contract, a pure-read fake (e.g. hook tests) should stub `_build` as a no-op rather than build a real graph.
