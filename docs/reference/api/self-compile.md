# Self-Compile Instructions

Self-compile instructions are a special extension point that can expand into executable node compositions at render time.

## SelfCompileInstruction

`SelfCompileInstruction` is an abstract base class for instructions that can compile themselves into a workflow fragment.

```python
class SelfCompileInstruction(ABC):
    @abstractmethod
    def extract(self) -> NodeCompose: ...
```

When a `SelfCompileInstruction` is encountered during `NodeCompose.render()`, the interpreter calls `extract()` to obtain a `NodeCompose` fragment. That fragment is then rendered and inserted into the final workflow graph.

This allows developers to implement custom control flow constructs that appear as first-class instructions during composition, while still executing as ordinary nodes at runtime.

## Typical use

- build reusable higher-level workflow primitives
- expand domain-specific instructions into standard `NodeCompose` patterns
- preserve runtime performance by resolving structure during render time

Example:

```python
class CustomInstruction(SelfCompileInstruction):
    def extract(self):
        return NodeCompose(
            Node(lambda: ...),
            Node(lambda: ...),
        )
```

When `CustomInstruction()` appears in a composition, its extracted nodes become part of the rendered graph.
