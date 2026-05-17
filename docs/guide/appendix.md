# Appendix and Resources

## 9.1 Glossary

### 9.1.1 Workflow

In AmritaSense, a workflow is an asynchronously executed sequence of nodes arranged in a specific order. It is not a static graph structure; it is an instruction sequence that the interpreter can step through, with support for interrupts and jumps.

### 9.1.2 Node

The smallest execution unit in a workflow. Any Python function or coroutine decorated with `@Node()` is a node. Nodes are atomic — they either execute completely or not at all. Conditionals, loop bodies, and exception handlers are all nodes.

### 9.1.3 PointerVector

AmritaSense's core addressing data structure. It is a variable-length integer array where each dimension corresponds to a nested level, and the value at that dimension represents the offset index within that level. In the interpreter loop, `PointerVector` acts as the program counter (PC), always pointing to the node currently being executed.

### 9.1.4 Bubble

A group of nodes wrapped in parentheses `()` forms an isolated address space after compilation. Each bubble has its own `near` address space, and jumps inside it do not affect outer scopes. Bubbles are the underlying mechanism AmritaSense uses to implement scope isolation and data encapsulation.

### 9.1.5 Instruction Set

AmritaSense provides a complete set of control flow primitives, including `IF/ELIF/ELSE` (conditional branching), `WHILE/DO-WHILE` (loops), `GOTO` (unconditional jumps), `CALL` (subroutine calls), `TRY/CATCH/THEN/FIN` (exception handling), `NOP` (sentinel), and `INTERRUPT` (forced stop). All instructions are expanded into underlying node compositions at compile time and executed via pointer jumps at runtime.

### 9.1.6 Self-Compile Instruction

Instruction classes that implement the `SelfCompileInstruction` interface. During the `render()` stage, they automatically expand into standard `NodeCompose` structures via the `extract()` method. Both built-in and user-defined instructions use this mechanism to achieve compile-time optimization and zero runtime overhead.

### 9.1.7 Interrupt

A cooperative interrupt mechanism provided by AmritaSense. Workflows suspend at designated breakpoints and hand control back to the external system. During this window, the external system can inspect state, modify variables, and then resume execution with `resume()`. This is the foundation for building debuggers and external monitoring systems.

### 9.1.8 Depends

A dependency injection pattern inspired by FastAPI. Nodes declare required resources through `Depends(factory)` in their function signatures. AmritaSense's dependency resolution system supports concurrent resolution, runtime injection, and type matching. If a factory function returns `None`, the workflow terminates immediately.

### 9.1.9 Alias

A globally unique symbolic name bound to a node via the `ALIAS` instruction. It is registered in `alias2vector_map` at compile time and resolved at runtime by `GOTO` and `CALL`. This is the basis of AmritaSense's symbolic addressing system.

### 9.1.10 Subprogram

A sequence of nodes defined by the `ARCHIVED_NODES` instruction, skipped by `SubprogramJumpNode`, and only accessed via `CALL` or external injection. Subprograms can contain interrupt handling logic, debugging utilities, or reusable modules without affecting normal execution flow.

### 9.1.11 Other Core Terms

- **Interpret Lock**: an `aiologic.Lock` instance that ensures only one node executes at a time; it is the mutex foundation for safe external calls.
- **Jump Mark**: the `_jump_marked` flag. When `True`, the interpreter skips the regular pointer advancement step and starts the next round from the jump target.
- **Exception Penetration**: exceptions marked by `exception_ignored` are not caught by any `CATCH` block and propagate to the top-level handler.
- **Call Stack**: a `Stack[PointerVector]` that manages return addresses for subroutine calls.

### 9.1.12 Acronyms

- **API**: Application Programming Interface
- **DI**: Dependency Injection
- **PC**: Program Counter
- **JSON**: JavaScript Object Notation
- **HTTP**: Hypertext Transfer Protocol
- **LGPL**: GNU Lesser General Public License
- **ISA**: Instruction Set Architecture

## 9.2 Project Resources

### 9.2.1 GitHub Repositories

- **AmritaSense repository**: [https://github.com/AmritaBot/AmritaSense](https://github.com/AmritaBot/AmritaSense)
- **AmritaCore repository**: [https://github.com/AmritaBot/AmritaCore](https://github.com/AmritaBot/AmritaCore)
- **Issue reporting**: file bug reports and feature requests in the appropriate repository
- **Pull requests**: contributions via PRs are welcome

### 9.2.2 Official Websites

- **AmritaSense documentation**: [https://sense.amritabot.com](https://sense.amritabot.com)
- **AmritaCore documentation**: [https://core.amritabot.com](https://core.amritabot.com)
- **Guides and tutorials**: each documentation site provides complete guides and API references

### 9.2.3 Contribution Guide

Contributions to AmritaSense are welcome. Follow this workflow:

1. Fork the repository
2. Create a branch for your changes
3. Add tests to ensure existing functionality is not broken
4. Update documentation to match code changes
5. Submit a pull request with a clear description

**Code style guidelines**:

- follow PEP 8 Python style conventions
- document public functions and classes with docstrings
- use type hints for function parameters and return values
- keep functions focused and concise
- core business logic should be hand-authored

For more details, see the `CONTRIBUTING.md` file in each repository.

### 9.2.4 License

- **AmritaSense**: released under LGPL v2
- **AmritaCore**: released under MIT

See each repository's `LICENSE` file for the full license text.

## 9.3 Community and Support

### 9.3.1 Discussions and Feedback

- **Discord**: [https://discord.gg/byAD3sbjjj](https://discord.gg/byAD3sbjjj)
- **QQ group**: 1006893368
- **GitHub Discussions**: participate in technical conversations on the repository discussion board

### 9.3.2 Issue Reporting

When reporting an issue, follow these steps:

1. Search existing issues to avoid duplicates
2. Provide a clear, descriptive title
3. Include complete reproduction steps and code snippets
4. Specify the runtime environment (OS, Python version, library versions)

### 9.3.3 Code of Conduct

The Amrita community follows a contributor covenant-style code of conduct:

- **Respect others**: treat everyone with courtesy and consideration
- **Be constructive**: give feedback that helps improve the project
- **Be inclusive**: welcome contributors from diverse backgrounds
- **Focus on quality**: strive to improve the project through thoughtful work

## 9.4 Design Philosophy and Related Resources

### 9.4.1 Design Philosophy

- **Everything is a node**: conditionals, loop bodies, and exception handlers are all instances of `Node`
- **Instructions instead of graphs**: workflows are nonlinear execution flows over a linear node array, where jumps rewrite the pointer
- **Simplicity is truth**: implement complete control flow with minimal code

### 9.4.2 Related Resources

- **Python official docs**: [https://docs.python.org/3/](https://docs.python.org/3/)
- **Python asyncio docs**: [https://docs.python.org/3/library/asyncio.html](https://docs.python.org/3/library/asyncio.html)
- **AmritaCore docs**: [https://core.amritabot.com](https://core.amritabot.com)
- **VitePress docs**: [https://vitepress.dev/](https://vitepress.dev/)

### 9.4.3 Recommended Reading

- “Why flowcharts need not be graphs” — a core article for understanding AmritaSense design
- “KISS principle” — Keep It Simple, Stupid, the design philosophy guiding AmritaSense
- “Unix philosophy” — small, focused, composable tools as the basis of modular design
