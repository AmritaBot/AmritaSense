# Compose 契约：默认实现与扩展点

AmritaSense 区分**日常使用的具体组合类**与它们所实现的**抽象契约**。绝大多数代码中你不会接触到这些契约——`NodeCompose` / `NodeComposeRendered` 功能完备、从包根导出，已经够用。抽象基类只服务于两个更窄的目的：

1. **Mock（测试替身）** —— 在单元测试中伪造渲染图（或源组合），而无需真正构建一个工作流。
2. **扩展** —— 接入满足契约的自定义源组合或自定义渲染图。

本章说明二者关系、列出两个契约，并给出最小可运行示例。

## 默认实现 vs. 抽象契约

| 角色                                                                | 默认实现（日常使用）  | 抽象契约（Mock / 扩展）              |
| ------------------------------------------------------------------- | --------------------- | ------------------------------------ |
| **源组合** —— 用 `>>` 构建的有序节点列表，交给 `render()`           | `NodeCompose`         | `AbstractComposeOriginal`            |
| **渲染图** —— 编译后、带地址映射、由 `WorkflowInterpreter` 执行的图 | `NodeComposeRendered` | `AbstractCompose[AddressCalculator]` |

两个默认类都是**完整实现**——它们实现了完整的编译管线（`render()`、`_build()`、别名解析、地址计算），公共 API（`WorkflowInterpreter`、`FUN_BLOCK`、`BATCH_RUN` …）接受的就是它们。请把契约当作*规格说明*，而非替代品。

```python
# 日常用法——不涉及契约。
from amrita_sense import Node, WorkflowInterpreter


@Node()
def node_a(): ...


@Node()
def node_b(): ...


wf = node_a >> node_b  # 产生 NodeCompose（默认实现）
rendered = wf.render()  # NodeComposeRendered
pc = WorkflowInterpreter(rendered)
```

## 契约的位置

两个抽象类都位于 `amrita_sense.node.abc_base`：

```python
from amrita_sense.node.abc_base import (
    AbstractAddressCalculator,
    AbstractCompose,
    AbstractComposeOriginal,
)
```

- `AbstractComposeOriginal` —— **源组合**契约。
- `AbstractCompose[Calc_T]` —— **渲染图**契约，以绑定的地址计算器类型为泛型参数（`AbstractAddressCalculator[Compose_T]`）。
- `AbstractAddressCalculator[Compose_T]` —— 地址计算器契约（由 `AddressCalculator` 实现）。

### 源组合契约：`AbstractComposeOriginal`

任何源组合都应支持链式追加、遍历与一个构建器钩子：

- `__iter__()` —— 产出子节点 / 嵌套组合 / 自编译指令。
- `__rshift__(other)` —— 追加一个元素并返回 `self`。
- `get_builder()`（抽象类方法）—— 声明该源组合编译成哪种具体渲染图类（`AbstractCompose` 子类型）。`NodeCompose` 返回 `NodeComposeRendered`。
- `render()` —— 构建编译后的工作流图。标准管线通过 `get_builder()` 构造渲染图；`NodeCompose.render()` 是通常的入口。

### 渲染图契约：`AbstractCompose[Calc_T]`

这是运行时消费的接口——解释器、调试器与节点的 `_post_compile` 钩子只**读取**渲染图，从不构建或修改它。契约分为两个面：

读取面（运行时与钩子使用）：

- `calc` —— 绑定的地址计算器（`resolve_alias()`、`find_addr()`、`find_addr_safe()`、`advance()`）。
- `__getitem__(key)` / `__iter__()` / `__len__()` —— 按索引 / 顺序访问子条目。
- `__bool__()` —— 为空或尚未构建时返回 `False`。

构建面（`render()` 以及渲染器遇到嵌套源组合时使用）：

- `__init__(compose)` —— 由源组合构造渲染图。
- `_build(current_path, top)` —— 原地编译图；`current_path` / `top` 仅在顶层图时保持 `None`。

构建面的两个成员都是抽象的，因此任何源组合都能通过各自的 `get_builder()` 被渲染。Mock 只需实现被测到的成员——钩子测试的假图可以把 `_build` 做成空操作。

