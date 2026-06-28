import asyncio

import pytest

from amrita_sense.streaming import SUSPEND_ON_YIELD, SuspendObjectStream

# ============================================================================
# Helpers
# ============================================================================


async def _consume_all(obj: SuspendObjectStream) -> list:
    """Consume the response generator until exhausted."""
    results = []
    async for item in obj.get_response_generator():
        results.append(item)
    return results


async def _async_gen(items: list):
    """Create an async generator from a list."""
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_chatobject_suspend_tags():
    obj = SuspendObjectStream()
    suspend = False

    async def suspend_func():
        nonlocal suspend
        while True:
            if await obj._wait_for_continue():
                pytest.fail("Should not continue without correct tag")
            elif await obj._wait_for_continue("test-tag"):
                break
        suspend = True

    hd: asyncio.Task[None] = asyncio.create_task(suspend_func())
    try:
        await obj.wait_to_suspend("test-tag", timeout=2)
        obj.resume()
        await asyncio.wait_for(hd, 0.2)
        assert suspend, "Suspend not called"
    finally:
        hd.cancel()


@pytest.mark.asyncio
async def test_chatobject_suspend():
    obj = SuspendObjectStream()
    suspend = False

    async def suspend_func():
        nonlocal suspend
        while True:
            if await obj._wait_for_continue():
                break
        suspend = True

    hd: asyncio.Task[None] = asyncio.create_task(suspend_func())
    try:
        await obj.wait_to_suspend(timeout=2)
        obj.resume()
        await asyncio.wait_for(hd, 0.2)
        assert suspend, "Suspend not called"
    finally:
        hd.cancel()


# ============================================================================
# A. suspend decorator (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_suspend_decorator_positional_arg():
    """suspend() discovers obj in positional args."""
    obj = SuspendObjectStream()
    called = False

    @SuspendObjectStream.suspend
    async def my_func(stream: SuspendObjectStream, value: str) -> str:
        nonlocal called
        called = True
        return value

    task = asyncio.create_task(my_func(obj, "hello"))
    await obj.wait_to_suspend(timeout=2)
    await asyncio.sleep(0)
    obj.resume()
    result = await task
    assert called
    assert result == "hello"


@pytest.mark.asyncio
async def test_suspend_decorator_keyword_arg():
    """suspend() discovers obj in keyword args."""
    obj = SuspendObjectStream()
    called = False

    @SuspendObjectStream.suspend
    async def my_func(*, stream: SuspendObjectStream) -> bool:
        nonlocal called
        called = True
        return True

    task = asyncio.create_task(my_func(stream=obj))
    await obj.wait_to_suspend(timeout=2)
    await asyncio.sleep(0)
    obj.resume()
    result = await task
    assert called
    assert result is True


def test_suspend_decorator_non_coroutine():
    """Decorating a sync function raises TypeError."""
    with pytest.raises(TypeError, match="is not a coroutine function"):

        @SuspendObjectStream.suspend
        def sync_func(x):
            return x


@pytest.mark.asyncio
async def test_suspend_decorator_no_object():
    """No SuspendObjectStream in args/kwargs raises TypeError."""

    @SuspendObjectStream.suspend
    async def my_func(x: int) -> int:
        return x

    with pytest.raises(TypeError, match="No SuspendObjectStream parameter found"):
        await my_func(42)


# ============================================================================
# B. Multi-waiter resume (1 test)
# ============================================================================


@pytest.mark.asyncio
async def test_multi_waiter_resume():
    """Multiple _wait_for_continue callers are all woken by a single resume()."""
    obj = SuspendObjectStream()
    counter = [0]

    async def waiter():
        while True:
            waited = await obj._wait_for_continue()
            if waited:
                counter[0] += 1
                return
            await asyncio.sleep(0)

    t1 = asyncio.create_task(waiter())
    t2 = asyncio.create_task(waiter())
    await asyncio.sleep(0)

    await obj.wait_to_suspend(timeout=2)
    await asyncio.sleep(0)  # let waiters exit the state lock
    obj.resume()
    await asyncio.gather(t1, t2)
    assert counter[0] == 2


