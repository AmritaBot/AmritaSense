from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine, Sequence
from contextlib import nullcontext
from functools import wraps
from inspect import iscoroutinefunction
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    TypeVar,
    cast,
    overload,
)
from uuid import uuid4

import aiologic
from cachetools import LRUCache

from amrita_sense._unsafe import __flags__
from amrita_sense.exceptions import (
    BreakLoop,
    DependsInjectFailed,
    DependsResolveFailed,
    IllegalState,
    InterruptKeepContext,
    InterruptNotice,
    NullPointerException,
)
from amrita_sense.hook.matcher import DependsFactory, MatcherFactory, sign_func
from amrita_sense.logging import debug_log, logger
from amrita_sense.node.core import BaseNode, NodeComposeRendered
from amrita_sense.node.core import Node as _Node
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.types import InterpreterContext
from amrita_sense.streaming import SuspendObjectStream
from amrita_sense.types import DICache, PointerVector, Stack
from amrita_sense.utils import TimeInsighter, _fingerprint_args

PC_CHECKPOINT = "WorkflowInterpreter::each_node"
NULL_CTX = nullcontext()
io_T = TypeVar("io_T", bound=SuspendObjectStream, covariant=True)
fun_T = TypeVar("fun_T", bound=Callable[..., Any], covariant=True)
UNSET = object()
if not TYPE_CHECKING:
    nop: _Node[None] | None = None
else:
    pass


