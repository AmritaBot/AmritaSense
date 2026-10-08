from __future__ import annotations

import asyncio
import datetime
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable, Hashable, Iterable, Mapping
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    asynccontextmanager,
    contextmanager,
)
from enum import Enum
from threading import Lock
from types import FrameType
from typing import (
    Any,
    ClassVar,
    Generic,
    Literal,
    TypeVar,
    cast,
    overload,
)
from uuid import UUID, uuid4

import aiologic
from exceptiongroup import ExceptionGroup
from typing_extensions import Never, Self

from amrita_sense._unsafe import __flags__
from amrita_sense.di import DependencyStore, LifecycleScope, Scope, lift_sync_context
from amrita_sense.exceptions import DependsDeclarationError, DependsInjectFailed
from amrita_sense.hook import fun_typing
from amrita_sense.logging import debug_log, logger
from amrita_sense.utils import _fingerprint_args
from amrita_sense.weakcache import WeakValueLRUCache

from .event import BaseEvent, ConstructableEvent
from .exception import (
    CancelException,
    MatcherException,
    PassException,
)
from .fun_typing import (
    EMPTY,
    DependencyMeta,
    FunctionData,
    ParamDescriptor,
    sign_func,
    type_matches,
)


class EventRegistry:
    _instance = None
    _event_handlers: ClassVar[
        defaultdict[str, defaultdict[int, list[FunctionData]]]
    ] = defaultdict(lambda: defaultdict(list))
    _lock: ClassVar[Lock] = Lock()

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_handler(self, event_type: str, data: FunctionData):
        with self._lock:
            self._event_handlers[event_type][data.priority].append(data)

    def get_handlers(self, event_type: str) -> defaultdict[int, list[FunctionData]]:
        with self._lock:
            return self._event_handlers[event_type]

    def get_all(self) -> defaultdict[str, defaultdict[int, list[FunctionData]]]:
        with self._lock:
            return self._event_handlers


class Matcher(Hashable):
    _dead_at: datetime.datetime | None = None
    id: UUID

    def __init__(
        self,
        event_type: str,
        priority: int = 10,
        block: bool = True,
        dead_at: datetime.datetime | None = None,
    ):
        """Constructor, initialize Matcher object.
        Args:
            event_type (str): Event type
            priority (int, optional): Priority. Defaults to 10.
            block (bool, optional): Whether to block subsequent events. Defaults to True.
            dead_at (datetime.datetime | None, optional): Deadline for this matcher. Defaults to None.
        """
        if priority <= 0:
            raise ValueError("Event priority cannot be zero or negative!")

        self.event_type: str = event_type
        self.priority: int = priority
        self.block: bool = block
        self._dead_at = dead_at
        self.id = uuid4()

    def __hash__(self):
        return hash(self.id.bytes)

    def append_handler(self, func: Callable[..., Awaitable[Any]]):
        frame = inspect.currentframe()
        assert frame is not None, "Frame is None!!!"
        func_data = FunctionData(
            function=func,
            signature=sign_func(func),
            frame=frame,
            priority=self.priority,
            matcher=self,
        )
        EventRegistry().register_handler(self.event_type, func_data)

    def handle(self):
        """
        Event handler registration function
        """

        def wrapper(
            func: Callable[..., Awaitable[Any]],
        ):
            self.append_handler(func)
            return func

        return wrapper

    def set_block(self, block: bool):
        self.block = block

    def stop_process(self) -> Never:
        """
        Stop the current matcher then break the matcher loop.
        """
        raise CancelException()  # pragma: no cover

    def pass_event(self) -> Never:
        """
        Ignore the current handler and continue processing the next one.
        """
        raise PassException()  # pragma: no cover

    @property
    def dead(self) -> bool:
        return self._dead_at is not None and self._dead_at < datetime.datetime.now()


T = TypeVar("T")


def _callable_name(call: Callable[..., Any]) -> str:
    return getattr(call, "__qualname__", None) or getattr(call, "__name__", repr(call))


