# Introduction

## 1.1 Project Overview

### 1.1.1 What is AmritaSense?

**AmritaSense is a next-generation, general-purpose workflow and event stream engine.** It abandons traditional graph-based design and instead adopts the **execution model of a low-level computer**—an instruction set, a pointer vector, and a program counter—to orchestrate and control workflows.

Unlike systems that require you to explicitly define nodes and edges and then rely on a scheduler to interpret the graph structure, AmritaSense provides an **intuitive composition model**. You simply combine nodes and control structures as if writing ordinary Python code; the framework compiles them into a linearized instruction sequence and a lightweight “virtual machine” executes them step by step. This design gives AmritaSense unparalleled expressive power and runtime control precision while keeping overhead extremely low.

Furthermore, AmritaSense includes a complete **event and dependency injection subsystem** with no external dependencies. Workflow nodes can trigger custom events, and event handlers share the same dependency injection mechanism as nodes, unifying orchestration and reaction inside a single runtime.

### 1.1.2 Why AmritaSense?

We believe that **workflows should be designed for the work, not limited by the flow**. “Flow” is merely a presentation; it should never become a shackle when you design logic.

- **Natively Turing-complete** – You can implement complete, arbitrary control logic without defining complex boundary conditions inside your program. AmritaSense natively supports conditionals (`IF/ELIF/ELSE`), loops (`WHILE/DO‑WHILE`), unconditional jumps (`GOTO`), subroutine calls (`CALL`), and exception handling (`TRY/CATCH`)—no external graph engine or state machine required.
- **Virtual-machine addressing model** – AmritaSense uses a classic computer-style **addressing and execution model** (`PointerVector` + call stack). All high-level control flow is expanded into uniform pointer instructions at compile time. Only integer operations and function calls remain at runtime; scheduling overhead is nearly zero.
- **Built for AI agents and complex business logic** – Whether it is tool-calling loops, nested sub‑workflows, pausing for user input, or exception recovery and rollback, AmritaSense can express it directly and execute it with extreme efficiency.

### 1.1.3 Core Value Proposition

- **Low-level computer execution model** – Replaces topological graphs with a pointer vector and call stack; minimal runtime, far outperforming traditional graph engines.
- **Natively Turing-complete** – `IF`, `WHILE`, `DO‑WHILE`, `GOTO`, `CALL`, `TRY`, `INTERRUPT` and more are all natively supported—no simulation.
- **Focus on flow logic** – Say goodbye to complicated edge definitions and state dictionaries; concentrate on the business process you actually care about.
- **Declarative dependency injection** – Nodes and event handlers declare required parameters through function signatures; the framework automatically performs keyword matching and type resolution.
- **Async-first, suspendable & resumable** – Native `async/await` support, built-in full-duplex streaming primitive (`SuspendObjectStream`), allowing precise suspension and resumption between nodes.
- **Interpreter tree & subgraph isolation** – Fork sub-interpreters for parallel execution; manage entire interpreter trees with `wait_all` / `terminate_all`; use `FUN_BLOCK` for isolated sub-workflow calls with independent middleware and error boundaries.
- **Self-contained runtime** – Built-in logging system, event bus, and dependency injection; zero mandatory external dependencies; embeddable into any Python project.