# ============================================================================
# C. wait_to_suspend boundaries (2 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_wait_to_suspend_already_waiting():
    """Calling wait_to_suspend while a previous one is pending raises RuntimeError."""
    obj = SuspendObjectStream()

    t = asyncio.create_task(obj.wait_to_suspend(timeout=None))
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="Already waiting for suspend"):
        await obj.wait_to_suspend(timeout=0.5)

    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t


@pytest.mark.asyncio
async def test_wait_to_suspend_done_signal_reuse():
    """After a full suspend cycle, calling wait_to_suspend again works."""
    obj = SuspendObjectStream()

    async def worker():
        while True:
            waited = await obj._wait_for_continue()
            if waited:
                return
            await asyncio.sleep(0)

    # First cycle
    t = asyncio.create_task(worker())
    await obj.wait_to_suspend(timeout=2)
    await asyncio.sleep(0)
    obj.resume()
    await t

    # Second cycle — __suspend_signal was cleared, should work
    t2 = asyncio.create_task(worker())
    await obj.wait_to_suspend(timeout=2)
    await asyncio.sleep(0)
    obj.resume()
    await t2


# ============================================================================
# D. resume no-op (1 test)
# ============================================================================


@pytest.mark.asyncio
async def test_resume_noop():
    """resume() with no pending __resume_signal is a silent no-op."""
    obj = SuspendObjectStream()
    obj.resume()  # no error


# ============================================================================
# E. Queue operations (7 tests)
# ============================================================================


def test_queue_closed_initial():
    """queue_closed() returns False initially."""
    obj = SuspendObjectStream()
    assert obj.queue_closed() is False


@pytest.mark.asyncio
async def test_set_queue_done_idempotent():
    """Calling set_queue_done twice is safe (second is no-op)."""
    obj = SuspendObjectStream()
    await obj.set_queue_done()
    assert obj.queue_closed() is True
    await obj.set_queue_done()
    assert obj.queue_closed() is True


@pytest.mark.asyncio
async def test_push_object_normal():
    """push_object sends items that can be consumed via generator."""
    obj = SuspendObjectStream(queue_size=5, queue_timeout=2)

    consumer = asyncio.create_task(_consume_all(obj))
    await asyncio.sleep(0)

    await obj.push_object("hello")
    await obj.push_object("world")
    await obj.set_queue_done()

    results = await consumer
    assert results == ["hello", "world"]


@pytest.mark.asyncio
async def test_push_object_closed():
    """push_object on a closed queue raises RuntimeError."""
    obj = SuspendObjectStream()
    await obj.set_queue_done()
    with pytest.raises(RuntimeError, match="Queue is closed"):
        await obj.push_object("should fail")


@pytest.mark.asyncio
async def test_yield_response_normal():
    """yield_response sends items that can be consumed via generator."""
    obj = SuspendObjectStream(queue_size=5, queue_timeout=2)

    consumer = asyncio.create_task(_consume_all(obj))
    await asyncio.sleep(0)

    await obj.yield_response("alpha")
    await obj.yield_response("beta")
    await obj.set_queue_done()

    results = await consumer
    assert results == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_yield_response_closed():
    """yield_response on a closed queue raises RuntimeError."""
    obj = SuspendObjectStream()
    await obj.set_queue_done()
    with pytest.raises(RuntimeError, match="Queue is closed"):
        await obj.yield_response("should fail")


@pytest.mark.asyncio
async def test_yield_response_with_callback():
    """yield_response dispatches to callback when set, bypassing the queue."""
    obj = SuspendObjectStream()
    received = []

    async def my_callback(item):
        received.append(item)

    obj.set_callback_func(my_callback)
    await obj.yield_response("via-callback")
    assert received == ["via-callback"]


# ============================================================================
# F. Callback settings (4 tests)
# ============================================================================