def detect_generator_kind(call: Callable[..., Any]) -> Literal["sync", "async"] | None:
    """Classify a dependency provider as a generator, if it is one.

    `inspect.unwrap` is required: `inspect.isgeneratorfunction` returns
    `False` for a function already decorated with `@contextmanager` (and
    likewise for `@asynccontextmanager`), while the wrapped function it
    exposes through `__wrapped__` is the generator.  Without the unwrap,
    every pre-decorated context-manager provider would be missed.

    Returns `"async"` for `async def ... yield`, `"sync"` for `def ... yield`,
    and `None` for an ordinary callable.
    """
    target = inspect.unwrap(call)
    if inspect.isasyncgenfunction(target):
        return "async"
    if inspect.isgeneratorfunction(target):
        return "sync"
    return None


class DependsFactory(Generic[T]):
    """Dependency factory class.

    Besides the provider itself this carries the *lifecycle* metadata needed
    when the provider is a generator: `generator_kind` records whether its
    teardown is synchronous or asynchronous, and `scope` records how long the
    resource should stay alive.  Both are computed once, at declaration time,
    so resolution never has to re-inspect the callable.
    """

    _depency_func: Callable[..., T | Awaitable[T]]
    _sign: DependencyMeta
    __cacheable: bool

    __slots__ = ("__cacheable", "_depency_func", "_sign", "generator_kind", "scope")

    @property
    def cacheable(self) -> bool:
        """Whether the resolved value may be reused."""
        return self.__cacheable

    @property
    def use_cache(self) -> bool:
        """Alias of `cacheable`, matching the upstream FastAPI/NoneBot2 naming."""
        return self.__cacheable

    @property
    def is_lifecycle(self) -> bool:
        """Whether the provider is a generator and therefore needs a scope."""
        return self.generator_kind is not None

    def __init__(
        self,
        depency: Callable[..., T | Awaitable[T]],
        cacheable: bool = False,
        *,
        scope: Scope | str | None = None,
    ):
        self._depency_func = depency
        self.__cacheable = cacheable
        self._sign = sign_func(self._depency_func)
        self.generator_kind = detect_generator_kind(self._depency_func)
        if self.generator_kind is None and scope is not None:
            raise DependsDeclarationError(
                f"`scope` is only meaningful for generator dependencies, but "
                f"{_callable_name(depency)!r} is a plain callable; use "
                "`use_cache=True` to reuse its value instead."
            )
        self.scope: Scope | None = Scope(scope) if scope is not None else None

    def make_context_manager(
        self, values: dict[str, Any]
    ) -> AbstractAsyncContextManager[Any]:
        """Build the (async) context manager for this generator provider.

        A bare generator function is wrapped with `contextmanager` /
        `asynccontextmanager`; a function already decorated with one of those
        is used as-is.  Adapted from NoneBot2's `DependParam._solve`
        (`nonebot/internal/params.py`), which draws the same distinction.
        """
        call = self._depency_func
        if self.generator_kind == "async":
            if inspect.isasyncgenfunction(call):
                return asynccontextmanager(call)(**values)
            return cast(AbstractAsyncContextManager[Any], call(**values))
        if inspect.isgeneratorfunction(call):
            return lift_sync_context(contextmanager(call)(**values))
        return lift_sync_context(cast(AbstractContextManager[Any], call(**values)))

    async def _resolve_kwargs(
        self,
        args: tuple,
        kwargs: dict[str, Any],
        store: DependencyStore | None,
        lifecycles: Mapping[Scope, LifecycleScope] | None,
        default_scope: Scope | None,
    ) -> dict[str, Any] | None:
        """Resolve this factory's own parameters, or `None` when it fails.

        Nested `Depends` is supported here: the sub-factories are resolved
        through the same lifecycle-aware entry point, so a nested generator
        registers on the caller's scope rather than a fresh one.
        """
        failed, values, dkw = MatcherFactory._resolve_dependencies(
            self._sign, session_args=args, session_kwargs=kwargs
        )
        if failed is not None:
            return None
        if dkw and not await MatcherFactory._do_runtime_resolve(
            runtime_args={},
            runtime_kwargs=dkw,
            args2update=[],
            kwargs2update=values,
            session_args=list(args),
            session_kwargs=kwargs,
            exception_ignored=(),
            store=store,
            lifecycles=lifecycles,
            default_scope=default_scope,
        ):
            return None
        return values

    async def resolve(
        self,
        *args: Any,
        _store: DependencyStore | None = None,
        _lifecycles: Mapping[Scope, LifecycleScope] | None = None,
        _default_scope: Scope | None = None,
        **kwargs: Any,
    ) -> T | None:
        """
        Resolve dependencies for a function.

        Args:
            *args: Positional arguments for dependency injection
            _store: Registry used to de-duplicate concurrent resolutions.
            _lifecycles: Active scopes; required for generator providers.
            _default_scope: Scope used when the declaration leaves it open.
            **kwargs: Keyword arguments for dependency injection

        Returns:
            T: The resolved dependency, or `None` when resolution failed.

        Raises:
            DependsInjectFailed: When the provider is a generator, which can
                only be resolved through an active lifecycle scope.
        """
        values = await self._resolve_kwargs(
            args, kwargs, _store, _lifecycles, _default_scope
        )
        if values is None:
            return None
        if self.is_lifecycle:
            raise DependsInjectFailed(
                f"{_callable_name(self._depency_func)!r} is a generator "
                "dependency; it has to be resolved through a lifecycle scope "
                "rather than by calling `resolve()` directly."
            )
        rs: T | Awaitable[T] = self._depency_func(**values)
        if isinstance(rs, Awaitable):
            rs = await rs
        return rs


