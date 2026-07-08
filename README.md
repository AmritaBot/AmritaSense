<center>
<img src="./docs/public/Amrita.png" alt="Logo" width="200" height="200">

<h1>AmritaSense</h1>

<p>
    <a href="https://img.shields.io/pypi/v/amrita-sense">
      <img src="https://img.shields.io/pypi/v/amrita-sense?color=blue&style=flat-square" alt="PyPI Version">
    </a>
    <a href="https://www.python.org/">
      <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&style=flat-square" alt="Python Version">
    </a>
    <a href="LICENSE">
      <img src="https://img.shields.io/github/license/AmritaBot/AmritaSense?style=flat-square" alt="License">
    </a>
    <a href="https://discord.gg/byAD3sbjjj">
      <img src="https://img.shields.io/badge/Discord-Project.Amrita-blue?logo=discord&style=flat-square" alt="Discord">
    </a>
    <a href="https://qm.qq.com/q/9J23pPZN3a">
      <img src="https://img.shields.io/badge/QQ-1006893368-blue?style=flat-square" alt="QQ Group">
    </a>
  </p>

> ### _"Sense is all you need."_

</center>

AmritaSense is a **general-purpose workflow orchestration engine** that replaces traditional graph-based models with an **instruction set architecture**—treating workflows not as nodes-and-edges diagrams, but as programmable execution streams driven by a lightweight virtual machine.

## Why AmritaSense?

Most workflow engines force you into a graph mindset: define nodes, connect edges, manage state objects. AmritaSense takes a different path. You compose nodes and control flow just like writing ordinary code—the engine compiles them into a linear instruction sequence, then executes them step by step. The result: **zero scheduling overhead, native interrupt support, and the expressive power of assembly-level control flow.**

## Core Features

- **Complete Instruction Set**—`IF/ELIF/ELSE`, `WHILE/DO-WHILE`, `GOTO`/`CALL`, `TRY/CATCH/THEN/FIN`, `NOP`, `INTERRUPT`. All control flow is first-class, not simulated through graph routing.
- **VM-Style Execution**—A program counter (`PointerVector`) and call stack drive execution. Jumps are integer operations, not graph traversals.
- **Async-Native Suspend/Resume**—Two `Future` callbacks enable full workflow interruption at any node boundary. Built for debuggers and human-in-the-loop systems.
- **Declarative Dependency Injection**—Nodes declare dependencies via function signatures. The engine resolves them at runtime with type matching and concurrent resolution.
- **Ultra Lightweight**— Compiles 100,000 nodes in ~200ms. Runs anywhere from Raspberry Pi to cloud.
- **Self-Compile Instructions**—Extend the instruction set with `SelfCompileInstruction`. Compile-time expansion, zero runtime overhead.

## Installation

```bash
pip install amrita-sense
```

## Quick Look

```python
import asyncio
from amrita_sense import Node, WorkflowInterpreter as WorkflowPC, IF, NOP

@Node()
def condition() -> bool: return True

@Node()
def action(): print("Done")

flow = IF(condition, action) >> NOP
pc = WorkflowPC(flow.render())

if __name__ == "__main__":
  asyncio.run(pc.run())
```

See more demos in `demos/`

## Documentation

Full guides, concept explanations, and API reference at **[sense.amritabot.com](https://sense.amritabot.com)**.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

Apache V2. See [LICENSE](LICENSE).

## AIGC Content Licensing Policy

AACLP V1. See [POLICY_OF_AIGC](./POLICY_OF_AIGC) ([Official Link](https://github.com/AmritaBot/AACLP)) for details.
