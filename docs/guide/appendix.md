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

A complete set of control flow primitives provided by AmritaSense, including `IF/ELIF/ELSE` (conditional branching), `WHILE/DO-WHILE` (loops), `JMP` (unconditional jump), `INVOKE` (subroutine call), `TRY/CATCH/THEN/FIN` (exception handling), `NOP` (sentinel), and `RESET` (forced termination). All instructions are expanded into low-level node compositions at compile time and completed through pointer jumps at runtime.

### 9.1.6 Self-Compile Instruction

An instruction class that implements the `SelfCompileInstruction` interface. During the `render()` phase, they are automatically expanded into standard `NodeCompose` structures through the `extract()` method. Both built-in instructions and developer-defined custom instructions are based on this mechanism, achieving compile-time optimization and zero runtime overhead.

### 9.1.7 Compose Contract

A _composition_ in AmritaSense is described by two abstract contracts in `amrita_sense.node.abc_base`: `AbstractComposeOriginal` (a source composition — iterable, chainable, renderable) and `AbstractCompose[AddressCalculator]` (a rendered graph — read-only, indexable, with a bound `calc`). The concrete classes you use in daily code — `NodeCompose` and `NodeComposeRendered` — are the **default implementations** of these contracts and are fully featured. The abstract contracts exist for mocking and extension: anything satisfying a contract can be consumed by the renderer or `WorkflowInterpreter`. See [Compose Contracts](/guide/advanced/compose-contracts).

### 9.1.8 Interrupt

A cooperative suspension mechanism provided by AmritaSense. The workflow actively suspends at specified markers, yielding control back to the external system. The external system can inspect state and modify variables during this window, then resume execution via `resume()`. This is the foundational capability for building debuggers and external monitoring systems.

### 9.1.9 Depends (Dependency Injection)

A dependency injection pattern inspired by FastAPI. Nodes declare the resources they need by declaring `Depends(factory)` in their function signatures. AmritaSense's dependency resolution system supports concurrent resolution, runtime injection, and type matching. If a factory function returns `None`, the workflow will terminate immediately.

### 9.1.10 Alias

A globally unique symbol name bound to a node via the `ALIAS` instruction. Registered into `alias2vector_map` at compile time for `JMP` and `INVOKE` to look up and resolve at runtime. This is the foundation of AmritaSense's symbolic addressing system.

### 9.1.11 Subprogram

A sequence of nodes defined by the `ARCHIVED_NODES` instruction, skipped by `SubprogramJumpNode`, and accessible only through `INVOKE` or external injection. Subprograms can store interrupt handling logic, debugging tools, or reusable functional modules without affecting the normal execution flow. For archiving a full node composition (e.g. function bodies), use `ARCHIVED_SEGMENT` instead; `FN` / `INTER_FN` build on it to define named function blocks (see [Function Block Call](/guide/advanced/function-block-call)).

### 9.1.12 Other Core Terminology

- **Interpret Lock**: An `aiologic.Lock` instance that guarantees only one node is executing at a time, forming the mutual exclusion basis for safe external invocation.
- **Jump Mark**: The `_jump_marked` flag. When `True`, the interpreter skips the regular pointer advancement step and the next cycle starts from the jump target.
- **Exception Penetration**: Exceptions marked via `exception_ignored` cannot be caught by any `CATCH` block and propagate directly to the top-level handler.
- **Call Stack**: `Stack[PointerVector]`, managing return addresses for subroutine calls.
- **DI Cache** (v0.4.2+): `DICache` — an LRU-based cache inside `WorkflowInterpreter` that stores resolved dependency injection kwargs. Keyed by `hash((id(node.func), args_hash))` (since v0.6.0), it avoids redundant DI resolution when the same node function is revisited with the same argument types. The payload is an `LRUCache` with max 2048 entries. Controlled via unsafe flags `WORKFLOW_DI_NO_CACHE`, `WORKFLOW_DI_PRELOAD_CACHE`, and `WORKFLOW_DI_PRELOAD_BATCH`.
- **Address Calculator** (v0.4.4+): `AddressCalculator` — a stateless address computation utility exposed via `NodeComposeRendered.calc`. Provides `advance()`, `resolve_alias()`, `find_addr()`, and `find_addr_safe()` methods. Encapsulates pointer advancement logic previously held in the interpreter's `_ptr_cache`.
- **Debugger** (v0.5.0+): A REPL-first, pure-function debugging toolkit provided by the `amrita_sense.debugger` module. Includes state inspection (`inspect`, `where`, `backtrace`, `list_nodes`, `list_sub_intp`), step control (`step`, `step_over`, `step_out`, `cont`), and breakpoint management (`break_at_tag`, `break_at_addr`, `clear_break_*`, `list_breaks`). Injected via composite middleware without modifying the core runtime. Sync functions are callable directly in a REPL without `await`.
- **Breakpoint** (v0.5.0+): An execution pause point marked on a specific node tag or address. Set via `amrita_sense.debugger`'s `break_at_tag()` and `break_at_addr()`, with support for conditional expressions (`condition` parameter). When hit, raises `BreakpointHit` (inherits `BaseException`, not `Exception`, avoiding the panic mechanism), caught by `cont()` to pause execution.