def Depends(
    dependency: Callable[..., T | Awaitable[T]],
    use_cache: bool = False,
    scope: Scope | str | None = None,
    *,
    cacheable: bool | None = None,
) -> Any:
    """Dependency injection decorator.

    A provider may also be a generator, in which case the value before its
    `yield` is injected and the code after it runs as a teardown when the
    surrounding scope closes (see `amrita_sense.di.Scope`).  Both plain
    generator functions and providers already wrapped with `@contextmanager`
    / `@asynccontextmanager` are accepted.

    **IMPORTANT**: For database sessions (or ORM frameworks like SQLAlchemy),
    reuse may cause connection leaks — keep `use_cache=False` and leave
    `scope` at `"call"` unless the resource is genuinely meant to be shared.

    Args:
        dependency: The dependency function to inject.
        use_cache: Whether to reuse the dependency result.  For generator
            providers, sharing is governed by `scope` instead.
        scope: How long a generator provider's resource stays alive —
            `"call"`, `"dispatch"` or `"workflow"`.  Ignored for plain
            providers.  Defaults to the widest scope available at the
            resolution site.
        cacheable: Deprecated alias of `use_cache`.

    Returns:
        DependsFactory: A factory for dependency injection

    Example:
        ```python
        async def get_example_dependency(...) -> Any | None:
            ...

        async def with_session():
            session = Session()
            try:
                yield session
            finally:
                await session.close()

        async def a_function_with_dependencies(
            event: PreCompletionEvent,
            dep: ExampleDependency = Depends(get_example_dependency),
            session: Session = Depends(with_session, scope="workflow"),
        ):
            ...
        # If DependsFactory's return is None, this function won't be called.
        ```
    """
    if cacheable is not None:
        use_cache = cacheable
    return DependsFactory[T](dependency, use_cache, scope=scope)


class FailedEnum(Enum):
    """
    Dependency resolution failed enum class.
    """

    MISSED_ANNOTATION = "Missed annotation"
    MISSED_DEPENDENCY = "Missed dependency"
    RESOLVE_FAILED = "Resolution failed"


