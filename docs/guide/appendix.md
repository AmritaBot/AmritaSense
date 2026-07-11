# Appendix and Resources

## 9.1 Glossary and Terminology

### 9.1.1 Workflow

In AmritaSense, a workflow is an asynchronous execution stream composed of nodes arranged in a specific order. It is not a static graph structure but an instruction sequence that can be executed step by step by the interpreter, supporting interruption and jumps.

### 9.1.2 Node

The smallest execution unit of a workflow. Any Python function or coroutine decorated with `@Node()` is a node. Nodes are atomic—they either execute completely or not at all. Conditions, loop bodies, exception handlers—everything is a node.

### 9.1.3 PointerVector

AmritaSense's core addressing data structure. It is a variable-length integer array where each dimension corresponds to a nesting level, and the value at that dimension represents the offset index within that level. In the interpreter's main loop, `PointerVector` plays the role of the program counter (PC), always pointing to the node currently being executed.

### 9.1.4 Bubble

An independent address space formed after compilation by nodes wrapped in parentheses `()`. Each Bubble has its own `near` address space, and jump operations inside it do not affect the outer layers. Bubble is the underlying mechanism by which AmritaSense achieves scope isolation and data encapsulation.

### 9.1.5 Instruction Set

A complete set of control flow primitives provided by AmritaSense, including `IF/ELIF/ELSE` (conditional branching), `WHILE/DO-WHILE` (loops), `GOTO` (unconditional jump), `CALL` (subroutine call), `TRY/CATCH/THEN/FIN` (exception handling), `NOP` (sentinel), and `INTERRUPT` (forced termination). All instructions are expanded into low-level node compositions at compile time and completed through pointer jumps at runtime.

### 9.1.6 Self-Compile Instruction

An instruction class that implements the `SelfCompileInstruction` interface. During the `render()` phase, they are automatically expanded into standard `NodeCompose` structures through the `extract()` method. Both built-in instructions and developer-defined custom instructions are based on this mechanism, achieving compile-time optimization and zero runtime overhead.

### 9.1.7 Interrupt

A cooperative suspension mechanism provided by AmritaSense. The workflow actively suspends at specified markers, yielding control back to the external system. The external system can inspect state and modify variables during this window, then resume execution via `resume()`. This is the foundational capability for building debuggers and external monitoring systems.

### 9.1.8 Depends (Dependency Injection)

A dependency injection pattern inspired by FastAPI. Nodes declare the resources they need by declaring `Depends(factory)` in their function signatures. AmritaSense's dependency resolution system supports concurrent resolution, runtime injection, and type matching. If a factory function returns `None`, the workflow will terminate immediately.

### 9.1.9 Alias

A globally unique symbol name bound to a node via the `ALIAS` instruction. Registered into `alias2vector_map` at compile time for `GOTO` and `CALL` to look up and resolve at runtime. This is the foundation of AmritaSense's symbolic addressing system.

### 9.1.10 Subprogram

A sequence of nodes defined by the `ARCHIVED_NODES` instruction, skipped by `SubprogramJumpNode`, and accessible only through `CALL` or external injection. Subprograms can store interrupt handling logic, debugging tools, or reusable functional modules without affecting the normal execution flow.

### 9.1.11 Other Core Terminology

- **Interpret Lock**: An `aiologic.Lock` instance that guarantees only one node is executing at a time, forming the mutual exclusion basis for safe external invocation.
- **Jump Mark**: The `_jump_marked` flag. When `True`, the interpreter skips the regular pointer advancement step and the next cycle starts from the jump target.
- **Exception Penetration**: Exceptions marked via `exception_ignored` cannot be caught by any `CATCH` block and propagate directly to the top-level handler.
- **Call Stack**: `Stack[PointerVector]`, managing return addresses for subroutine calls.
- **DI Cache** (v0.4.2+): `DICache` — an LRU-based cache inside `WorkflowInterpreter` that stores resolved dependency injection kwargs. Keyed by `hash((hash(pointer), args_hash))`, it avoids redundant DI resolution when the same node is revisited with the same argument types. The payload is an `LRUCache` with max 2048 entries. Controlled via unsafe flags `WORKFLOW_DI_NO_CACHE`, `WORKFLOW_DI_PRELOAD_CACHE`, and `WORKFLOW_DI_PRELOAD_BATCH`.
- **Address Calculator** (v0.4.4+): `AddressCalculator` — a stateless address computation utility exposed via `NodeComposeRendered.calc`. Provides `advance()`, `resolve_alias()`, `find_addr()`, and `find_addr_safe()` methods. Encapsulates pointer advancement logic previously held in the interpreter's `_ptr_cache`.

### 9.1.12 Abbreviations

- **API**: Application Programming Interface
- **DI**: Dependency Injection
- **PC**: Program Counter
- **JSON**: JavaScript Object Notation
- **HTTP**: Hypertext Transfer Protocol
- **ISA**: Instruction Set Architecture

### 9.1.13 Primitive

