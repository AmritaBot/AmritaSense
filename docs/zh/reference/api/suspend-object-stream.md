# SuspendObjectStream

`SuspendObjectStream` 是一个通用的异步流工具，支持协作式挂起/恢复控制流程。它提供双工接口，用于推送对象、产出响应，以及与外部控制器协调挂起点。

## 概述

`SuspendObjectStream[ObjectTypeT]` 组合了异步发送队列、异步接收队列和挂起/恢复协调机制。

它既可以作为 `WorkflowInterpreter` 的 `object_io` 实现，也可以在自定义运行时集成中单独使用。

核心能力：

- 通过 `wait_to_suspend()` / `_wait_for_continue()` 在可配置标签处挂起执行
- 使用 `resume()` 恢复被挂起的执行
- 通过 `yield_response()` 或 `push_object()` 发送响应对象
- 使用 `get_response_generator()` 消费响应对象

## 公共方法

### `static suspend(func: Callable[..., Any], tag: str | None = None) -> Callable[..., Any]`

用于协程函数的装饰器，在执行前插入挂起点。被装饰的函数必须在参数中包含一个 `SuspendObjectStream` 实例。

### `static suspend_with_tag(tag: str)`

返回一个装饰器，使用固定标签调用 `SuspendObjectStream.suspend()`。

### `async wait_to_suspend(*tags: str, timeout: float | None = None)`

请求挂起并等待下一个匹配的挂起点。

- `tags`：可选的挂起标签，用于筛选会触发的断点。
- `timeout`：可选超时时间，单位秒。

### `resume()`

恢复挂起后的执行。

### `queue_closed() -> bool`

如果响应队列已关闭，则返回 `True`。

### `async set_queue_done()`

通过发送完成标记将响应队列标记为完成。完成后不能再发送新的响应。

### `async push_object(obj: ObjectTypeT)`

将对象推入流队列。此方法会等待特殊的产出挂起标签后再发送。

### `async yield_response(response: ObjectTypeT)`

将响应对象发送到流消费者。如果已配置回调，则会调用回调而不是通过队列交付。

### `set_callback_func(func: CALLBACK_TYPE)`

设置用于处理生产端产出响应的回调函数。

### `set_callback_fun_sending(func: CALLBACK_TYPE)`

设置用于发送端响应的回调函数。

### `async yield_response_iteration(iterator: AsyncGenerator[ObjectTypeT, None])`

遍历异步生成器，并通过 `yield_response()` 发送每个产出项。

### `get_response_generator() -> AsyncGenerator[ObjectTypeT, None]`

返回一个异步生成器，迭代响应对象直到遇到完成标记。