### 9.1.13 Abbreviations

- **API**: Application Programming Interface
- **DI**: Dependency Injection
- **PC**: Program Counter
- **JSON**: JavaScript Object Notation
- **HTTP**: Hypertext Transfer Protocol
- **ISA**: Instruction Set Architecture

### 9.1.14 Primitive

**Primitive** is a core concept in computer architecture, referring to the **smallest indivisible operation unit** defined within a processor's Instruction Set Architecture (ISA). In an ISA, primitives dictate the most fundamental capabilities a processor can execute—such as addition, data loading, conditional branching—and all complex programs are ultimately composed of these primitives. Primitives define "what the hardware can do"; software achieves arbitrarily complex logic through the combination of primitives.

In AmritaSense, **workflows are similarly built upon a set of primitives**:

- **Nodes are execution primitives**: Every function wrapped by `@Node()` is an indivisible atomic execution unit. The interpreter will not interrupt execution inside a node; a node either runs completely or not at all.
- **Instructions are control flow primitives**: `IF`, `JMP`, `INVOKE`, `TRY`, and other instructions are the smallest semantic units of flow control. They define the most basic control flow operations the interpreter can execute—conditional jump, unconditional jump, subroutine call, exception capture.
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

## 9.5 Deprecated Instruction Names (1.0.0)

A rendered workflow graph *is* an address-mapped instruction sequence, so the disassembler in `amrita_sense.debugger` has always printed CPU-style mnemonics. AmritaSense 1.0.0 renamed the public instructions so that the API and the disassembly finally speak the same language.

### 9.5.1 Rename Table

| Old (≤ 0.8)                     | New (1.0+)                                | Kind     | Old name still importable | Notes                                          |
| ------------------------------- | ----------------------------------------- | -------- | ------------------------- | ---------------------------------------------- |
| `GOTO`                          | `JMP`                                     | function | ✅                        | drop-in                                        |
| `PUSH_STACK`                    | `PUSH_RET`                                | function | ✅                        | drop-in                                        |
| `RET_FAR`                       | `RET`                                     | function | ✅                        | drop-in                                        |
| `PUSH_AND_GOTO(from_adr, to_adr)` | `CALL(to_adr, *, from_adr=None)`        | function | ✅                        | **argument order changed**                     |
| `CALL`                          | `INVOKE`                                  | function | ❌                        | **no alias — breaks silently, see below**      |
| `INTERRUPT_INTO`                | `INT`                                     | function | ✅                        | drop-in                                        |
| `INTERRUPT_RET`                 | `IRET`                                    | function | ✅                        | drop-in                                        |
| `INTERRUPT`                     | `RESET`                                   | constant | ✅                        | drop-in, **no static warning**                 |
| `INTERRUPT_KEEP_CTX`            | `SUSPEND`                                 | constant | ✅                        | drop-in, **no static warning**                 |
| `CallNode`                      | `InvokeNode`                              | class    | ✅                        | drop-in                                        |

