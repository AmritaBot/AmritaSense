# Project Introduction

## 1.1 Project Overview

### 1.1.1 What is AmritaSense?

**AmritaSense is the next-generation workflow engine**. It abandons traditional topological graph design and instead uses the **low-level execution model of a computer** to orchestrate and control workflows.

Unlike systems that require you to explicitly define nodes and edges and then rely on a scheduler to parse the graph structure, AmritaSense provides an **intuitive orchestration model** that lets developers focus entirely on the **logic of the flow itself** instead of being distracted by infrastructure adaptation.

You only need to compose nodes and control structures like ordinary Python code. The framework automatically compiles them into a linear instruction sequence, which is then executed by a lightweight “virtual machine.” This design gives AmritaSense unmatched expressive power and flexibility while keeping overhead extremely low.

### 1.1.2 Why choose AmritaSense?

We believe: **workflows should be designed for the work, not limited by the flow**. The “flow” is just a presentation form and should not become a shackle when you design logic.

- **Native Turing completeness**: You can express full, arbitrary control logic without manually defining complex boundary conditions inside the program. AmritaSense natively supports conditionals, loops, jumps, exception handling, and more without relying on an external graph engine or state machine.
- **Virtual machine addressing model**: AmritaSense uses a classic computer-style **addressing and execution model** (program counter + stack). All higher-level control flow is expanded into uniform pointer instructions at compile time. At runtime, only integer operations and function calls remain, so scheduling overhead is almost zero.
- **Built for AI agents and complex business logic**: Whether you are looping over tool calls, nesting subworkflows, suspending for user input, or recovering from exceptions, AmritaSense can express it directly and execute it very efficiently.

### 1.1.3 Core value proposition

- **Low-level execution model**: Use pointers + stack instead of topological graphs, resulting in a minimal runtime and far better performance than traditional graph engines.
- **Native Turing completeness**: IF, WHILE, DO-WHILE, GOTO, TRY… are all first-class and supported directly without simulation.
- **Focus on flow logic**: Say goodbye to complex edge definitions and state dictionaries, and focus on the business process that really matters.
- **Declarative dependency injection**: Nodes declare required parameters through function signatures, and the framework resolves them automatically with type safety.
- **Async-first with suspend/resume**: Native async/await support lets workflows suspend between nodes and resume precisely.
- **Ultra lightweight**: The core engine is only a few thousand lines of code and contains no heavy abstractions, so it can be embedded in any Python project.