@pytest.mark.asyncio
async def test_set_callback_func_normal():
    """Normal setup and invocation of response callback."""
    obj = SuspendObjectStream()
    received = []

    async def cb(item):
        received.append(item)

    obj.set_callback_func(cb)
    await obj.yield_response("cb-test")
    assert received == ["cb-test"]


def test_set_callback_func_twice():
    """Setting response callback twice raises RuntimeError."""
    obj = SuspendObjectStream()

    async def cb1(x):
        pass

    async def cb2(x):
        pass

    obj.set_callback_func(cb1)
    with pytest.raises(RuntimeError, match="already been set"):
        obj.set_callback_func(cb2)


def test_set_callback_fun_sending_normal():
    """Normal setup of sending-side callback."""
    obj = SuspendObjectStream()
    received = []

    async def cb(item):
        received.append(item)

    obj.set_callback_fun_sending(cb)
    assert obj._callback_fun_sending is cb


def test_set_callback_fun_sending_twice():
    """Setting sending callback twice raises RuntimeError."""
    obj = SuspendObjectStream()

    async def cb1(x):
        pass

    async def cb2(x):
        pass

    obj.set_callback_fun_sending(cb1)
    with pytest.raises(RuntimeError, match="already been set"):
        obj.set_callback_fun_sending(cb2)


# ============================================================================
# G. Generator lifecycle (5 tests)
# ============================================================================


def test_get_generator_already_consumed():
    """Calling get_response_generator twice raises RuntimeError."""
    obj = SuspendObjectStream()
    obj.get_response_generator()
    with pytest.raises(RuntimeError, match="already being consumed"):
        obj.get_response_generator()


def test_get_generator_blocked_by_callback():
    """get_response_generator with callback set raises RuntimeError."""
    obj = SuspendObjectStream()

    async def cb(x):
        pass

    obj.set_callback_func(cb)
    with pytest.raises(RuntimeError, match="already being consumed"):
        obj.get_response_generator()


@pytest.mark.asyncio
async def test_full_flow_push_yield_done_close():
    """End-to-end: push -> yield -> set_queue_done -> generator yields -> close."""
    obj = SuspendObjectStream(queue_size=5, queue_timeout=2)

    consumer = asyncio.create_task(_consume_all(obj))
    await asyncio.sleep(0)

    await obj.push_object(1)
    await obj.yield_response(2)
    await obj.push_object(3)
    await obj.set_queue_done()

    results = await consumer
    assert results == [1, 2, 3]
    assert obj.queue_closed()


@pytest.mark.asyncio
async def test_yield_response_iteration():
    """yield_response_iteration forwards all chunks from an async generator."""
    obj = SuspendObjectStream(queue_size=5, queue_timeout=2)

    consumer = asyncio.create_task(_consume_all(obj))
    await asyncio.sleep(0)

    await obj.yield_response_iteration(_async_gen([0, 1, 2]))
    await obj.set_queue_done()

    results = await consumer
    assert results == [0, 1, 2]


@pytest.mark.asyncio
async def test_response_generator_done_marker():
    """_response_generator returns when it receives the done marker."""
    obj = SuspendObjectStream(queue_size=5, queue_timeout=2)

    consumer = asyncio.create_task(_consume_all(obj))
    await asyncio.sleep(0)

    await obj.yield_response("x")
    await obj.set_queue_done()

    results = await consumer
    assert results == ["x"]


# ============================================================================
# H. SUSPEND_ON_YIELD tag shortcut (1 test)
# ============================================================================


@pytest.mark.asyncio
async def test_wait_for_continue_with_yield_tag():
    """_wait_for_continue(SUSPEND_ON_YIELD) matches the tag and suspends correctly."""
    obj = SuspendObjectStream()
    waited = False

    async def worker():
        nonlocal waited
        while True:
            w = await obj._wait_for_continue(SUSPEND_ON_YIELD)
            if w:
                waited = True
                return
            await asyncio.sleep(0)

    t = asyncio.create_task(worker())
    await obj.wait_to_suspend(SUSPEND_ON_YIELD, timeout=2)
    await asyncio.sleep(0)
    obj.resume()
    await t
    assert waited
