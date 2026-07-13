import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from functools import wraps
from typing import Any, Generic, TypeAlias, TypeVar

import aiologic
import anyio
from anyio.abc import ObjectReceiveStream, ObjectSendStream
from typing_extensions import LiteralString

from amrita_sense.exceptions import StreamStateError

ObjectTypeT = TypeVar("ObjectTypeT")
CALLBACK_TYPE: TypeAlias = Callable[[ObjectTypeT], Awaitable[Any]]
SUSPEND_ON_YIELD: LiteralString = "SuspendObjectStream::yield_response"


class SuspendObjectStream(Generic[ObjectTypeT]):
    """
    A bidirectional stream with suspend/resume control.

    The producer sends items to a single consumer through one channel, and the
    consumer can independently send items back to the producer through a second
    channel.  The producer can be suspended and resumed externally, and both
    sides can optionally use callbacks instead of the stream interface.
    """

    __eof_marker = object()

    # Suspension signals
    __suspend_signal: asyncio.Future | None = None
    __resume_signal: asyncio.Future | None = None
    _suspend_tags: tuple[str, ...] | None = None

    # Callbacks
    _callback_fun: CALLBACK_TYPE | None = None
    _callback_lock: aiologic.Lock
    _callback_fun_sending: CALLBACK_TYPE | None = None
    _callback_sending_lock: aiologic.Lock

    # Streams – two independent unidirectional channels
    _send_stream: ObjectSendStream  # Producer -> Consumer
    _receive_stream: ObjectReceiveStream  # Consumer reads from Producer

    _peer_send_stream: ObjectSendStream  # Consumer -> Producer
    _peer_receive_stream: ObjectReceiveStream  # Producer reads from Consumer

    # State
    _queue_done: bool = False
    _peer_done: bool = False
    _has_consumer: bool = False
    _has_producer_input_consumer: bool = False
    _q_tout: float | None

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
        self._peer_send_stream, self._peer_receive_stream = (
            anyio.create_memory_object_stream(max_buffer_size=queue_size)
        )
        self._callback_fun = callback
        self._callback_lock = aiologic.Lock()
        self._callback_fun_sending = receive_callback
        self._callback_sending_lock = aiologic.Lock()
        self._q_tout = queue_timeout
        self._state_lock = aiologic.Lock()

    # Suspend / resume – shared by both stream directions

    @staticmethod
    def suspend(func: Callable[..., Any], tag: str | None = None) -> Callable[..., Any]:
        """
        Decorator that pauses the decorated coroutine until the stream is
        resumed.  Must be applied to a coroutine that receives a
        ``SuspendObjectStream`` instance as one of its arguments.

        The optional *tag* allows selective resumption – only
        ``wait_to_suspend`` calls with a matching tag will block the
        function.
        """
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
        """Shorthand for ``SuspendObjectStream.suspend(func, tag)``."""
        return lambda func: SuspendObjectStream.suspend(func, tag)

    async def _wait_for_continue(self, tag: str | None = None) -> bool:
        """
        Block until the stream is resumed.

        Multiple concurrent callers share a single resume future; the first
        caller creates it and others piggyback via callbacks.

        Returns:
            ``True`` if the caller actually blocked (was suspended), ``False``
            if no suspension was in progress or the *tag* did not match.
        """
        async with self._state_lock:
            if self.__suspend_signal is None:
                return False
            if self._suspend_tags:
                if tag is None or tag not in self._suspend_tags:
                    return False

            if self.__resume_signal is not None and not self.__resume_signal.done():
                shared_fut = self.__resume_signal
                is_first = False
            else:
                if not self.__suspend_signal.done():
                    self.__suspend_signal.set_result(True)
                self.__resume_signal = asyncio.Future()
                shared_fut = self.__resume_signal
                is_first = True
            if is_first:
                fut = shared_fut
            else:
                fut: asyncio.Future[None] = asyncio.Future()
                shared_fut.add_done_callback(lambda _: fut.set_result(None))
            await asyncio.sleep(0)
        try:
            await fut
        finally:
            if is_first:
                async with self._state_lock:
                    if (rmt := self.__resume_signal) is fut:
                        if not rmt.done():
                            rmt.cancel()
                        self.__resume_signal = None
        return True

    async def wait_to_suspend(self, *tags: str, timeout: float | None = None):  # noqa: ASYNC109
        """
        Request the producer to suspend and wait until it actually blocks.

        Only break points whose tag is in *tags* (or all break points if
        *tags* is empty) will be blocked.

        Raises:
            StreamStateError: If a suspension is already waiting.
        """
        async with self._state_lock:
            if self.__suspend_signal is not None:
                if self.__suspend_signal.done():
                    self.__suspend_signal = None
                else:
                    raise StreamStateError("Already waiting for suspend!")
            self._suspend_tags = tags
            self.__suspend_signal = asyncio.Future()
        try:
            await asyncio.wait_for(self.__suspend_signal, timeout)
        finally:
            async with self._state_lock:
                self.__suspend_signal = None
                self._suspend_tags = None

    def resume(self) -> None:
        """Resume a suspended producer."""
        with self._state_lock:
            if self.__resume_signal and not self.__resume_signal.done():
                self.__resume_signal.set_result(True)

    # Low‑level send helpers

    async def _put_to_queue(self, item):
        """Send *item* through the producer -> consumer channel."""
        with anyio.fail_after(self._q_tout):
            await self._send_stream.send(item)

    async def _peer_put_to_queue(self, item):
        """Send *item* through the consumer -> producer channel."""
        with anyio.fail_after(self._q_tout):
            await self._peer_send_stream.send(item)

    # Producer -> Consumer direction (main response stream)

    async def push_object(self, obj: ObjectTypeT) -> None:
        """
        Producer sends an object (e.g. a prompt) to the consumer.

        This uses the primary producer->consumer channel and is subject to
        suspension via the ``SUSPEND_ON_YIELD`` tag.
        """
        await self._wait_for_continue(SUSPEND_ON_YIELD)
        async with self._state_lock:
            cb = self._callback_fun_sending
            if cb is None and self._queue_done:
                raise StreamStateError("Queue is closed.")
        if cb is not None:
            async with self._callback_sending_lock:
                await cb(obj)
        else:
            await self._put_to_queue(obj)

    async def yield_response(self, response: ObjectTypeT) -> None:
        """
        Producer sends a response chunk to the consumer.

        This is normally used to stream output from a long‑running operation.
        It respects the ``SUSPEND_ON_YIELD`` suspension tag and falls back to
        the ``_callback_fun`` callback if one is configured.
        """
        await self._wait_for_continue(SUSPEND_ON_YIELD)
        async with self._state_lock:
            cb = self._callback_fun
            if cb is None and self._queue_done:
                raise StreamStateError("Queue is closed.")
        if cb is not None:
            async with self._callback_lock:
                await cb(response)
        else:
            await self._put_to_queue(response)

    async def yield_response_iteration(
        self, iterator: AsyncGenerator[ObjectTypeT, None]
    ):
        """Convenience wrapper that calls ``yield_response`` for every item of *iterator*."""
        async for chunk in iterator:
            await self.yield_response(chunk)

    def get_response_generator(self) -> AsyncGenerator[ObjectTypeT, None]:
        """
        Return an async generator that yields every response item sent by the
        producer.

        Only one consumer is allowed.  The generator automatically exits when
        the producer sends the done marker (see ``set_queue_done``).

        Raises:
            StreamStateError: If another consumer is already active or a
                response callback has been set.
        """
        with self._state_lock:
            if self._has_consumer or self._callback_fun is not None:
                raise StreamStateError("Response is already being consumed.")
            self._has_consumer = True
        return self._response_generator()

    async def _response_generator(self) -> AsyncGenerator[ObjectTypeT]:
        """Internal generator that reads from the producer->consumer channel."""
        try:
            async for item in self._receive_stream:
                if item is self.__eof_marker:
                    return
                yield item
        finally:
            async with self._state_lock:
                self._queue_done = True
            await self._receive_stream.aclose()

    def queue_closed(self) -> bool:
        """Return ``True`` if the producer->consumer channel is closed."""
        return self._queue_done

    async def set_queue_done(self) -> None:
        """Producer signals the end of the response stream by sending a done marker."""
        async with self._state_lock:
            if self._queue_done:
                return
            self._queue_done = True
        try:
            await self._put_to_queue(self.__eof_marker)
        except anyio.BrokenResourceError:
            pass  # The consumer already closed its end.

    # Consumer -> Producer direction (reverse stream)

    async def send_to_producer(self, obj: ObjectTypeT) -> None:
        """
        Consumer sends an object back to the producer over the reverse channel.

        Raises:
            StreamStateError: If the reverse channel has been marked done.
        """
        async with self._state_lock:
            if self._peer_done:
                raise StreamStateError("Reverse queue is closed.")
        await self._peer_put_to_queue(obj)

    async def send_done_to_producer(self) -> None:
        """
        Consumer sends the end‑of‑stream marker to the producer.

        After this call the producer's input generator (obtained via
        ``get_producer_input_generator``) will stop yielding items.
        """
        async with self._state_lock:
            if self._peer_done:
                return
            self._peer_done = True
        try:
            await self._peer_put_to_queue(self.__eof_marker)
        except anyio.BrokenResourceError:
            pass

    def get_producer_input_generator(self) -> AsyncGenerator[ObjectTypeT, None]:
        """
        Return an async generator that yields every object sent by the consumer
        over the reverse channel.

        The producer can use this to receive data from the consumer.  The
        generator stops when the consumer sends the done marker (see
        ``send_done_to_producer``).

        Raises:
            StreamStateError: If another generator for the reverse stream is
                already active.
        """
        with self._state_lock:
            if self._has_producer_input_consumer:
                raise StreamStateError("Producer input is already being consumed.")
            self._has_producer_input_consumer = True
        return self._producer_input_generator()

    async def _producer_input_generator(self) -> AsyncGenerator[ObjectTypeT]:
        """Internal generator that reads from the consumer->producer channel."""
        try:
            async for item in self._peer_receive_stream:
                if item is self.__eof_marker:
                    return
                yield item
        finally:
            await self._peer_receive_stream.aclose()

    # Callback management

    def set_callback_func(self, func: CALLBACK_TYPE) -> None:
        """
        Set a callback that receives every ``yield_response`` value instead
        of pushing it to the stream.

        Only one callback can be set, and it prevents the use of
        ``get_response_generator``.

        Raises:
            StreamStateError: If a callback has already been set.
        """
        with self._state_lock:
            if self._callback_fun:
                raise StreamStateError(
                    "The callback function of this chat object has already been set!"
                )
            self._callback_fun = func

    def set_callback_fun_sending(self, func: CALLBACK_TYPE) -> None:
        """
        Set a callback that receives every ``push_object`` value instead of
        pushing it to the stream.

        Raises:
            StreamStateError: If a sending‑side callback has already been set.
        """
        with self._state_lock:
            if self._callback_fun_sending:
                raise StreamStateError(
                    "The callback function for sending-side responses has already been set!"
                )
            self._callback_fun_sending = func
