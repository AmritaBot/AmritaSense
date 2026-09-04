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

Any source composition is expected to support chaining and iteration:

- `__iter__()` — yield the child nodes / nested compositions / self-compile instructions.
- `__rshift__(other)` — append another element and return `self`.
- `render()` — build the compiled workflow graph.

### The rendered-graph contract: `AbstractCompose[Calc_T]`

This is the **read-only interface the runtime consumes** — the interpreter, the debugger and node `_post_compile` hooks never build or mutate a rendered graph, they only read it:

- `calc` — the bound address calculator (`resolve_alias()`, `find_addr()`, `find_addr_safe()`, `advance()`).
- `__getitem__(key)` / `__iter__()` / `__len__()` — indexed / sequential access to child entries.
- `__bool__()` — `False` while empty or not yet built.

Construction and compilation members (`__init__`, `_build`) are intentionally **not** part of this contract — they belong to concrete implementations such as `NodeComposeRendered`. Keeping the contract minimal is what makes a fake rendered graph cheap to write in tests.

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

No workflow was built and no `NodeComposeRendered` was constructed — the fake satisfies the whole rendered-graph contract with five small members.

## Example 2 — A custom source composition

A source composition that implements `AbstractComposeOriginal` can be embedded into a larger workflow and is consumed by the renderer purely through its contract (iteration + `render()`).

```python
from amrita_sense.node.abc_base import AbstractComposeOriginal
from amrita_sense.node.core import NodeComposeRendered


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

    def render(self) -> NodeComposeRendered:
        rendered = NodeComposeRendered(self)
        rendered._build()
        return rendered


workflow = step1 >> RepeatTwice(step2, step3)  # NodeCompose (default impl)
rendered = workflow.render()
```

`RepeatTwice(step2, step3)` is rendered as a nested bubble whose graph contains `step2, step2, step3, step3` — the renderer treats it exactly like a `NodeCompose` because both satisfy the same source-composition contract.

## Relationship to `SelfCompileInstruction`

`SelfCompileInstruction` is a third extension point that _produces_ source compositions: its `extract()` returns an `AbstractComposeOriginal` (usually a `NodeCompose`). See [Custom Instruction Set](./custom_instruction) for building new instructions; the contracts in this chapter are for mocking or replacing the _composition containers_ themselves.

## Rules of thumb

- **Default path**: keep using `NodeCompose` / `NodeComposeRendered` — they are complete, exported and recommended.
- **Testing hooks / runtimes**: implement `AbstractCompose` (plus `AbstractAddressCalculator` if `calc` needs to answer lookups) with just the members under test.
- **New container kinds**: subclass `AbstractComposeOriginal` when you need a different _source_ container; implement `AbstractCompose` when you need a different _rendered_ container.
- **Never** put compilation-only members on a rendered-graph contract — the runtime never calls them, and adding them makes mocks heavier for no benefit.