**Primitive** is a core concept in computer architecture, referring to the **smallest indivisible operation unit** defined within a processor's Instruction Set Architecture (ISA). In an ISA, primitives dictate the most fundamental capabilities a processor can execute—such as addition, data loading, conditional branching—and all complex programs are ultimately composed of these primitives. Primitives define "what the hardware can do"; software achieves arbitrarily complex logic through the combination of primitives.

In AmritaSense, **workflows are similarly built upon a set of primitives**:

- **Nodes are execution primitives**: Every function wrapped by `@Node()` is an indivisible atomic execution unit. The interpreter will not interrupt execution inside a node; a node either runs completely or not at all.
- **Instructions are control flow primitives**: `IF`, `GOTO`, `CALL`, `TRY`, and other instructions are the smallest semantic units of flow control. They define the most basic control flow operations the interpreter can execute—conditional jump, unconditional jump, subroutine call, exception capture.
- **Instructions define the architectural boundary**: Just as an ISA defines the contract between hardware and software, AmritaSense's instruction set defines the stable boundary between "what the compiler can generate" and "what the interpreter can execute." Self-compile instructions (`SelfCompileInstruction`) expand into low-level primitive nodes at compile time; the runtime only processes these already-expanded primitives.

The core value of primitives lies in the **unity of simplicity and completeness**: each primitive does only one thing, but a set of primitives combined can express arbitrarily complex logic. This is the theoretical root of AmritaSense's design philosophy that "simplicity is truth."

## 9.2 Project Resources

### 9.2.1 GitHub Repositories

- **AmritaSense Repository**: [https://github.com/AmritaBot/AmritaSense](https://github.com/AmritaBot/AmritaSense)
- **Issue Reports**: Submit bug reports and feature requests in the repository
- **Pull Requests**: Code contributions via PR are welcome

### 9.2.2 Official Websites

- **AmritaSense Documentation**: [https://sense.amritabot.com](https://sense.amritabot.com) (this page)
- **Comprehensive Guides and Tutorials**: This documentation site provides complete guides and API references

### 9.2.3 Contribution Guide

Contributions to AmritaSense are welcome. The contribution process is as follows:

1. **Fork the repository**: Create a personal copy of the project
2. **Create a branch**: Make changes in a new branch
3. **Write tests**: Ensure changes do not break existing functionality
4. **Update documentation**: Keep documentation in sync with code
5. **Submit a pull request**: Describe the changes and submit for review

**Code Style Guide**:

- Follow the PEP 8 Python style guide
- Write docstrings for all public functions and classes
- Use type hints for all function parameters and return values
- Keep functions focused and concise
- Core business logic must be written by humans (see the AIGC policy in the repository for details)

For more information, refer to the `CONTRIBUTING.md` file in each project repository.

### 9.2.4 License

- **AmritaSense**: Released under the **Apache 2.0** license

For the complete license text, refer to the `LICENSE` file in the repository.

## 9.3 Community and Support

### 9.3.1 Discussion and Feedback

- **Discord Server**: [https://discord.gg/byAD3sbjjj](https://discord.gg/byAD3sbjjj)
- **QQ Group**: 1006893368
- **GitHub Discussions**: Participate in technical discussions in the repository's discussion section

### 9.3.2 Submitting Issues

Please follow these steps when reporting issues:

1. Search existing issues to avoid duplicates
2. Provide a clear, descriptive title
3. Include complete reproduction steps and code snippets
4. Specify the runtime environment (OS, Python version, library version)

### 9.3.3 Code of Conduct

The Amrita community follows the Contributor Covenant Code of Conduct:

- **Be respectful**: Treat everyone with respect regardless of background
- **Be constructive**: Provide constructive feedback and suggestions
- **Be inclusive**: Welcome people from all backgrounds
- **Focus on quality**: Strive to improve the quality of the project

## 9.4 Design Philosophy and Related Resources

### 9.4.1 Design Philosophy

- **"Everything is a node"**: Conditions, loop bodies, exception handlers—they are all instances of `Node`
- **"Instructions replace graphs"**: Workflows are nonlinear execution streams on linear node arrays; jumps are pointer rewrites
- **"Simplicity is truth"**: Achieving complete control flow with minimal code

### 9.4.2 Related Technical Resources

- **Python Official Documentation**: [https://docs.python.org/3/](https://docs.python.org/3/)
- **Python asyncio Documentation**: [https://docs.python.org/3/library/asyncio.html](https://docs.python.org/3/library/asyncio.html)
- **VitePress Documentation**: [https://vitepress.dev/](https://vitepress.dev/) (The tool used to build this site)

### 9.4.3 Recommended Reading

- **"Why must a flowchart be a diagram?"** — The core article for understanding AmritaSense's design philosophy
- **"KISS Principle"**: Keep It Simple, Stupid—the design philosophy followed by AmritaSense
- **"Unix Philosophy"**: Small, focused, composable—the modular design foundation of AmritaSense
