# SuspendObjectStream

`SuspendObjectStream` is a generic asynchronous stream helper for cooperative suspend/resume workflows. It provides a duplex interface for pushing objects, yielding responses, and coordinating suspend points with an external controller.

## Overview

`SuspendObjectStream[ObjectTypeT]` combines an async send queue, an async receive queue, and a suspend/resume coordination mechanism.

It is designed to be used as the `object_io` implementation for `WorkflowInterpreter` or as a standalone stream object in custom runtime integrations.

Key behaviors:

- suspend execution at configurable tags using `wait_to_suspend()` and `_wait_for_continue()`
- resume internal execution using `resume()`
- send response objects through `yield_response()` or `push_object()`
- consume response objects with `get_response_generator()`

### Concurrency Safety (v0.3.2+)

`SuspendObjectStream` is fully concurrency-safe. Multiple coroutines and threads can safely share a single instance — calling `wait_to_suspend()`, `resume()`, `yield_response()`, and `push_object()` concurrently is protected by the **CLCA (Cross Loop Callback-Allocate) signal design pattern**. See [CLCA Design Pattern](/guide/practice/clca-design-pattern) for details.

## Public methods

### `static suspend(func: Callable[..., Any], tag: str | None = None) -> Callable[..., Any]`

A decorator for coroutine functions that require a suspend point before execution. The decorated function must accept a `SuspendObjectStream` instance in its arguments.

### `static suspend_with_tag(tag: str)`

Return a decorator that applies `SuspendObjectStream.suspend()` with a fixed tag filter.

### `async wait_to_suspend(*tags: str, timeout: float | None = None)`

Request suspension and wait until the next matching suspend point is reached.

- `tags`: optional suspend tags to filter which breakpoints will pause execution.
- `timeout`: optional timeout in seconds.

### `resume()`

Resume execution after a suspend point.

### `queue_closed() -> bool`

Return `True` if the response queue has been closed.

### `async set_queue_done()`

Mark the response queue done by sending a done marker. Once done, no further responses may be sent.

### `async push_object(obj: ObjectTypeT)`

Push an object into the stream queue. This method waits for the special yield suspend tag before sending.

### `async yield_response(response: ObjectTypeT)`

Send a response object to the stream consumer. If a callback is configured, it will be invoked instead of queue delivery.

### `set_callback_func(func: CALLBACK_TYPE)`

Set a callback to handle emitted responses on the producer side.

### `set_callback_fun_sending(func: CALLBACK_TYPE)`

Set a callback to handle responses sent for the producer.

### `async yield_response_iteration(iterator: AsyncGenerator[ObjectTypeT, None])`

Iterate over an async generator and send every yielded item through `yield_response()`.

### `get_response_generator() -> AsyncGenerator[ObjectTypeT, None]`

Return an async generator that iterates over response objects until the done marker is reached.
