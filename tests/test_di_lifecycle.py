"""Tests for generator-based dependency lifecycle management.

Covers the three scopes (`call`, `dispatch`, `workflow`), both sync and async
generators, the two declaration forms (bare generator and `@contextmanager` /
`@asynccontextmanager`-decorated), teardown ordering, teardown on failure, and
the de-duplication provided by `DependencyStore`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

import pytest

from amrita_sense.di import DependencyStore, LifecycleScope, Scope
from amrita_sense.exceptions import DependsDeclarationError, DependsInjectFailed
from amrita_sense.hook.event import BaseEvent
from amrita_sense.hook.matcher import Depends, Matcher, MatcherFactory
from amrita_sense.node.core import NodeCompose
from amrita_sense.node.wrapper import Node as NodeDecorator
from amrita_sense.runtime.workflow import WorkflowInterpreter


class LifecycleEvent(BaseEvent):
    """Dedicated event type so handler registration cannot leak between tests."""

    def get_event_type(self) -> str:
        return "lifecycle_event"

    @property
    def event_type(self) -> str:
        return "lifecycle_event"


class _Absent:
    """Sentinel distinguishing "yield the name" from "yield None"."""


ABSENT = _Absent()


def make_logging_generator(log: list[str], name: str, value: Any = ABSENT):
    """Return a sync generator provider recording open/close into `log`."""

    def resource() -> Generator[Any, None, None]:
        log.append(f"open:{name}")
        try:
            yield name if value is ABSENT else value
        finally:
            log.append(f"close:{name}")

    return resource


#  LifecycleScope / DependencyStore units


class TestLifecycleScope:
    @pytest.mark.asyncio
    async def test_acquire_reuses_and_close_is_idempotent(self):
        log: list[Any] = []

        @asynccontextmanager
        async def cm() -> AsyncGenerator[str, None]:
            log.append("open")
            try:
                yield "v"
            finally:
                log.append("close")

        scope = LifecycleScope(Scope.CALL)
        first = await scope.acquire("k", cm)
        second = await scope.acquire("k", cm)
        assert first is second == "v"
        assert log == ["open"]

        await scope.aclose()
        await scope.aclose()
        assert log == ["open", "close"]

    @pytest.mark.asyncio
    async def test_acquire_after_close_raises(self):
        scope = LifecycleScope(Scope.CALL)
        await scope.aclose()

        @asynccontextmanager
        async def cm() -> AsyncGenerator[str, None]:
            yield "v"

        with pytest.raises(RuntimeError):
            await scope.acquire("k", cm)

    @pytest.mark.asyncio
    async def test_teardown_order_is_lifo(self):
        log: list[Any] = []

        @asynccontextmanager
        async def make(name: str) -> AsyncGenerator[str, None]:
            log.append(f"open:{name}")
            try:
                yield name
            finally:
                log.append(f"close:{name}")

        scope = LifecycleScope(Scope.CALL)
        await scope.acquire("a", lambda: make("a"))
        await scope.acquire("b", lambda: make("b"))
        await scope.aclose()
        assert log == ["open:a", "open:b", "close:b", "close:a"]


class TestDependencyStore:
    @pytest.mark.asyncio
    async def test_concurrent_resolution_computes_once(self):
        calls: list[int] = []

        async def compute() -> str:
            calls.append(1)
            await asyncio.sleep(0)
            return "v"

        store = DependencyStore()
        results = await asyncio.gather(*(store.resolve("k", compute) for _ in range(5)))
        assert results == ["v"] * 5
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_failure_is_shared_with_waiters(self):
        async def boom() -> str:
            raise ValueError("nope")

        store = DependencyStore()
        with pytest.raises(ValueError, match="nope"):
            await store.resolve("k", boom)
        with pytest.raises(ValueError, match="nope"):
            await store.resolve("k", boom)


#  Declaration validation


class TestDeclarationValidation:
    def test_scope_on_a_plain_callable_is_rejected(self):
        def plain() -> int:
            return 1

        with pytest.raises(DependsDeclarationError):
            Depends(plain, scope="workflow")

    def test_plain_provider_has_no_lifecycle(self):
        def plain() -> int:
            return 1

        factory = Depends(plain)
        assert factory.is_lifecycle is False
        assert factory.generator_kind is None
        assert factory.scope is None

    def test_generator_detection_covers_decorated_providers(self):
        def bare():
            yield 1

        @contextmanager
        def decorated():
            yield 1

        async def async_bare():
            yield 1

        @asynccontextmanager
        async def async_decorated():
            yield 1

        assert Depends(bare).generator_kind == "sync"
        assert Depends(decorated).generator_kind == "sync"
        assert Depends(async_bare).generator_kind == "async"
        assert Depends(async_decorated).generator_kind == "async"

    @pytest.mark.asyncio
    async def test_resolve_rejects_a_generator_directly(self):
        def resource():
            yield "r"

        with pytest.raises(DependsInjectFailed):
            await Depends(resource).resolve()


#  Node scopes


class TestCallScope:
    @pytest.mark.asyncio
    async def test_call_scope_wraps_the_node_invocation(self):
        log: list[Any] = []

        @NodeDecorator()
        def node(value: str = Depends(make_logging_generator(log, "r"), scope="call")):
            log.append(f"body:{value}")

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open:r", "body:r", "close:r"]

    @pytest.mark.asyncio
    async def test_call_scope_reopens_for_each_node(self):
        log: list[Any] = []
        resource = make_logging_generator(log, "r")

        @NodeDecorator()
        def first(value: str = Depends(resource, scope="call")):
            log.append("first")

        @NodeDecorator()
        def second(value: str = Depends(resource, scope="call")):
            log.append("second")

        await WorkflowInterpreter((first >> second).render()).run()
        assert log == ["open:r", "first", "close:r", "open:r", "second", "close:r"]

    @pytest.mark.asyncio
    async def test_teardown_runs_when_the_node_raises(self):
        log: list[Any] = []

        @NodeDecorator()
        def node(value: str = Depends(make_logging_generator(log, "r"), scope="call")):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open:r", "close:r"]

    @pytest.mark.asyncio
    async def test_teardown_order_follows_declaration_order(self):
        log: list[Any] = []
        outer = make_logging_generator(log, "outer")
        inner = make_logging_generator(log, "inner")

        @NodeDecorator()
        def node(
            a: str = Depends(outer, scope="call"),
            b: str = Depends(inner, scope="call"),
        ):
            log.append("body")

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == [
            "open:outer",
            "open:inner",
            "body",
            "close:inner",
            "close:outer",
        ]

    @pytest.mark.asyncio
    async def test_yield_none_fails_but_still_tears_down(self):
        log: list[Any] = []

        @NodeDecorator()
        def node(
            value: Any = Depends(make_logging_generator(log, "r", None), scope="call"),
        ):
            log.append("body")

        with pytest.raises(DependsInjectFailed):
            await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open:r", "close:r"]


class TestWorkflowScope:
    @pytest.mark.asyncio
    async def test_workflow_scope_is_shared_and_closed_at_the_end(self):
        log: list[Any] = []
        resource = make_logging_generator(log, "r")

        @NodeDecorator()
        def first(value: str = Depends(resource, scope="workflow")):
            log.append(("first", value))

        @NodeDecorator()
        def second(value: str = Depends(resource, scope="workflow")):
            log.append(("second", value))

        await WorkflowInterpreter((first >> second).render()).run()
        assert log[0] == "open:r"
        assert log[-1] == "close:r"
        assert log[1][1] is log[2][1]

    @pytest.mark.asyncio
    async def test_generator_defaults_to_the_widest_available_scope(self):
        log: list[Any] = []
        resource = make_logging_generator(log, "r")

        @NodeDecorator()
        def first(value: str = Depends(resource)):
            log.append(("first", value))

        @NodeDecorator()
        def second(value: str = Depends(resource)):
            log.append(("second", value))

        await WorkflowInterpreter((first >> second).render()).run()
        assert log[0] == "open:r"
        assert log[-1] == "close:r"
        assert log[1][1] is log[2][1]

    @pytest.mark.asyncio
    async def test_terminate_is_an_idempotent_backstop(self):
        log: list[Any] = []

        @NodeDecorator()
        def node(value: str = Depends(make_logging_generator(log, "r"))):
            log.append("body")

        pc = WorkflowInterpreter(NodeCompose(node).render())
        await pc.run()
        assert log == ["open:r", "body", "close:r"]
        await pc.terminate()
        assert log == ["open:r", "body", "close:r"]

    @pytest.mark.asyncio
    async def test_workflow_scope_survives_a_panic_until_terminate(self):
        log: list[Any] = []

        @NodeDecorator()
        def node(value: Any = Depends(make_logging_generator(log, "r", None))):
            log.append("body")

        pc = WorkflowInterpreter(NodeCompose(node).render())
        with pytest.raises(DependsInjectFailed):
            await pc.run()
        # A panic is recoverable by running again, so the workflow scope is deliberately left open.
        assert log == ["open:r"]
        await pc.terminate()
        assert log == ["open:r", "close:r"]

    @pytest.mark.asyncio
    async def test_workflow_scope_is_per_interpreter(self):
        log: list[Any] = []
        resource = make_logging_generator(log, "r")

        @NodeDecorator()
        def node(value: str = Depends(resource)):
            log.append(value)

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open:r", "r", "close:r", "open:r", "r", "close:r"]


#  Provider shapes


class TestProviderShapes:
    @pytest.mark.asyncio
    async def test_bare_sync_generator(self):
        log: list[Any] = []

        @NodeDecorator()
        def node(value: str = Depends(make_logging_generator(log, "sync"))):
            log.append(f"body:{value}")

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open:sync", "body:sync", "close:sync"]

    @pytest.mark.asyncio
    async def test_contextmanager_decorated_provider(self):
        log: list[Any] = []

        @contextmanager
        def resource() -> Generator[str, None, None]:
            log.append("open")
            try:
                yield "decorated"
            finally:
                log.append("close")

        @NodeDecorator()
        def node(value: str = Depends(resource)):
            log.append(f"body:{value}")

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open", "body:decorated", "close"]

    @pytest.mark.asyncio
    async def test_bare_async_generator(self):
        log: list[Any] = []

        async def resource() -> AsyncGenerator[str, None]:
            log.append("open")
            try:
                yield "async"
            finally:
                log.append("close")

        @NodeDecorator()
        async def node(value: str = Depends(resource)):
            log.append(f"body:{value}")

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open", "body:async", "close"]

    @pytest.mark.asyncio
    async def test_asynccontextmanager_decorated_provider(self):
        log: list[Any] = []

        @asynccontextmanager
        async def resource() -> AsyncGenerator[str, None]:
            log.append("open")
            try:
                yield "async-decorated"
            finally:
                log.append("close")

        @NodeDecorator()
        async def node(value: str = Depends(resource)):
            log.append(f"body:{value}")

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open", "body:async-decorated", "close"]

    @pytest.mark.asyncio
    async def test_nested_depends_is_supported(self):
        seen: list[int] = []

        async def inner() -> int:
            return 41

        async def outer(value: int = Depends(inner)) -> int:
            return value + 1

        @NodeDecorator()
        async def node(result: int = Depends(outer)):
            seen.append(result)

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert seen == [42]

    @pytest.mark.asyncio
    async def test_nested_generator_shares_the_caller_scope(self):
        log: list[Any] = []

        def inner() -> Generator[str, None, None]:
            log.append("open:inner")
            try:
                yield "i"
            finally:
                log.append("close:inner")

        async def outer(value: str = Depends(inner)) -> str:
            return value.upper()

        @NodeDecorator()
        async def node(result: str = Depends(outer)):
            log.append(f"body:{result}")

        await WorkflowInterpreter(NodeCompose(node).render()).run()
        assert log == ["open:inner", "body:I", "close:inner"]


#  Event dispatch scope


class TestDispatchScope:
    @pytest.mark.asyncio
    async def test_handlers_share_one_dispatch_scope(self):
        log: list[Any] = []
        resource = make_logging_generator(log, "r")
        matcher = Matcher("lifecycle_event", block=False)

        @matcher.handle()
        async def first(value: str = Depends(resource)):
            log.append(("first", value))

        @matcher.handle()
        async def second(value: str = Depends(resource)):
            log.append(("second", value))

        await MatcherFactory.trigger_event(LifecycleEvent())
        assert log[0] == "open:r"
        assert log[-1] == "close:r"
        assert log[1][1] is log[2][1]

    @pytest.mark.asyncio
    async def test_dispatch_scope_is_not_shared_between_dispatches(self):
        log: list[Any] = []
        resource = make_logging_generator(log, "r")
        matcher = Matcher("lifecycle_event", block=False)

        @matcher.handle()
        async def handler(value: str = Depends(resource)):
            log.append(value)

        await MatcherFactory.trigger_event(LifecycleEvent())
        await MatcherFactory.trigger_event(LifecycleEvent())
        assert log == ["open:r", "r", "close:r", "open:r", "r", "close:r"]
