import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from functools import wraps
from typing import Any, Generic, TypeAlias, TypeVar

import aiologic
import anyio
from anyio.abc import ObjectReceiveStream, ObjectSendStream
from typing_extensions import LiteralString

ObjectTypeT = TypeVar("ObjectTypeT")
CALLBACK_TYPE: TypeAlias = Callable[[ObjectTypeT], Awaitable[Any]]
SUSPEND_ON_YIELD: LiteralString = "SuspendObjectStream::yield_response"


class SuspendObjectStream(Generic[ObjectTypeT]):
    """
    A class for objects that can be suspended and resumed.

    This implements a duplex asynchronous stream: the producer can suspend and
    resume execution while sending items, and a single consumer receives those
    items. The stream supports bidirectional control flow for suspend/resume
    coordination.
    """

    __done_marker = object()

    # Suspension-related attributes
    __suspend_signal: asyncio.Future | None = None
    __resume_signal: asyncio.Future | None = None
    _suspend_tags: tuple[str, ...] | None = None

    # Callback-related attributes
    _callback_fun: CALLBACK_TYPE | None = None
    _callback_lock: aiologic.Lock
    _callback_fun_sending: CALLBACK_TYPE | None = None
    _callback_sending_lock: aiologic.Lock

    # Stream-related attributes
    _send_stream: ObjectSendStream
    _receive_stream: ObjectReceiveStream

    # Queue state attributes
    _queue_done: bool = False
    _has_consumer: bool = False
    _q_tout: float | None

    # Concurrency control
    _state_lock: aiologic.Lock

    def __init__(
        self,
        /,
        queue_size: int = 45,
        queue_timeout: float | None = 10.0,
        callback: CALLBACK_TYPE | None = None,
        receive_callback: CALLBACK_TYPE | None = None,
    ) -> None:
        self._send_stream, self._receive_stream = anyio.create_memory_object_stream(
            max_buffer_size=queue_size
        )
        self._callback_fun = callback
        self._callback_lock = aiologic.Lock()
        self._callback_fun_sending = receive_callback
        self._callback_sending_lock = aiologic.Lock()
        self._q_tout = queue_timeout
        self._state_lock = aiologic.Lock()

    @staticmethod
    def suspend(func: Callable[..., Any], tag: str | None = None) -> Callable[..., Any]:
        """Decorator for suspend. (Only be used for a time-costly function)"""
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"{func.__name__} is not a coroutine function.")

        @wraps(func)
        async def wrapper(*args, **kwargs):
            chat_object = None
            for arg in args:
                if isinstance(arg, SuspendObjectStream):
                    chat_object = arg
                    break
            if chat_object is None:
                for value in kwargs.values():
                    if isinstance(value, SuspendObjectStream):
                        chat_object = value
                        break
            if chat_object is None:
                raise TypeError(
                    f"No SuspendObjectStream parameter found in function '{func.__name__}'. "
                    f"Args types: {[type(a).__name__ for a in args]}, "
                    f"Kwargs keys: {list(kwargs.keys())}"
                )

            await chat_object._wait_for_continue(tag)
            return await func(*args, **kwargs)

        return wrapper

    @staticmethod
    def suspend_with_tag(tag: str):
        """Decorator for suspend with tag filter. Used in inner function.

        Args:
            tag (str): Tag for break point.
        """

        return lambda func: SuspendObjectStream.suspend(func, tag)

    async def _wait_for_continue(self, tag: str | None = None) -> bool:
        """Break point for suspend.

        Multiple waiters share a single ``__resume_signal`` Future via
        ``add_done_callback`` to avoid one-waiter-only limitation.

        Args:
            tag: Tag for break point.  Matched against ``_suspend_tags``.

        Returns:
            True if the call actually waited (suspended), False otherwise.
        """
        async with self._state_lock:
            if self.__suspend_signal is None:
                return False
            if self._suspend_tags:
                if tag is None or tag not in self._suspend_tags:
                    return False

            if self.__resume_signal is not None and not self.__resume_signal.done():
                # Another waiter is already waiting — attach callback.
                shared_fut = self.__resume_signal
                is_first = False
            else:
                # First waiter — create the shared resume Future.
                if not self.__suspend_signal.done():
                    self.__suspend_signal.set_result(True)
                self.__resume_signal = asyncio.Future()
                shared_fut = self.__resume_signal
                is_first = True

            await asyncio.sleep(0)

            if is_first:
                fut = shared_fut
            else:
                fut: asyncio.Future[None] = asyncio.Future()
                shared_fut.add_done_callback(lambda _: fut.set_result(None))
        try:
            await fut
        finally:
            if is_first:
                async with self._state_lock:
                    if self.__resume_signal is fut:
                        self.__resume_signal = None
        return True

    async def wait_to_suspend(self, *tags: str, timeout: float | None = None):  # noqa: ASYNC109
        """Tell SuspendObjectStream to suspend and wait for it.

        Args:
            *tags: Tags to wait for (filter break points).
            timeout: Timeout for waiting.  Defaults to None (no timeout).

        Raises:
            RuntimeError: Raised when already waiting.
        """
        async with self._state_lock:
            if self.__suspend_signal is not None:
                if self.__suspend_signal.done():
                    self.__suspend_signal = None
                else:
                    raise RuntimeError("Already waiting for suspend!")
            self._suspend_tags = tags
            self.__suspend_signal = asyncio.Future()
        try:
            await asyncio.wait_for(self.__suspend_signal, timeout)
        finally:
            async with self._state_lock:
                self.__suspend_signal = None
                self._suspend_tags = None

    def resume(self) -> None:
        """Resume to run when suspend."""
        with self._state_lock:
            if self.__resume_signal and not self.__resume_signal.done():
                self.__resume_signal.set_result(True)

    def queue_closed(self) -> bool:
        """Check if the response queue is closed.

        Returns:
            bool: True if the queue is closed, False otherwise.
        """
        return self._queue_done

    async def set_queue_done(self) -> None:
        """Mark the response queue as done by putting the done marker."""
        async with self._state_lock:
            if self._queue_done:
                return
            self._queue_done = True
        try:
            await self._put_to_queue(self.__done_marker)
        except anyio.BrokenResourceError:
            pass  # queue is already marked done

    async def _put_to_queue(self, item):
        """Put an item to the queue, waiting if the queue is full.

        Args:
            item: Item to put in the queue.
        """
        with anyio.fail_after(self._q_tout):
            await self._send_stream.send(item)

    async def push_object(self, obj: ObjectTypeT) -> None:
        """Push an object to the sending queue.(always used for prompt)

        Args:
            obj: Object to be pushed to the queue.
        """
        await self._wait_for_continue(SUSPEND_ON_YIELD)
        async with self._state_lock:
            if self._queue_done:
                raise RuntimeError("Queue is closed.")
        await self._put_to_queue(obj)

    async def yield_response(self, response: ObjectTypeT) -> None:
        """Send response to the sending queue allowing both str and MessageContent types.

        Args:
            response: Either a string or MessageContent object to be sent to the receiving queue.
        """
        await self._wait_for_continue(SUSPEND_ON_YIELD)
        async with self._state_lock:
            cb = self._callback_fun
            if cb is None and self._queue_done:
                raise RuntimeError("Queue is closed.")
        if cb is not None:
            async with self._callback_lock:
                await cb(response)
        else:
            await self._put_to_queue(response)

    def set_callback_func(self, func: CALLBACK_TYPE) -> None:
        """Set a callback function to be executed when a response is yielded.

        Args:
            func: Function to be executed when a response is yielded.

        Raises:
            RuntimeError: If a callback function is already set.
        """
        with self._state_lock:
            if self._callback_fun:
                raise RuntimeError(
                    "The callback function of this chat object has already been set!"
                )
            self._callback_fun = func

    def set_callback_fun_sending(self, func: CALLBACK_TYPE) -> None:
        """Set a callback function to be executed when a response is sent for producer.

        Args:
            func: Function to be executed when a response is sent.
        """
        with self._state_lock:
            if self._callback_fun_sending:
                raise RuntimeError(
                    "The callback function for sending-side responses has already been set!"
                )
            self._callback_fun_sending = func

    async def yield_response_iteration(
        self, iterator: AsyncGenerator[ObjectTypeT, None]
    ):
        """Send chat model response to the queue allowing both str and MessageContent types.

        Args:
            iterator: An async generator that yields either strings or MessageContent objects.
        """
        async for chunk in iterator:
            await self.yield_response(chunk)

    def get_response_generator(self) -> AsyncGenerator[ObjectTypeT, None]:
        """Return an async generator to iterate over responses from the queue.

        Yields:
            ObjectTypeT: Either a string or MessageContent object from the response queue.

        Raises:
            RuntimeError: If response is already being consumed.
        """
        with self._state_lock:
            if self._has_consumer or self._callback_fun is not None:
                raise RuntimeError("Response is already being consumed.")
            self._has_consumer = True
        return self._response_generator()

    async def _response_generator(self) -> AsyncGenerator[ObjectTypeT]:
        """Internal method to asynchronously yield items from the queue until done marker is reached.

        Yields:
            ObjectTypeT: Items from the response queue until the done marker is encountered.
        """
        try:
            async for item in self._receive_stream:
                if item is self.__done_marker:
                    return
                yield item
        finally:
            async with self._state_lock:
                self._queue_done = True
            await asyncio.gather(
                self._send_stream.aclose(),
                self._receive_stream.aclose(),
                return_exceptions=True,
            )