class WorkflowInterpreter(Generic[io_T]):
    """Main workflow interpreter and execution engine.

    This class is responsible for executing compiled workflow graphs by managing
    the execution pointer, handling control flow operations (jumps, calls, loops),
    and providing dependency injection services. It implements an interpreter/VM
    pattern for dynamic workflow execution.
    """

    _graph: NodeComposeRendered
    _pointer: PointerVector
    _jump_marked: bool

    __ava_args: tuple
    __ava_kwargs: dict[str, Any]
    _exc_ignored: tuple[type[BaseException], ...]

    _di_cache: DICache
    _ptr_cache: LRUCache[int, list[int]]

    _ret_addr_stack: Stack[PointerVector]

    _interpreter_id: str  # Instance id
    _interpret_lock: aiologic.Lock
    _panic_exc: Exception | None

    _if_flag: bool  # Whether in the interrupt mode
    _context_stack: Stack[InterpreterContext]

    _parent_interpreter: WorkflowInterpreter | None
    _glob_top_mod_lock: aiologic.Lock
    _top_interpreter: WorkflowInterpreter | None

    _sub_interpreters_all: dict[str, WorkflowInterpreter] | None
    _sub_interpreters: dict[str, WorkflowInterpreter]
    _waiter_fut: asyncio.Future[None] | None

    _middleware: Callable[[WorkflowInterpreter], Awaitable[Any]] | None
    _pending_stop: bool
    object_io: io_T
    __slots__ = (
        "__ava_args",
        "__ava_kwargs",
        "_context_stack",
        "_di_cache",
        "_exc_ignored",
        "_glob_top_mod_lock",
        "_graph",
        "_if_flag",
        "_interpret_lock",
        "_interpreter_id",
        "_jump_marked",
        "_middleware",
        "_panic_exc",
        "_parent_interpreter",
        "_pending_stop",
        "_pointer",
        "_ptr_cache",
        "_ret_addr_stack",
        "_sub_interpreters",
        "_sub_interpreters_all",
        "_top_interpreter",
        "_waiter_fut",
        "object_io",
    )

    def __init__(
        self,
        node_compose: NodeComposeRendered | SelfCompileInstruction,
        object_io: SuspendObjectStream[Any] | None = None,
        *,
        exception_ignored: tuple[type[BaseException], ...] = (),
        extra_args: tuple = (),
        extra_kwargs: dict[str, Any] | None = None,
        addr_stack: Stack[PointerVector] | None = None,
        context_stack: Stack[InterpreterContext] | None = None,
        middleware: Callable[[WorkflowInterpreter], Awaitable[Any]] | None = None,
        parent_interpreter: WorkflowInterpreter | None = None,
        ptr_cache_size: int = 1024,
    ):
        """Initialize the workflow interpreter with a compiled workflow graph.

        Args:
            node_compose: The workflow graph to execute, either pre-rendered or a self-compiling instruction.
            object_io: Optional I/O stream for external communication. Defaults to a new SuspendObjectStream.
            exception_ignored: Exception types that should bypass TRY/CATCH handlers.
            extra_args: Additional positional arguments for dependency injection.
            extra_kwargs: Additional keyword arguments for dependency injection.
            addr_stack: Optional pre-initialized return address stack.
            context_stack: Optional pre-initialized interpreter context stack.
            middleware: Optional middleware function to execute before each node.
            parent_interpreter: Optional parent interpreter for sub-interpreter relationship.
            ptr_cache_size: Size of the addressing cache.
        """
        # Kernel initialization
        self._interpreter_id = uuid4().hex
        if isinstance(node_compose, SelfCompileInstruction):
            node_compose = node_compose.extract().render()
        self._graph = node_compose
        self._pointer = PointerVector()
        self._panic_exc = None
        # DI
        self.__ava_args = (self, *extra_args)
        extra_kwargs = extra_kwargs or {}
        self.__ava_kwargs = (extra_kwargs).copy()
        self._exc_ignored = (
            (*exception_ignored, InterruptNotice, BreakLoop)
            if not __flags__.DISABLE_EXC_IGNORED
            else ()
        )
        # Cache
        self._di_cache = DICache(
            args_hash=_fingerprint_args(self.__ava_args, self.__ava_kwargs),
            hash_trustable=True,
        )
        self._ptr_cache = LRUCache(maxsize=ptr_cache_size)

        # Runtime attrs
        object_io = object_io or SuspendObjectStream()
        self.object_io = cast(io_T, object_io)
        self._ret_addr_stack = addr_stack or Stack()
        self._jump_marked = False
        self._interpret_lock = aiologic.Lock()
        self._middleware = middleware

        self._if_flag = False
        self._context_stack = context_stack or Stack()
        # Sub-Parent interpreter relationship management
        self._parent_interpreter = parent_interpreter
        self._sub_interpreters = {}
        self._sub_interpreters_all = None

        self._waiter_fut = None
        if parent_interpreter is not None:
            if (interp := parent_interpreter._top_interpreter) is not None:
                self._top_interpreter = interp  # the top-level interpreter is other
            else:
                self._top_interpreter = (
                    parent_interpreter  # The parent is top-level interpreter
                )
            self._glob_top_mod_lock = (
                parent_interpreter.top_interpreter._glob_top_mod_lock
            )
            with self._glob_top_mod_lock:
                parent_interpreter.top_interpreter.all_sub_interpreters[
                    self._interpreter_id
                ] = self
            parent_interpreter._sub_interpreters[self._interpreter_id] = self

        else:  # This is a top-level interpreter
            self._glob_top_mod_lock = aiologic.Lock()
            self._sub_interpreters_all = {}
            self._top_interpreter = None
        self._pending_stop = False

    def get_graph(self) -> NodeComposeRendered:
        """Return the compiled workflow graph being executed.

        Returns:
            The NodeComposeRendered instance representing the workflow graph.
        """
        return self._graph

    @property
    def id(self) -> str:
        """Return the unique identifier of the workflow interpreter.

        Returns:
            The unique identifier of the workflow interpreter.
        """
        return self._interpreter_id

    @property
    def parent(self) -> WorkflowInterpreter | None:
        """Get the parent interpreter if this is a sub-interpreter.

        Returns:
            The parent WorkflowInterpreter instance, or None if this is a top-level interpreter.
        """
        return self._parent_interpreter

    @property
    def top_interpreter(self) -> WorkflowInterpreter:
        """Get the top-level interpreter.

        Returns:
            The top-level WorkflowInterpreter instance.
        """
        return self._top_interpreter or self

    @property
    def all_sub_interpreters(self) -> dict[str, WorkflowInterpreter]:
        if self._top_interpreter is not None:
            raise RuntimeError(
                f"{self._interpreter_id} is not a top-level interpreter, the real top-level interpreter is {self._top_interpreter.id}"
            )
        assert self._sub_interpreters_all is not None
        return self._sub_interpreters_all

    @property
    def sub_interpreters(self) -> dict[str, WorkflowInterpreter]:
        """Get a dict of sub-interpreters.

        Returns:
            A dict of WorkflowInterpreter instances representing sub-interpreters.
        """
        return self._sub_interpreters

    @property
    def args_hash_trustable(self) -> bool:
        """Get whether the args hash is trustable.

        Returns:
            Whether the args hash is trustable.
        """
        return self._di_cache.hash_trustable

    @property
    def args_hash(self) -> int:
        """Get the args hash."""
        return self._di_cache.args_hash

    def rehash_args(self) -> None:
        pev = self._di_cache.args_hash
        self._di_cache.args_hash = _fingerprint_args(self.__ava_args, self.__ava_kwargs)
        self._di_cache.hash_trustable = True
        if pev != self._di_cache.args_hash:
            self._di_cache.payload.clear()

    @property
    def _ava_args(self) -> tuple:
        return self.__ava_args

    @property
    def _ava_kwargs(self) -> dict:
        return self.__ava_kwargs

    @_ava_args.setter
    def _ava_args(self, value: tuple) -> None:
        self._di_cache.hash_trustable = False
        self.__ava_args = value

    @_ava_kwargs.setter
    def _ava_kwargs(self, value: dict) -> None:
        self._di_cache.hash_trustable = False
        self.__ava_kwargs = value

    def get_exception(self) -> Exception | None:
        """Get the last panic exception."""
        return self._panic_exc

    def reset(self) -> None:
        """Reset the workflow interpreter to its initial state."""
        if self._waiter_fut is not None:
            self._waiter_fut.cancel("Reseted by manual.")
        self._waiter_fut = None
        self._pointer.clear()
        self._pending_stop = False
        self._ret_addr_stack.clear()
        self._jump_marked = False
        self._panic_exc = None
        self._if_flag = False
        self._context_stack.clear()

    def fork_interpreter(
        self,
        compose: NodeComposeRendered | None,
        middleware: Callable[[WorkflowInterpreter], Awaitable[Any]]
        | None
        | object = UNSET,
        object_io: io_T | None = None,
    ) -> "WorkflowInterpreter[io_T]":
        """Fork a new sub-interpreter.

        This method creates a new WorkflowInterpreter instance that shares the same
        state, but you can custom the workflow graph and middleware for the sub-interpreter.

        Since v0.3.2, ``SuspendObjectStream`` is concurrency-safe via the
        **CLCA (Cross Loop Callback-Allocate)** signal design pattern, so the
        parent's ``object_io`` can be safely shared with child interpreters.

        Args:
            compose (NodeComposeRendered | None): The workflow graph for the sub-interpreter.
                If None, it will use the same graph as the parent.
            middleware (Callable[[WorkflowInterpreter], Awaitable[Any]] | None | object):
                The middleware to be used for the sub-interpreter.
                If UNSET, it will use the same middleware as the parent.
                If None, it will not use any middleware.
            object_io (io_T | None): The object I/O stream for the sub-interpreter.
                If None, reuses the parent interpreter's ``object_io`` instance.
                Safe sharing is guaranteed for ``SuspendObjectStream`` (CLCA-safe since v0.3.2);
                other ``io_T`` subtypes must ensure their own thread safety if passed explicitly.

        Returns:
            A new WorkflowInterpreter instance representing the sub-interpreter.
        """
        mdw: Callable[[WorkflowInterpreter], Awaitable[Any]] | None
        if middleware is UNSET and not __flags__.NO_SHARED_MIDDLEWARE:
            mdw = self._middleware
        elif middleware is None:
            mdw = None
        else:
            assert isinstance(middleware, Callable), (
                "Middleware must be a callable that takes a WorkflowInterpreter and returns an Awaitable."
            )
            mdw = middleware
        if compose is None:
            compose = self._graph
        return WorkflowInterpreter[io_T](
            compose,
            object_io=object_io or self.object_io,
            exception_ignored=self._exc_ignored,
            middleware=mdw,
            extra_args=self.__ava_args[1:],  # Exclude self from args
            extra_kwargs=self.__ava_kwargs.copy(),
            parent_interpreter=self,
        )

    @staticmethod
    def markup(fun: fun_T) -> fun_T:  # Used to mark a pointer action
        """Decorator for marking methods that perform jump operations.

        This decorator automatically sets the _jump_marked flag when a jump method
        is called, preventing the pointer from advancing normally after the jump.

        All decorated methods must be instance methods which return None.

        Args:
            fun: The method to decorate as a jump operation.

        Returns:
            A wrapped version of the original method that manages the jump flag.
        """

        @wraps(fun)
        def wrapper(*args, **kwargs):
            self: WorkflowInterpreter = args[0]
            if not self._jump_marked:
                self._jump_marked = True
                fun(*args, **kwargs)

        if not TYPE_CHECKING:
            return wrapper  # Make the behavior of the function visible to type checkers
        return fun

    def unmarkup(self) -> None:
        self._jump_marked = False

    @property
    def jump_marked(self) -> bool:
        return self._jump_marked

    @property
    def if_flag(self) -> bool:
        return self._if_flag

    @if_flag.setter
    def if_flag(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("if_flag must be a boolean value")
        self._if_flag = value

    @property
    def context_stack(self) -> Stack[InterpreterContext]:
        return self._context_stack

    def dump_interpreter(
        self, exclude_deps: bool = True, exclude_stack: bool = True
    ) -> InterpreterContext:
        """Dump the interpreter state into InterpreterContext object

        Returns:
            InterpreterContext: Interpreter context
        """
        return InterpreterContext(
            ptr=self._pointer.copy(),
            exception_ignored=self._exc_ignored,
            s_args=None if exclude_deps else self.__ava_args,
            s_kwargs=None if exclude_deps else self.__ava_kwargs,
            extra={},
            stack=None if exclude_stack else self._ret_addr_stack,
            exception=self._panic_exc,
        )

    def rebase_context(self, ctx: InterpreterContext) -> None:
        """Rebase the interpreter context stack to the current pointer and state.

        Args:
            ctx: The InterpreterContext object to rebase.
        """
        self.rebase_ptr(ctx.ptr)
        self._exc_ignored = ctx.exception_ignored
        if ctx.s_args and ctx.s_kwargs:
            self.__ava_args = ctx.s_args
            self.__ava_kwargs = ctx.s_kwargs
            self._di_cache.hash_trustable = False
        self._ret_addr_stack = ctx.stack or self._ret_addr_stack
        self._panic_exc = ctx.exception

    def rebase_ptr(self, ptr: list[int] | PointerVector) -> None:
        """Rebase the pointer to a new address.

        Args:
            ptr: The new base address vector for the pointer.
        """
        self._pointer.base_addr = (
            list(ptr) if isinstance(ptr, list) else ptr.base_addr.copy()
        )

    @markup
    def jump_to(self, addr: list[int]) -> None:
        """Jump to an absolute address in the workflow graph.

        Args:
            addr: Absolute address vector to jump to.

        Raises:
            NullPointerException: If the target address does not exist.
        """
        if (self._find_addr_or_none(addr)) is None:
            raise NullPointerException(f"{addr} is not a valid address")
        debug_log(f"Jumping to address {addr}")
        self._pointer.far_to(addr)

    @markup
    def jump_near(self, addr: int) -> None:
        """Jump to a relative address within the current scope.

        Args:
            addr: Relative address offset within the current container.
        """
        debug_log(f"Jumping near to address {addr}")
        self._pointer.near_to(addr)

    @markup
    def jump_offset(self, offset: int) -> None:
        """Jump by applying a relative offset to the current pointer.

        Args:
            offset: Integer offset to apply to the current pointer position.
        """
        debug_log(f"Jumping with offset {offset}")
        self._pointer.offset(offset)

    @markup
    def jump_far_ptr(self, offset: list[int]) -> None:
        """Jump using a multi-dimensional offset vector.

        Args:
            offset: Multi-dimensional offset vector to apply to the current pointer.
        """
        debug_log(f"Jumping far to pointer {offset}")
        self._pointer.far_to(offset)

    @markup
    def jump_offset_far(self, offset: list[int]) -> None:
        """Jump using a multi-dimensional offset vector from the current pointer.

        Args:
            offset: Multi-dimensional offset vector to apply to the current pointer.
        """
        debug_log(f"Jumping far with offset {offset}")
        self._pointer.offset_far(offset)

    @markup
    def jump_to_top(self, addr: int) -> None:
        """Jump to an absolute address at the top level of the workflow.

        Args:
            addr: Address index at the top level to jump to.
        """
        debug_log(f"Jumping far to top at {addr}")
        self._pointer.far_to([addr])

    @markup
    def jump_offset_top(self, offset: int) -> None:
        """Jump to the top level with a relative offset.

        Args:
            offset: Offset to apply when jumping to the top level.
        """
        debug_log(f"Jumping to top with offset {offset}")
        self._pointer.offset_far(
            [offset, -((self._pointer[1] if len(self._pointer) > 1 else 0) + 1)]
        )

    async def call_offset(self, offset: int, *ag, interrupt: bool = False, **kw) -> Any:
        """Call a subroutine at a relative offset from the current position.

        Args:
            offset: Relative offset from current pointer position.
            *ag: Additional positional arguments to pass to the subroutine.
            interrupt: Whether to allow interruption during this call.
            **kw: Additional keyword arguments to pass to the subroutine.

        Returns:
            The result of executing the subroutine.
        """
        ptr: PointerVector = self._pointer.copy().offset(offset)
        debug_log(f"Calling with offset {offset} at pointer {ptr}")

        return await self.call_sub(ptr, *ag, interrupt=interrupt, **kw)

    async def call_offset_far(
        self, offset: list[int], *ag, interrupt: bool = False, **kw
    ) -> Any:
        """Call a subroutine at a multi-dimensional offset from the current position.

        Args:
            offset: Multi-dimensional relative offset from current pointer position.
            *ag: Additional positional arguments to pass to the subroutine.
            interrupt: Whether to allow interruption during this call.
            **kw: Additional keyword arguments to pass to the subroutine.

        Returns:
            The result of the subroutine call.
        """
        ptr: PointerVector = self._pointer.copy().offset_far(offset)
        debug_log(f"Calling with far offset {offset} at pointer {ptr}")
        return await self.call_sub(ptr, *ag, interrupt=interrupt, **kw)

    async def call_near(self, addr: int, *ag, interrupt: bool = False, **kw) -> Any:
        """Call a subroutine at a relative address within the current scope.

        Args:
            addr: Relative address within the current container.
            *ag: Additional positional arguments to pass to the subroutine.
            interrupt: Whether to allow interruption during this call.
            **kw: Additional keyword arguments to pass to the subroutine.

        Returns:
            The result of executing the subroutine.
        """
        ptr: PointerVector = self._pointer.copy().near_to(addr)
        debug_log(f"Calling near address {addr} at pointer {ptr}")
        return await self.call_sub(ptr, *ag, interrupt=interrupt, **kw)

    async def call_sub(
        self,
        addr: PointerVector | list[int],
        /,
        *extra_arg,
        interrupt: bool = False,
        **extra_kwargs,
    ) -> Any:
        """Call a subroutine at the specified address.

        This method manages the call stack by pushing the current return address
        and setting up the new execution context.

        Args:
            addr: Absolute address vector of the subroutine to call.
            *extra_arg: Additional positional arguments to pass to the subroutine.
            interrupt: Whether to allow interruption during this call.
            **extra_kwargs: Additional keyword arguments to pass to the subroutine.

        Returns:
            The result of executing the subroutine.
        """
        pev: PointerVector = self._pointer
        self._ret_addr_stack.push(pev)
        self._pointer = addr if isinstance(addr, PointerVector) else PointerVector(addr)
        debug_log(f"Calling subroutine at {addr}")
        try:
            if not interrupt and not self._interpret_lock.async_owned():
                raise RuntimeError(
                    "Subroutine call detected, but lock is not acquired by current coroutine and caller is not in interrupt mode."
                    " Set `interrupt` to True to use outer interrupt mode."
                )
            async with self._interpret_lock if interrupt else NULL_CTX:
                return await (
                    self._middleware(self)
                    if self._middleware
                    else self._call(self.find_addr, *extra_arg, **extra_kwargs)
                )
        finally:
            ptr = self._ret_addr_stack.pop()
            if not self._jump_marked:
                self._pointer = ptr

    @property
    def pending_stop(self) -> bool:
        return self._pending_stop

    async def terminate(self, eol: bool = True):
        """Mark interpreter as terminated, wait for it to finish.

        Args:
            eol (bool, optional): Is this interpreter at the End-Of_Lifecycle. Defaults to True.
                If True, will remove this interpreter from the tree.
        """
        if not self._pending_stop:
            self._pending_stop = True
            if self._waiter_fut and not self._waiter_fut.done():
                await self._waiter_fut
        if eol:
            if parent := self.parent:
                parent.sub_interpreters.pop(self.id, None)
            async with self._glob_top_mod_lock:
                self.top_interpreter.all_sub_interpreters.pop(self.id, None)
            self._parent_interpreter = (
                None  # To avoid circular reference caused memory leak
            )

    def terminate_all_forks(
        self, eol: bool = True, exclude_self: bool = False
    ) -> asyncio.Future[list[BaseException | None]]:
        """Mark all forked interpreters as should be killed.

        Args:
            eol (bool, optional): If all interpreters are at the End-Of-Lifecycle, mark this to True to remove them from the tree. Defaults to True.

        Returns:
            asyncio.Future[list[BaseException | None]]: A future that will be resolved when all forked interpreters are terminated.
        """
        return asyncio.gather(
            *([self.terminate(eol)] if not exclude_self else []),
            *[i.terminate(eol) for i in self.sub_interpreters.values()],
            return_exceptions=True,
        )

    async def terminate_all(
        self, eol: bool = True, exclude_self: bool = False
    ) -> list[BaseException | None]:
        """Mark this interpreter and all sub interpreter to done, wait them.

        Args:
            exclude_self (bool, optional): Exclude self. Defaults to False.
            eol (bool, optional): Is all interpreters end of lifecycle. Defaults to True.

        Returns:
            list: A list of all sub interpreter's exc value or None.
        """
        if self.top_interpreter is not self:
            raise IllegalState("This interpreter is not top level.")
        async with self._glob_top_mod_lock:
            futs = [i.terminate(eol) for i in self.all_sub_interpreters.values()]
        return await asyncio.gather(
            *([self.terminate(eol)] if not exclude_self else []),
            *futs,
            return_exceptions=True,
        )

    async def run(self):
        """Execute the entire workflow to completion.

        This method runs the workflow until all nodes have been processed or
        an interrupt occurs.
        """
        async for _ in self.run_step_by():
            pass

    async def run_step_by(self) -> AsyncGenerator[Any, None]:
        """Execute the workflow step by step, yielding results from each node.

        This generator method executes one node at a time and yields its result,
        allowing for external monitoring and interruption between steps.

        Yields:
            The result of each executed node in sequence.

        Raises:
            RuntimeError: If runtime dependencies cannot be resolved.
            InterruptNotice: When an external interrupt is requested.
        """
        exc_val: BaseException | None = None
        if self._panic_exc is not None:
            logger.debug("Recovered from panic.")
            self._panic_exc = None
        if self._waiter_fut is not None and not self._waiter_fut.done():
            raise IllegalState(
                "Cannot start a new workflow while one is already running"
            )
        try:
            self._waiter_fut = asyncio.Future()
            session_args = list(self.__ava_args)
            session_kwargs: dict[str, Any] = self.__ava_kwargs
            runtime_args: dict[int, DependsFactory] = {  # index -> DependsFactory
                k: v
                for k, v in enumerate(session_args)
                if isinstance(v, DependsFactory)
            }
            runtime_kwargs = {
                k: v for k, v in session_kwargs.items() if isinstance(v, DependsFactory)
            }
            if runtime_args or runtime_kwargs:
                if not await MatcherFactory._do_runtime_resolve(
                    runtime_args=runtime_args,
                    runtime_kwargs=runtime_kwargs,
                    args2update=session_args,
                    kwargs2update=session_kwargs,
                    session_args=session_args,
                    session_kwargs=session_kwargs,
                    exception_ignored=self._exc_ignored,
                ):
                    raise RuntimeError("Runtime arguments cannot be resolved")
            self.__ava_args = tuple(session_args)
            self.rehash_args()
            if __flags__.WORKFLOW_DI_PRELOAD_CACHE:
                await self._refresh_di_cache_full()
            graph = self.get_graph()
            while True:
                await self.object_io._wait_for_continue(PC_CHECKPOINT)
                if self._pending_stop:
                    self._pending_stop = False
                    break
                async with self._interpret_lock:
                    if not self._pointer:
                        if not graph:
                            break
                        self._pointer.append(0)
                    yield (
                        await self._middleware(self)
                        if self._middleware
                        else await self._call()
                    )
                    if self._jump_marked:
                        self._jump_marked = False
                        continue

                    if not self.advance_pointer():
                        break
        except InterruptNotice as e:
            logger.info(f"Interrupt notice at {self._pointer} :{e.message}")
            logger.info("Cleaning up pointer stack...")
            if not isinstance(e, InterruptKeepContext):
                self.reset()

        except BaseException as e:
            if isinstance(e, Exception):
                logger.warning(
                    "*** workflow exception detected ***: "
                    f"`{e}@{e.__class__.__name__}` at ptr {self._pointer}"
                )
                debug_log(f"Interpreter: {self.id} at {hex(id(self))}")
            exc_val = e
            raise
        finally:
            if exc_val is not None and isinstance(exc_val, Exception):
                self._panic_exc = exc_val
                logger.warning("Aborted (Interpreter Dumped)")
            if self._waiter_fut and (
                getattr(self._waiter_fut, "_asyncio_future_blocking", False)
                or getattr(self._waiter_fut, "_blocking", False)
            ):  # To ensure the waiter future is really waiting
                if exc_val is not None:
                    self._waiter_fut.set_exception(exc_val)
                else:
                    self._waiter_fut.set_result(None)
            self._waiter_fut = None

    async def _refresh_di_cache_full(self):
        """Fully refresh DI cache of nodes.

        !!!WARNINGS!!!: This method should only be used in initializing phase, because it's costy.
        """
        if not self._di_cache.hash_trustable:
            raise DependsResolveFailed(
                "Args hash is not trustable! Please use `rehash_args()` to rehash args."
            )

        async def _worker(node: BaseNode, ptr_hash: int):
            if self._di_cache.payload.currsize >= self._di_cache.payload.maxsize:
                return
            kw = await self._rslv_node(node, self.__ava_args, self.__ava_kwargs)

            self._di_cache.payload[ptr_hash] = kw

        ptr = PointerVector([0])
        logger.debug(f"Preloading DI cache for {self.id}")
        coro: list[Coroutine[Any, Any, Any]] = []
        with TimeInsighter() as t:
            while True:
                if self._di_cache.payload.currsize >= self._di_cache.payload.maxsize:
                    break
                node = self.find_addr(ptr.base_addr)
                assert isinstance(node, BaseNode)
                coro.append(_worker(node, hash((hash(ptr), self._di_cache.args_hash))))
                if len(coro) > __flags__.WORKFLOW_DI_PRELOAD_BATCH:
                    await asyncio.gather(*coro)
                    await asyncio.sleep(0)
                    coro.clear()
                if not self.advance_pointer(ptr):
                    break
            if coro:
                await asyncio.gather(*coro)
        logger.debug(f"DI cache preloaded in {t.t_diff.total_seconds()}")

    @property
    def is_running(self) -> bool:
        """Check if the interpreter is running.

        Returns:
            True if the interpreter is running, False otherwise.
        """
        if fut := self._waiter_fut:
            return not fut.done()
        return False

    @property
    def wait(self) -> asyncio.Future[None]:
        """Get the wait future.

        !!!WARN!!!: Please do not manually set result for this future.
        Although this interpreter may done, but sub-interpreters may still running.

        Returns:
            The wait future.
        """
        if (fut := self._waiter_fut) is None:
            raise IllegalState("Interpreter is not running.")
        return fut

    @overload
    async def wait_all_forks(self, *, exclude_self: bool = False) -> None: ...
    @overload
    async def wait_all_forks(
        self, return_exc: Literal[True], exclude_self: bool = False
    ) -> list[BaseException | None]: ...
    @overload
    async def wait_all_forks(
        self, return_exc: Literal[False], exclude_self: bool = False
    ) -> None: ...
    async def wait_all_forks(
        self, return_exc: bool = False, exclude_self: bool = False
    ) -> None | list[BaseException | None]:

        futs: Sequence[Awaitable] = ([(self.wait)] if not exclude_self else []) + [
            (sub.wait_all_forks()) for sub in self.sub_interpreters.values()
        ]
        rst = await asyncio.gather(
            *futs,
            return_exceptions=return_exc,
        )
        if return_exc:
            return rst

    @overload
    async def wait_all(self, *, exclude_self: bool = False) -> None: ...
    @overload
    async def wait_all(
        self, return_exc: Literal[True], exclude_self: bool = False
    ) -> list[BaseException | None]: ...
    @overload
    async def wait_all(
        self, return_exc: Literal[False], exclude_self: bool = False
    ) -> None: ...

    async def wait_all(
        self, return_exc: bool = False, exclude_self: bool = False
    ) -> None | list[BaseException | None]:
        """Wait all interpreter (self and sub), only when this interpreter is the top-level interpreter.

        Args:
            return_exc (bool, optional): Return the exception if occured. Defaults to False.
            exclude_self (bool, optional): Exclude self. Defaults to False.
        Returns:
            None: No return value.
        """
        if self.top_interpreter is not self:
            raise IllegalState("Only top-level interpreter can wait all interpreters.")
        async with self._glob_top_mod_lock:
            futs: Sequence[Awaitable] = ([(self.wait)] if not exclude_self else []) + [
                (sub.wait) for sub in self.all_sub_interpreters.values()
            ]
        rst = await asyncio.gather(
            *futs,
            return_exceptions=return_exc,
        )
        if return_exc:
            return rst

    def advance_pointer(self, ptr: PointerVector | None = None) -> bool:
        """Advance the execution pointer to the next node with ptr arg by the graph.

        This method implements the logic for navigating through
        nested workflow structures, handling both sequential execution and
        hierarchical traversal.

        Args:
            ptr (PointerVector, optional): ptr to advance to. If None, advance to the next node in the current container of interpreter.

        Returns:
            bool: True if the pointer was successfully advanced, False if at the end of workflow.
        """

        pointer: PointerVector = ptr if ptr is not None else self._pointer
        ptr_hash = hash(pointer)
        if (
            not __flags__.NO_ADDRESSING_CACHE
            and ptr is None
            and (rst := self._ptr_cache.get(ptr_hash)) is not None
            and rst != pointer.base_addr
        ):
            self._pointer.base_addr = rst.copy()
            return True

        if not pointer:
            logger.debug("Pointer is empty, cannot advance")
            return False
        graph: NodeComposeRendered = self.get_graph()
        current_container: BaseNode | NodeComposeRendered = graph
        for idx in pointer.base_addr[:-1]:
            if isinstance(current_container, NodeComposeRendered):
                current_container = current_container[idx]
            else:
                return False

        end_idx = pointer[-1]
        if not isinstance(current_container, NodeComposeRendered):
            return False

        current_node: BaseNode | NodeComposeRendered = current_container[end_idx]
        if isinstance(current_node, NodeComposeRendered) and current_node:
            pointer.append(0)
            debug_log(f"Entered nested container, new pointer: {pointer}")
            self._ptr_cache[ptr_hash] = pointer.base_addr.copy()
            return True

        next_idx = end_idx + 1
        if next_idx < len(current_container):
            # Check if the next node is a NodeComposeRendered that should be entered immediately
            next_node = current_container[next_idx]
            if isinstance(next_node, NodeComposeRendered) and next_node:
                pointer[-1] = next_idx
                pointer.append(0)
                debug_log(
                    f"Advanced to and entered nested container, new pointer: {pointer}"
                )
            else:
                pointer[-1] = next_idx
                debug_log(f"Advanced to next sibling node, new pointer: {pointer}")
            self._ptr_cache[ptr_hash] = pointer.base_addr.copy()
            return True

        while pointer:
            pointer.pop()
            if not pointer:
                logger.debug("Reached end of workflow, no more nodes to process")
                return False

            parent_path: list[int] = pointer.base_addr[:-1]
            parent_container: BaseNode | NodeComposeRendered = graph
            for idx in parent_path:
                if isinstance(parent_container, NodeComposeRendered):
                    parent_container = parent_container[idx]
                else:
                    debug_log(f"Failed to traverse to parent container at index {idx}")
                    return False

            if isinstance(parent_container, NodeComposeRendered):
                current_parent_idx = pointer[-1]
                if current_parent_idx + 1 < len(parent_container):
                    next_parent_node = parent_container[current_parent_idx + 1]
                    if (
                        isinstance(next_parent_node, NodeComposeRendered)
                        and next_parent_node
                    ):
                        pointer[-1] = current_parent_idx + 1
                        pointer.append(0)
                    else:
                        pointer[-1] = current_parent_idx + 1
                    self._ptr_cache[ptr_hash] = pointer.base_addr.copy()
                    return True

        logger.debug("Failed to advance pointer through any path")
        return False

    def find_addr_alias(self, alias: str) -> list[int]:
        """Find the address vector for a node by its alias.

        Args:
            alias: The alias name of the target node.

        Returns:
            The address vector (list of indices) pointing to the node.

        Raises:
            NullPointerException: If the alias does not exist in the graph.
        """
        if alias not in self.get_graph().alias2vector_map:
            raise NullPointerException(f"{alias} is not a valid alias")
        return self.get_graph().alias2vector_map[alias]

    def find_node_alias(self, alias: str) -> BaseNode | NodeComposeRendered:
        """Find a node by its alias and return the node object.

        Args:
            alias: The alias name of the target node.

        Returns:
            The node object corresponding to the alias.
        """
        return self.find_addr(self.find_addr_alias(alias))

    def _find_addr_or_none(
        self, addr: list[int]
    ) -> BaseNode | NodeComposeRendered | None:
        """Find a node at the specified address, returning None if not found.

        Args:
            addr: Address vector to look up.

        Returns:
            The node at the specified address, or None if it doesn't exist.
        """
        graph: NodeComposeRendered = self.get_graph()
        current_chunk: NodeComposeRendered | BaseNode = graph

        for i, chunk in enumerate(addr):
            if isinstance(current_chunk, NodeComposeRendered):
                if chunk >= len(current_chunk):
                    return None
                current_chunk = current_chunk[chunk]
            else:
                # If we reach a BaseNode before consuming all address components, it's invalid
                if i < len(addr) - 1:
                    return None
                break

        return current_chunk

    def find_addr(self, addr: list[int]) -> BaseNode | NodeComposeRendered:
        """Find a node at the specified address.

        Args:
            addr: Address vector to look up.

        Returns:
            The node at the specified address.

        Raises:
            NullPointerException: If the address does not exist in the graph.
        """
        if (node := self._find_addr_or_none(addr)) is not None:
            return node
        else:
            raise NullPointerException(f"Node at {addr} does not exist")

    async def _rslv_node(
        self, node: BaseNode, ava_args: tuple, ava_kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        fun = node.func
        fail, kw_rsved, kw2rsev = MatcherFactory._resolve_dependencies(
            node.fun_sign
            if not __flags__.NO_DEPENDENCY_META_CACHE
            else sign_func(node.func),
            ava_args,
            ava_kwargs,
        )
        if fail is not None:
            raise DependsResolveFailed(
                f"Function {fun.__name__} in {node.tag} could not be resolved due to reason `{fail.value}`"
            )
        if kw2rsev and not await MatcherFactory._do_runtime_resolve(
            runtime_args={},
            runtime_kwargs=kw2rsev,
            args2update=[],
            kwargs2update=kw_rsved,
            session_args=list(ava_args),
            session_kwargs=ava_kwargs,
            exception_ignored=self._exc_ignored,
        ):
            raise DependsInjectFailed(
                "Runtime resolve failed for kwargs: {}".format(
                    ", ".join(kw2rsev.keys())
                )
            )
        return kw_rsved

    async def _call(
        self,
        addr_getter: Callable[[list[int]], BaseNode | NodeComposeRendered]
        | None = None,
        *extra_args: Any,
        **extra_kwargs: Any,
    ) -> Any:
        """Execute a single node at the current pointer position.

        This internal method handles the complete execution cycle for a node,
        including dependency resolution, pre-checks, and actual function execution.

        Args:
            addr_getter: Optional function to retrieve the node at a specific address.
            *extra_args: Additional positional arguments for the node execution.
            **extra_kwargs: Additional keyword arguments for the node execution.

        Returns:
            The result of executing the node.

        Raises:
            DependsResolveFailed: If node dependencies cannot be resolved.
            DependsInjectFailed: If dependency injection fails at runtime.
            RuntimeError: If attempting to call a NodeCompose directly.
        """
        global nop
        addr_getter = addr_getter or self.find_addr
        node: BaseNode | NodeComposeRendered = addr_getter(self._pointer.base_addr)
        if isinstance(node, NodeComposeRendered):
            if __flags__.ALLOW_CALL_NODECOMPOSE:
                return
            raise RuntimeError(
                f"Cannot call a NodeCompose in addr {self._pointer.base_addr}."
            )
        await self.object_io._wait_for_continue(node.tag)

        node._pre_check(self)

        ava_args = self.__ava_args
        if extra_args:
            ava_args += extra_args
        if extra_kwargs:  # To avoid a copy cost.
            ava_kwargs = self.__ava_kwargs.copy()
            if any(k in ava_kwargs for k in extra_kwargs.keys()):
                raise DependsInjectFailed(
                    "Cannot override existing kwargs: {}".format(
                        ", ".join(extra_kwargs.keys())
                    )
                )
            ava_kwargs.update(extra_kwargs)
        else:
            ava_kwargs = self.__ava_kwargs
        if extra_args or extra_kwargs:  # should rebuild hash:
            code = _fingerprint_args(ava_args, ava_kwargs)
        else:
            code = self._di_cache.args_hash

        fun = node.func
        if (
            not __flags__.WORKFLOW_DI_NO_CACHE
            or not self._di_cache.hash_trustable
            or (
                kw_rsved := self._di_cache.payload.get(
                    hash((hash(self._pointer), code))
                )
            )
            is None
        ):
            kw_rsved = await self._rslv_node(node, ava_args, ava_kwargs)
            if not __flags__.WORKFLOW_DI_NO_CACHE:
                self._di_cache.payload[hash((hash(self._pointer), code))] = kw_rsved
        logger.debug(f"Running node {node.tag}:{node.func.__name__}")
        debug_log(
            f"Address is {self._pointer}, Type of node is {node.__class__.__name__}"
        )
        if iscoroutinefunction(fun):
            return await fun(**kw_rsved)
        elif node.wrap_to_async and not __flags__.FORCE_NOT_WRAP_TO_ASYNC:
            return await asyncio.to_thread(fun, **kw_rsved)
        else:
            return fun(**kw_rsved)


__all__ = ["PC_CHECKPOINT", "WorkflowInterpreter", "fun_T", "io_T"]