## 示例 1 —— 为 `_post_compile` 钩子 Mock 渲染图

许多内置节点在编译期的 `_post_compile(compose)` 中解析别名或校验地址。单元测试这类节点时，你不想构建整个工作流——只需要一个 `calc` 能回答别名查找的替身。

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
    """最小假渲染图：只实现运行时读取面。"""

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

    def _build(
        self,
        current_path: list[int] | None = None,
        top: AbstractCompose | None = None,
    ) -> None:
        """空操作：钩子测试从不渲染真实图。"""
        return None
```

把它喂给一个在 `_post_compile` 中通过 `compose.calc` 解析别名的节点：

```python
from amrita_sense.node import Node


def make_resolver(alias: str):
    addr: list[int] | None = None

    @Node()
    def call():
        return addr

    def _post_compile(compose):  # 签名与运行时的传参一致
        nonlocal addr
        addr = compose.calc.resolve_alias(alias)

    call._post_compile = _post_compile
    return call


node = make_resolver("target")
node._post_compile(FakeRendered({"target": [1, 2]}))
assert node() == [1, 2]
```

全程没有构建任何工作流、也没有构造 `NodeComposeRendered`——这个假图用少量小成员就满足了整个渲染图契约（其 `_build` 为空操作，因为钩子测试从不渲染）。

## 示例 2 —— 自定义源组合

实现了 `AbstractComposeOriginal` 的源组合可以嵌入更大的工作流。渲染器纯粹通过契约消费它——遍历子元素，并用 `get_builder()` 构造嵌套渲染图；它从不调用嵌套组合的 `render()`（该方法只是顶层入口）。

```python
from amrita_sense.node.abc_base import AbstractComposeOriginal
from amrita_sense.node.core import NodeComposeRendered


class RepeatTwice(AbstractComposeOriginal["NodeComposeRendered"]):
    """最小自定义源组合：每个子元素产出两次。"""

    def __init__(self, *nodes):
        self._nodes = list(nodes)

    def __iter__(self):
        for n in self._nodes:
            yield n
            yield n

    def __rshift__(self, other):
        self._nodes.append(other)
        return self

    @classmethod
    def get_builder(cls) -> type[NodeComposeRendered]:
        return NodeComposeRendered

    def render(self) -> NodeComposeRendered:
        rendered = type(self).get_builder()(self)
        rendered._build()
        return rendered


workflow = step1 >> RepeatTwice(step2, step3)  # 产生 NodeCompose（默认实现）
rendered = workflow.render()
```

`RepeatTwice(step2, step3)` 被渲染成一个嵌套 bubble，其内部图是 `step2, step2, step3, step3`——渲染器通过 `get_builder()` 构造嵌套容器，因此只要二者声明同一个构建器，`RepeatTwice` 就与 `NodeCompose` 被完全同等地处理。

## 与 `SelfCompileInstruction` 的关系

`SelfCompileInstruction` 是第三个扩展点，它负责*产出*源组合：其 `extract()` 返回 `AbstractComposeOriginal`（通常是 `NodeCompose`）。自定义指令请参见 [自定义指令集](./custom_instruction)；本章的契约用于 Mock 或替换*组合容器本身*。

## 经验法则

- **默认路径**：继续使用 `NodeCompose` / `NodeComposeRendered` —— 它们完整、已导出、值得推荐。
- **测试钩子 / 运行时**：实现 `AbstractCompose`（若 `calc` 需要回答查找，再实现 `AbstractAddressCalculator`），只实现被测成员。
- **新型容器**：需要不同的*源*容器时继承 `AbstractComposeOriginal`；需要不同的*渲染后*容器时实现 `AbstractCompose`。务必声明 `get_builder()`，渲染器才能知道你的源组合编译成哪种渲染图类。
- **读取面保持最小**：只实现测试真正用到的成员。由于 `__init__` / `_build` 已是渲染图契约的一部分，纯读取的假图（例如钩子测试）应把 `_build` 存根为空操作，而不是构建真实图。