`ALIAS` deliberately keeps its name: the runtime vocabulary is alias-based throughout (`alias2vector_map`, `AddressCalculator.resolve_alias`, `AliasNotFoundError`), and an `AliasNode` is an *addressable node occupying a real slot* — calling it `LABEL` would be both inconsistent and inaccurate, since an assembly `LABEL` is zero-width.

### 9.5.2 ⚠️ `CALL` Changes Meaning Silently

This is the only rename without a compatibility alias, and it is the one to look at twice.

The old `CALL(alias)` performed a single-step `call_sub`. That name was taken over by the far-call instruction, so `CALL(alias)` now means "push a return address and jump" — **it will not raise, it will just do something else**. The old behaviour is now `INVOKE(alias)`.

Audit your code with:

```bash
grep -rn '\bCALL(' --include='*.py'
```

Then change every old `CALL(x)` to `INVOKE(x)`.

### 9.5.3 ⚠️ Constants Have No Static Deprecation Warning

`INTERRUPT` and `INTERRUPT_KEEP_CTX` are module-level *constants*, not functions. PEP 702 (`@deprecated`) has no decorator form for variables, so the type checker cannot flag them: they are silent aliases. If you use them, grep manually:

```bash
grep -rn '\bINTERRUPT\b' --include='*.py'
```

The function renames in the table above *do* carry static markers, so a type checker reports them once `reportDeprecated` is enabled:

```toml
[tool.pyright]
reportDeprecated = "warning"   # off by default
```

### 9.5.4 ⚠️ `BuiltinTags` String Values Changed

The `BuiltinTags` members mirroring the renamed instructions now carry new values, and the old member names are kept as same-value aliases (`BuiltinTags.RET_FAR is BuiltinTags.RET`). Aliases appear in `__members__` but not in `list(BuiltinTags)`.

| Member (old)     | Member (new) | Value (old)            | Value (new)    |
| ---------------- | ------------ | ---------------------- | -------------- |
| `RET_FAR`        | `RET`        | `"__RET_FAR__"`        | `"__RET__"`    |
| `PUSH_STACK`     | `PUSH_RET`   | `"__PUSH_STACK__"`     | `"__PUSH_RET__"` |
| `PUSH_AND_GOTO`  | `CALL`       | `"__PUSH_AND_GOTO__"`  | `"__CALL__"`   |
| `INTERRUPT_INTO` | `INT`        | `"__INTERRUPT_INTO__"` | `"__INT__"`    |
| `INTERRUPT_RET`  | `IRET`       | `"__INTERRUPT_RET__"`  | `"__IRET__"`   |

Comparing against the enum members keeps working; hard-coding the old tag *strings* does not.

### 9.5.5 Disassembly Mnemonics

`dis()` output changed along with the names:

| Instruction            | Old mnemonic             | New mnemonic                    |
| ---------------------- | ------------------------ | ------------------------------- |
| `JMP`                  | `JMP`                    | `JMP` (unchanged)               |
| `PUSH_RET`             | `PUSH`                   | `PUSH` (unchanged)              |
| `RET`                  | `RET_FAR`                | `RET`                           |
| `CALL`                 | `CALL.FAR from -> to`    | `CALL to, ret=from`             |
| `INVOKE`               | `CALL sym -> [0]`        | `INVOKE sym -> [0]`             |
| `INT`                  | `INTINTO jmp -> ret`     | `INT jmp, ret=ret`              |
| `IRET`                 | `INTERRUPT_RET`          | `IRET`                          |
| `RESET`                | `INT`                    | `RESET`                         |
| `SUSPEND`              | `INT.KEEP`               | `SUSPEND`                       |
| `PUSH_CONTEXT`         | `PUSHCTX`                | `PUSHCTX` (unchanged)           |
| `ALIAS`                | `ALIAS sym`              | `ALIAS sym` (unchanged)         |

### 9.5.6 Removal Schedule

Every alias in this section is deprecated and will be **removed in 2.0**. Deep import paths such as `from amrita_sense.instructions.ret2 import PUSH_STACK` keep working through plain aliases next to each replacement, but those aliases carry no static marker — prefer the top-level `amrita_sense` or `amrita_sense.instructions` imports.
