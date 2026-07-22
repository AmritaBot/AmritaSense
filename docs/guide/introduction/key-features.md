# Key Features

## 1.2.1 Nodes as Primitives

In AmritaSense, everything is a node. Conditions, loop bodies, exception handlers, jump targets—they are all ordinary Python functions or coroutines wrapped by the `@Node()` decorator; no special inheritance is required.

Every node is treated as an **atomic execution unit**: it either runs completely or not at all. The workflow interpreter manages jumps and nesting through a pointer vector (`PointerVector`) and a call stack instead of a graph structure. All high-level control flow is expanded into a linear instruction sequence at compile time; at runtime only integer operations and function calls remain.

## 1.2.2 Streaming-First

AmritaSense includes a built-in full-duplex streaming primitive, `SuspendObjectStream`, making streaming control flow as natural as ordinary iteration:

- **Native suspend/resume** – The workflow can be precisely suspended between any two nodes, waiting for external input or an async operation to complete before resuming. This mechanism is built entirely on Python’s `asyncio.Future`, with zero blocking overhead.
- **Bidirectional control channel** – External systems can actively push messages or instructions into the workflow via `push_object`, enabling interrupt calls and context injection.
- **Perfect fit for LLM streaming** – Whether it is tool-calling loops, nested sub‑workflows, or pausing for user input, everything can be expressed in the most direct way.

## 1.2.3 Native Control Flow

AmritaSense provides a first-class control flow instruction set; no external graph engine or state machine is needed:

- **Conditional branching** – `IF` / `ELIF` / `ELSE`, no forced `ELSE` pairing, supports chain composition.
- **Loop structures** – `WHILE` (pre‑condition) and `DO…WHILE` (post‑condition), supports breaking out with `BreakLoop`.
- **Jump instructions** – `GOTO` with `ALIAS` for unconditional jumps, `CALL` with `ARCHIVED_NODES` for subroutine calls and returns.
- **Exception handling** – `TRY…CATCH…THEN…FIN`, fully aligned with Python’s exception handling semantics, with controlled exception penetration.

All control flow instructions are expanded into low-level node compositions at compile time. Execution is performed entirely through pointer offsets; there is no graph traversal, string routing, or state-dictionary lookup.

## 1.2.4 Async-Native

- Full `async/await` support, seamlessly integrated with Python’s modern async ecosystem.
- The workflow executor is built on `asyncio`; every I/O‑bound operation can run without blocking.
- The suspend/resume mechanism is completely asynchronous and never blocks the event loop.
- Synchronous functions can be automatically executed in a thread pool via `wrap_to_async`, preventing event-loop blockage.

## 1.2.5 Declarative Dependency Injection

- Nodes and event handlers declare required parameters through function signatures; the framework automatically resolves them from the workflow context.
- Resolution strategy based on **keyword-first matching with type-matching fallback**, eliminating the fragility of positional argument ordering.
- `Depends` supports custom dependency factories, giving flexible control over object creation and scope.
- The dependency list (`DependencyMeta`) is a pure data structure—cacheable, dynamically generatable.

## 1.2.6 Self-Contained Runtime

- **Built-in event system** – Workflow nodes can fire custom events; event handlers share the same dependency injection mechanism as nodes. The event system is broadcast-oriented and is clearly separated from the workflow interruption mechanism.
- **Built-in logging system** – High-performance logger based on `loguru`, supports environment-variable log level control and automatic bridging of the standard `logging` module.
- **Zero mandatory external dependencies** – The core engine is only a few thousand lines of code with no heavy abstractions; it depends solely on `aiologic` and `anyio`.
- **Compile-time expansion of high-level structures** – Runtime overhead is virtually zero; embeddable into any Python project.

## 1.2.7 Interpreter Tree & Subgraph Isolation

- **`FUN_BLOCK` instruction** – Execute a compiled `NodeCompose` as an isolated sub-workflow inside a child interpreter, with independent middleware, I/O stream, and lifecycle.
- **Interpreter tree model** – `fork_interpreter()` creates child interpreters forming a tree; `parent` / `top_interpreter` / `sub_interpreters` properties give full visibility.
- **Parallel execution** – Run multiple child interpreters concurrently via `asyncio.gather` or `wait_all`.
- **Lifecycle management** – `terminate()` / `terminate_all()` for graceful shutdown; `is_running` / `pending_stop` for status queries.
- **Unsafe configuration flags** – `_unsafe.__flags__` provides switches (`FORCE_NOT_WRAP_TO_ASYNC`, `DISABLE_EXC_IGNORED`, etc.) for tuning internal engine behavior in rare edge cases.

## 1.2.8 Native Debugger Implementation

AmritaSense v0.5.0 ships with a complete REPL debugger built in — no extra plugins or tools required. It leverages the interpreter's native Panic/Recover mechanism and middleware injection to deliver breakpoints, stepping, and state inspection directly in the Python REPL.

Key capabilities:

- **Dual API design** — sync API (`step`, `cont`) for interactive REPL use; async API (`step_async`, `cont_async`) for scripted debugging and programs with existing event loops
- **Breakpoint system** — set breakpoints by tag (`break_at_tag`) or address (`break_at_addr`), with conditional expressions
- **Step control** — `step()`, `step_over()`, `step_out()`, `cont()`, with both sync and async API flavors
- **Crash recovery** — after a node exception, the panic state is fully preserved; use `inspect()` to examine the crash site, `advance_pointer()` to skip the failing node, then `cont()` to resume
- **Security guard** — set `REMOVE_DEBUGGER=true` to physically destroy the debugger module, preventing SSTI leakage in production
