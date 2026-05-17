# 编排与运行

## 3.1.1 节点

在 AmritaSense 中，声明节点的常用方式是使用`@Node()`装饰器。例如：

```python
@Node()
def my_fun():...
```

`Node()`装饰器接受三个参数：

```python
def Node(
    tag: str | None = None,
    wrap_to_async: bool = True,
    address_able: bool = True,
):...
```

**这里分别作出解释：**

- `tag`：节点的标签，用于**标识**节点，用于外部断点调试与可视化，详情请见[执行与中断](/zh/guide/concepts/exec_and_interrupt)。这里只需要直到`tag`可以重复。
- `wrap_to_async`：是否将**同步函数**转换为异步函数。
- `address_able`：是否允许节点被其他节点引用（通过`ALIAS`，后为会讲到）。

使用`@Node()`装饰器会返回一个`Node`对象，`Node`事实上是一个带有函数元信息的包装类，集成自BaseNode，实现了`__call__`方法的函数包装对象。并且它也可以作为普通函数使用，函数签名来自函数本身。

那么我们如何把节点串起来呢？这里引入了编排的概念。

## 3.1.2 编排

单个节点当然不能直接执行，我们需要进行编排；编排是把节点串起来，并定义节点之间的位置关系。在 AmritaSense 中，我们可以使用`>>`运算符来定义节点之间的排布顺序，例如：

```python
compose: NodeCompose = node1 >> node2
```

在得到编排之后，我们下一步需要进行的就是**渲染**（或者说“编译”）。由于`.render()`返回一个新的对象`NodeComposeRendered`，因此，这一步需要单独分配一个变量，并赋值：

```python
comp_rendered: NodeComposeRendered = compose.render()
```

到这里，前期准备工作就完成了，下一步，我们要让它运行起来。

## 3.1.3 运行

渲染后的编排事实上只是一个**含有节点的数据容器**，执行需要引入解释器，我们在这里引入`WorkflowInterpreter`的概念。不过，继续之前，让我们先来解析下解释器的构造函数：

```python
def __init__(
    self,
    node_compose: NodeComposeRendered | SelfCompileInstruction,
    object_io: SuspendObjectStream[Any] | None = None,
    *,
    exception_ignored: tuple[type[BaseException], ...] = (),
    extra_args: tuple = (),
    extra_kwargs: dict[str, Any] | None = None,
    addr_stack: Stack[PointerVector] | None = None,
):...
```

### `'*'`前参数

- `node_compose`: 节点组合，可以是 `NodeComposeRendered` 或 `SelfCompileInstruction`(你在现在不需要了解到自编译指令是什么，我们在后面高级教程中会介绍，只需要知道`IF()`,`WHILE`这些控制流指令都是`SelfCompileInstruction`，它会自动展开为节点组合)。
- `object_io`: 对象输入输出流，用于处理对象输入，见[AmritaCore-IOStream](https://core.amritabot.com/zh/guide/api-reference/classes/SuspendObjectStream.html)。

### `'*'`后参数

这些参数只能通过kwargs传入，不能通过args传入。

- `exception_ignored`: 传入一个元组，包含要被忽略的异常类型。被忽略的异常类型在内部的异常捕捉链中**不会被捕获**，会被重新抛出。它的默认值是`(InteruptNotice,BreakLoop)`。
- `extra_args`: 传入一个元组，包含额外的参数。这些参数会通过类型绑定依赖注入的方式传递给内部函数。
- `extra_kwargs`: 传入一个字典，包含额外的关键字参数。这些参数会通过类型绑定依赖注入的方式传递给内部函数。

有关依赖注入相关内容会在[后文](#314-依赖声明)提及。

### 执行工作流

事实上它有两种方式：

1. 使用 `run()` 方法运行完整的工作流。
2. 使用 `run_step_by()` 以异步生成器作为时钟周期的方式逐节点运行。

例如：

```python
inter = WorkflowInterpreter(...)
if __name__ == '__main__':
    inter.run()
# 或者是：
async def main():
    inter = WorkflowInterpreter(...)
    async for resp in inter.run_step_by():
        # resp事实上能得到各个节点的输出
        ...

if __name__ == '__main__':
    asyncio.run(main())
```

## 3.1.4 依赖声明

这是一个较为抽象的概念，但如果您使用过`FastAPI`或者`NoneBot2`这样类似的框架，那么您就能够很快理解到`AmritaSense`中依赖的工作方式，如果没有，也没关系，让我们逐步展开。

**简单来说**：节点函数的参数需要从外部获得值，这些值可以是常数、其他节点的输出，或者由 `WorkflowInterpreter` 提供的全局依赖。`AmritaSense` 会根据参数的类型和名字自动帮你填充。

### 什么被视为“依赖”？

假设你有一个函数`my_fun`，它的定义如下：

```python
async def my_fun(a: int, b: int) -> int:
    return a + b
```

在这个函数中，它依赖`a`与`b`两个参数，并且返回一个整数。我们称这两个**形式参数**的声明为**依赖**

事实上，依赖注入和匹配的过程可以被抽象地理解为**给予的参数被动态绑定**的过程。

我们接下来介绍如何传入参数。

### 传参与绑定

参数通过`WorkflowInterperter`构造函数的`extra_args`与`extra_kwargs`参数传入。它们的作用是什么？

- `extra_args`: 可用的位置参数实参，通过**参数的类型**与**函数的参数类型**进行匹配。
- `extra_kwargs`: 可用的关键字参数实参，通过**参数名**与**函数的参数名**进行匹配。并且优先级高于`extra_args`，并且不能进行类型匹配。

::: tip
在执行中，有任何一个参数解析失败都将导致工作流中止。
:::

还是有些抽象吧，举个例子：

```python
# 假设你现在有一个叫a的参数元组,和一个叫b的参数字典
a = (MyType(),MyOtherType())
b = {"arg":MyOtherType()}
# 定义一个节点my_func
@Node()
def my_func(arg: MyType):...

interpreter = WorkflowInterpreter(my_func>>NOP,extra_args=a,extra_kwargs=b)

...
```

在这个例子中，虽然`arg`的类型是`MyType`，并且参数元组中也有一个`MyType`参数，但是`extra_args`中第一个参数是`MyOtherType`，所以`arg`会被`extra_args`中的第一个参数替换。

来看看第二个例子：

```python
from amrita_sense.instructions import NOP # 导入NOP
# 假设你现在有一个叫a的参数元组,和一个叫b的参数字典
a = (MyOtherType(),)
b = {"other_arg":MyType()}
# 定义一个节点my_func
@Node()
def my_func(arg: MyType):...

interpreter = WorkflowInterpreter(my_func>>NOP,extra_args=a,extra_kwargs=b)

...
```

这个程序会报错。因为`extra_kwargs`的参数不能进行类型匹配，并且`extra_args`的参数中不存在同类型的参数。

::: warning
值的注意的是，函数签名中不能使用`*args`和`**kwargs`，这会导致参数无法进行匹配。
同时，对于使用`extra_args`注入的参数，则**必须**在形式参数中声明类型，否则将以报错结束。
:::