class MatcherFactory:
    """
    Event handling factory class.
    """

    _lock_pool: ClassVar[WeakValueLRUCache[str, aiologic.Lock]] = WeakValueLRUCache(
        capacity=1024, loose_mode=True
    )

    @classmethod
    def _repo_lock(cls, category: str) -> aiologic.Lock:
        if (lock := cls._lock_pool.get(category)) is None:
            lock = aiologic.Lock()
            cls._lock_pool[category] = lock
        return lock

    @staticmethod
    def _resolve_dependencies(
        signature: DependencyMeta,
        session_args: Iterable[Any],
        session_kwargs: dict[str, Any],
    ) -> tuple[FailedEnum | None, dict[str, Any], dict[str, DependsFactory]]:
        """Resolve dependencies for a function based on its signature and available arguments.

        Args:
            signature: Function signature to resolve dependencies for
            session_args: Available positional arguments for dependency injection
            session_kwargs: Available keyword arguments for dependency injection

        Returns:
            tuple[ FailedEnum | None, dict[str, Any], dict[str, DependsFactory] ]: A tuple containing:
                - An optional enum indicating the reason for failure (None if successful)
                - A dictionary of resolved keyword arguments
                - A dictionary of runtime dependencies to resolve
        """
        f_kwargs: dict[str, Any] = {}
        d_kwargs: dict[str, DependsFactory] = signature["factory_map"]
        required_params: dict[str, ParamDescriptor] = {}
        for k, v in signature["params"].items():
            if v["type_hint"] is EMPTY:
                return FailedEnum.MISSED_ANNOTATION, {}, {}
            if k in session_kwargs:
                f_kwargs[k] = session_kwargs[k]
            if v["default"] is EMPTY:
                required_params[k] = v
        for name, param in required_params.items():
            if name in f_kwargs:
                continue
            # Look for positional argument match
            param_type = param["type_hint"]
            for arg in session_args:
                if type_matches(arg, param_type):
                    f_kwargs[name] = arg
                    break
            else:
                return FailedEnum.MISSED_DEPENDENCY, {}, {}

        # Every required parameter was filled by the loop above; this only guards against one being silently dropped.
        if not required_params.keys() <= f_kwargs.keys():
            return FailedEnum.RESOLVE_FAILED, {}, {}

        return None, f_kwargs, d_kwargs

    @staticmethod
    async def _resolve_scoped(
        factory: DependsFactory,
        session_args: list[Any],
        session_kwargs: dict[str, Any],
        store: DependencyStore,
        lifecycles: Mapping[Scope, LifecycleScope] | None,
        default_scope: Scope | None,
    ) -> Any:
        """Resolve a generator provider through its lifecycle scope.

        The provider's own parameters are resolved first (which may itself
        open nested generator dependencies on the same scope), then the
        context manager is entered and its value returned.  Reuse is keyed by
        the provider, the fingerprint of the arguments it was given and the
        scope, so a changed input or a different lifecycle never hands back a
        stale resource.
        """
        values = await factory._resolve_kwargs(
            tuple(session_args), session_kwargs, store, lifecycles, default_scope
        )
        if values is None:
            return None
        scope: Scope | None = factory.scope or default_scope
        lifecycle = lifecycles.get(scope) if (lifecycles and scope) else None
        if scope is None or lifecycle is None:
            raise DependsInjectFailed(
                f"Dependency {_callable_name(factory._depency_func)!r} is a "
                f"generator declaring scope "
                f"{factory.scope.value if factory.scope else None!r}, but no "
                "matching lifecycle scope is active at this resolution site."
            )
        key: tuple[int, int, Scope] = (
            id(factory._depency_func),
            _fingerprint_args(tuple(session_args), session_kwargs),
            scope,
        )
        if scope is Scope.CALL:
            # A call scope owns a fresh value map for every call, so it *is* the cache.  Routing it through the store would hand a later call the previous call's resource.
            return await lifecycle.acquire(
                key, lambda: factory.make_context_manager(values)
            )
        return await store.resolve(
            key,
            lambda: lifecycle.acquire(
                key, lambda: factory.make_context_manager(values)
            ),
        )

    @staticmethod
    async def _do_runtime_resolve(
        runtime_args: dict[int, DependsFactory],
        runtime_kwargs: dict[str, DependsFactory],
        args2update: list[Any],
        kwargs2update: dict[str, Any],
        session_args: list[Any],
        session_kwargs: dict[str, Any],
        exception_ignored: tuple[type[BaseException], ...],
        *,
        store: DependencyStore | None = None,
        lifecycles: Mapping[Scope, LifecycleScope] | None = None,
        default_scope: Scope | None = None,
    ) -> bool:
        """Do a runtime resolve of dependencies.

        Plain providers are resolved concurrently, as before.  Generator
        providers are entered **one at a time** so that teardown order is the
        exact reverse of declaration order — concurrent setup would leave the
        closing order up to whichever provider happened to finish first.

        Args:
            runtime_args (dict[int, DependsFactory]): This is a dict of args dependencies (usually be passed in `trigger_event`) to resolve.
            runtime_kwargs (dict[str, DependsFactory]): This is a dict of kwargs dependencies to resolve.
            args2update (list[Any]): This is a list of args to update.
            kwargs2update (dict[str, Any]): This is a dict of kwargs to update.
            session_args (list[Any]): This is a list of args that can be used from the session .
            session_kwargs (dict[str, Any]): This is a dict of kwargs that can be used from the session.
            exception_ignored (tuple[type[BaseException], ...]): These exception will be raised again if occurred.
            store: Registry used to de-duplicate concurrent resolutions.  A
                throwaway one is created when the caller has none, which keeps
                the two providers within a single resolution call shared but
                nothing beyond it.
            lifecycles: Active scopes, looked up by `Scope`.
            default_scope: Scope used when a declaration leaves it open.

        Raises:
            result: if these exception

        Returns:
            result (bool): Return True if all injections are resolved, otherwise returns False
        """
        if not runtime_args and not runtime_kwargs:
            return True
        if store is None:
            store = DependencyStore()

        pending: list[tuple[int | None, str | None, DependsFactory]] = [
            (idx, None, factory) for idx, factory in runtime_args.items()
        ]
        pending.extend((None, key, factory) for key, factory in runtime_kwargs.items())
        plain = [item for item in pending if not item[2].is_lifecycle]
        scoped = [item for item in pending if item[2].is_lifecycle]

        args_tmp: dict[int, Any] = {}
        kwargs_tmp: dict[str, Any] = {}

        if plain:
            resolved_results: list[Any | BaseException] = await asyncio.gather(
                *[
                    factory.resolve(
                        *session_args,
                        _store=store,
                        _lifecycles=lifecycles,
                        _default_scope=default_scope,
                        **session_kwargs,
                    )
                    for _, _, factory in plain
                ],
                return_exceptions=True,
            )
            excs: list[Exception] = []
            for (idx, key, _), result in zip(plain, resolved_results):
                if isinstance(result, BaseException):
                    if not __flags__.DISABLE_EXC_IGNORED and isinstance(
                        result, exception_ignored
                    ):
                        raise result
                    if not isinstance(result, Exception):
                        # `ExceptionGroup` only accepts `Exception`s, and a bare `BaseException` such as cancellation must not be folded into a group anyway.
                        raise result
                    excs.append(result)
                elif result is None:
                    return False
                elif idx is not None:
                    args_tmp[idx] = result
                elif key is not None:
                    kwargs_tmp[key] = result
            if excs:
                raise ExceptionGroup("Some exceptions had occurred.", excs)

        for idx, key, factory in scoped:
            value = await MatcherFactory._resolve_scoped(
                factory,
                session_args,
                session_kwargs,
                store,
                lifecycles,
                default_scope,
            )
            if value is None:
                return False
            if idx is not None:
                args_tmp[idx] = value
            elif key is not None:
                kwargs_tmp[key] = value

        for k, v in args_tmp.items():
            args2update[k] = v
        kwargs2update.update(kwargs_tmp)
        return True

    @classmethod
    async def _simple_run(
        cls,
        matcher_list: list[FunctionData],
        /,
        exception_ignored: tuple[type[BaseException], ...],
        extra_args: Iterable[Any],
        extra_kwargs: dict[str, Any],
        store: DependencyStore | None = None,
        lifecycles: Mapping[Scope, LifecycleScope] | None = None,
    ) -> bool:
        """Run a round of matcher

        Args:
            matcher_list (list[FunctionData]): Matchers to run
            exception_ignored (tuple[type[BaseException], ...]): Exceptions to ignore(to raise again)
            extra_args (tuple): extra args for dependency injection
            extra_kwargs (dict[str, Any]): extra kwargs for dependency injection
            store: Registry used to de-duplicate concurrent resolutions.
            lifecycles: Active scopes, shared with the enclosing dispatch.

        Returns:
            bool: Should continue to run.
        """
        _dead_to_remove: list[FunctionData] = []
        try:
            for func in matcher_list:
                matcher: Matcher = func.matcher
                if matcher.dead:
                    _dead_to_remove.append(func)
                    continue
                signature = (
                    func.signature
                    if not __flags__.NO_DEPENDENCY_META_CACHE
                    else sign_func(func.function)
                )
                frame: FrameType = func.frame
                line_number: int = frame.f_lineno
                file_name: str = frame.f_code.co_filename
                handler = func.function
                if any(isinstance(i, DependsFactory) for i in extra_args):
                    raise ValueError(
                        "Runtime dependency injection is not supported in simple_run, please resolve them first or pass it to the trigger_event method"
                    )
                elif any(isinstance(i, DependsFactory) for i in extra_kwargs.values()):
                    raise ValueError(
                        "Runtime dependency injection is not supported in simple_run, please resolve them first or pass it to the trigger_event method"
                    )
                session_args = [matcher, *extra_args]
                failed, f_kwargs, d_kw = MatcherFactory._resolve_dependencies(
                    signature, session_args, extra_kwargs
                )
                if failed is not None:
                    failed_args = list(
                        {
                            k: v for k, v in signature["params"].items() if v is EMPTY
                        }.keys()
                    )
                    if failed_args:
                        prompt = (
                            f"Matcher {func.function.__name__} (File: {file_name}: Line {frame.f_lineno!s}) has untyped parameters!"
                            + f"(Args:{''.join(i + ',' for i in failed_args)}).Skipping......"
                        )

                    else:
                        prompt = f"Matcher {func.function.__name__} (File: {file_name}: Line {frame.f_lineno!s}) failed to resolve dependencies for {failed.value}! Skipping......"
                    logger.warning(prompt)
                    continue
                # Do kwargs dependency injection
                if d_kw and not await cls._do_runtime_resolve(
                    runtime_args={},
                    runtime_kwargs=d_kw,
                    args2update=[],
                    kwargs2update=f_kwargs,
                    session_args=session_args,
                    session_kwargs=extra_kwargs,
                    exception_ignored=exception_ignored,
                    store=store,
                    lifecycles=lifecycles,
                    default_scope=Scope.DISPATCH,
                ):
                    continue

                # Call the handler
                try:
                    logger.info(f"Starting to run Matcher: '{handler.__name__}'")

                    await handler(**f_kwargs)
                except PassException:
                    logger.info(
                        f"Matcher '{handler.__name__}'(~{file_name}:{line_number}) was skipped"
                    )
                    continue
                except Exception as e:
                    if isinstance(e, CancelException):
                        logger.info("Cancelled Matcher processing")
                        return False
                    elif isinstance(e, MatcherException):
                        raise
                    elif exception_ignored and isinstance(e, exception_ignored):
                        raise
                    logger.opt(exception=e).error(
                        f"An error occurred while running '{handler.__name__}'({file_name}:{line_number}) "
                    )
                    continue
                logger.info(f"Handler {handler.__name__} finished")

                if matcher.block:
                    return False
        finally:
            if _dead_to_remove:
                for func in _dead_to_remove:
                    matcher_list.remove(func)
        return True

    @overload
    @classmethod
    async def trigger_event(
        cls,
        event: BaseEvent,
        *args: Any,
        exception_ignored: tuple[type[BaseException], ...] = (),
        **kwargs: Any,
    ) -> None: ...
    @overload
    @classmethod
    async def trigger_event(
        cls,
        event: BaseEvent,
        *args: Any,
        config: None = None,
        exception_ignored: tuple[type[BaseException], ...] = (),
        **kwargs: Any,
    ) -> None: ...

    @overload
    @classmethod
    async def trigger_event(
        cls,
        event: BaseEvent,
        *args: Any,
        **kwargs: Any,
    ) -> None: ...
    @classmethod
    async def trigger_event(
        cls,
        event: BaseEvent,
        *args: Any,
        exception_ignored: tuple[type[BaseException], ...] = (),
        **kwargs,
    ) -> None:
        """Trigger a specific type of event and call all registered event handlers for that type.

        Args:
            event (BaseEvent): Event which will be used for DI system
            config (AmritaConfig): Configh which will be used for DI
            *args (Any): Positional arguments for DI
            exception_ignored (tuple[type[Exception], ...], optional): Exceptions that will be raised again if occurred. Defaults to tuple().
            **kwargs (Any): Keyword arguments for DI

        Raises:
            RuntimeError: If event or config is None, it will raise RuntimeError.
        """
        for i in args:
            if isinstance(i, BaseEvent):
                event = i
        if not event:
            raise RuntimeError("No event found in args")
        if isinstance(event, type) and issubclass(
            event, ConstructableEvent
        ):  # In the future, we will support constructable event class directly.
            raise TypeError(
                f"Cannot trigger ConstructableEvent class {event!r} directly; "
                "please use a constructable event in TRIGGER_EVENT node."
            )
        session_kwargs = kwargs
        event_type: str = event.get_event_type()  # Get event type
        if __flags__.DISABLE_EXC_IGNORED:
            exception_ignored = ()
        async with cls._repo_lock(event_type):
            handlers: defaultdict[int, list[FunctionData]] = (
                EventRegistry().get_handlers(event_type)
            )
            priorities: list[int] = sorted(handlers.keys(), reverse=False)
            debug_log(f"Running matchers for event: {event_type}!")
            # Check if there are handlers for this event type
            if priorities:
                s_args = [event, *args]
                session_kwargs: dict[str, Any] = kwargs.copy()
                # One dispatch scope covers every handler of this event, so a generator dependency declared by two handlers is opened once and torn down after the last of them returns.  This mirrors NoneBot2's single per-event `AsyncExitStack` (`nonebot/message.py`).
                async with LifecycleScope(Scope.DISPATCH) as dispatch_scope:
                    store = DependencyStore()
                    lifecycles: Mapping[Scope, LifecycleScope] = {
                        Scope.DISPATCH: dispatch_scope
                    }
                    runtime_args: dict[
                        int, DependsFactory
                    ] = {  # index -> DependsFactory
                        k: v
                        for k, v in enumerate(s_args)
                        if isinstance(v, DependsFactory)
                    }
                    runtime_kwargs = {
                        k: v
                        for k, v in session_kwargs.items()
                        if isinstance(v, DependsFactory)
                    }
                    # These args/kwargs will be generated by Depends
                    if runtime_args or runtime_kwargs:
                        if not await cls._do_runtime_resolve(
                            runtime_args=runtime_args,
                            runtime_kwargs=runtime_kwargs,
                            args2update=s_args,
                            kwargs2update=session_kwargs,
                            session_args=s_args,
                            session_kwargs=session_kwargs,
                            exception_ignored=exception_ignored,
                            store=store,
                            lifecycles=lifecycles,
                            default_scope=Scope.DISPATCH,
                        ):
                            raise RuntimeError("Runtime arguments cannot be resolved")
                    for priority in priorities:
                        logger.info(f"Running matchers for priority {priority}......")
                        if not await cls._simple_run(
                            handlers[priority],
                            exception_ignored=exception_ignored,
                            extra_args=s_args,
                            extra_kwargs=session_kwargs,
                            store=store,
                            lifecycles=lifecycles,
                        ):
                            break
            else:
                logger.info(
                    f"No registered Matcher for {event_type} event, skipping processing."
                )


fun_typing.DependsFactory = DependsFactory
