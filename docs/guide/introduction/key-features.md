# Key Features

## 1.2.1 Stream-first design

- Native support for streaming output, which integrates seamlessly with AmritaCore for real-time response.
- Workflows can suspend and resume between nodes, making them ideal for LLM streaming, long-lived connections, and similar scenarios.
- Built-in `SuspendObjectStream` abstraction makes writing streaming control flow feel as natural as ordinary iteration.

## 1.2.2 Turing completeness (nodes as primitives)

AmritaSense natively provides a complete set of control flow capabilities without relying on an external graph engine or state machine:

- **Conditional logic**: `IF` / `ELIF` / `ELSE`, with no forced `ELSE` pairing and support for chained combinations.
- **Loop constructs**: `WHILE` (precondition) and `DO...WHILE` (postcondition).
- **Jump instructions**: `GOTO` combined with `ALIAS`, support for relative and absolute addressing.
- **Exception handling**: `TRY...CATCH`, with stack-safe behavior that maintains integrity in nested scenarios.

**Nodes are primitives**: each node is an ordinary callable object (function or coroutine), without requiring special inheritance. The framework does not depend on runtime graph parsing of edges; all control flow is expanded into unified pointer instructions at compile time, and runtime execution only involves integer operations and function calls.

## 1.2.3 Native async

- Full support for `async/await`, with seamless integration into Python’s modern async ecosystem.
- The workflow executor is built on `asyncio`, so all I/O-bound operations can run non-blocking.
- The suspend/resume mechanism is fully asynchronous and does not block the event loop.

## 1.2.4 High extensibility

- **Custom nodes**: implement a callable object and embed it into the workflow as a node.
- **Self-compiled instructions**: create new high-level primitives by implementing the `SelfCompileInstruction` interface.
- **Extensible instruction set**: register new jump types or addressing patterns without modifying the core runtime.

## 1.2.5 Dependency injection (automatic context resolution)

- Nodes declare required parameters through function signatures, and the framework resolves them from the workflow context automatically.
- Dependency resolution is based on type annotations, avoiding implicit `Dict[str, Any]`-style state passing.
- Custom dependency factories are supported, giving you flexible control over object creation and scope.

## 1.2.6 Lightweight and high performance

- The core engine is only a few thousand lines of code, with no heavy abstractions or runtime state dictionaries.
- High-level constructs are expanded at compile time, so runtime overhead is nearly zero.
