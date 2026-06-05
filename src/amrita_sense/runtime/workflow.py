from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import nullcontext
from functools import wraps
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

import aiologic
from typing_extensions import deprecated

from amrita_sense.exceptions import (
    BreakLoop,
    DependsInjectFailed,
    DependsResolveFailed,
    InterruptNotice,
    NullPointerException,
)
from amrita_sense.hook.matcher import DependsFactory, MatcherFactory
from amrita_sense.logging import logger
from amrita_sense.node.core import BaseNode, NodeComposeRendered
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.streaming import SuspendObjectStream
from amrita_sense.types import PointerVector, Stack

PC_CHECKPOINT = "WorkflowInterpreter::each_node"
NULL_CTX = nullcontext()
io_T = TypeVar("io_T", bound=SuspendObjectStream, covariant=True)
fun_T = TypeVar("fun_T", bound=Callable[..., Any], covariant=True)


class WorkflowInterpreter(Generic[io_T]):
    """Main workflow interpreter and execution engine.

    This class is responsible for executing compiled workflow graphs by managing
    the execution pointer, handling control flow operations (jumps, calls, loops),
    and providing dependency injection services. It implements an interpreter/VM
    pattern for dynamic workflow execution.

    Attributes:
        _graph: The compiled workflow graph to execute.
        _pointer: Current execution pointer in the workflow graph.
        _ava_args: Available arguments for dependency injection.
        _ava_kwargs: Available keyword arguments for dependency injection.
        _exc_ignored: Exception types that should not be caught by TRY/CATCH blocks.
        object_io: I/O stream for external communication and interruption.
        _ret_addr_stack: Stack for managing return addresses during subroutine calls.
        _jump_marked: Flag indicating if a jump operation has been performed.
        _interpret_lock: Lock for ensuring thread-safe execution.
        _middleware: Optional middleware function for custom execution logic.
    """

    _graph: NodeComposeRendered
    _pointer: PointerVector
    _ava_args: tuple
    _ava_kwargs: dict[str, Any]
    _exc_ignored: tuple[type[BaseException], ...]
    object_io: io_T
    _ret_addr_stack: Stack[PointerVector]
    _jump_marked: bool
    _interpret_lock: aiologic.Lock
    _middleware: Callable[["WorkflowInterpreter"], Awaitable[Any]] | None
    __slots__ = (
        "_ava_args",
        "_ava_kwargs",
        "_exc_ignored",
        "_graph",
        "_interpret_lock",
        "_jump_marked",
        "_middleware",
        "_pointer",
        "_ret_addr_stack",
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
        middleware: Callable[["WorkflowInterpreter"], Awaitable[Any]] | None = None,
    ):
        """Initialize the workflow interpreter with a compiled workflow graph.

        Args:
            node_compose: The workflow graph to execute, either pre-rendered or a self-compiling instruction.
            object_io: Optional I/O stream for external communication. Defaults to a new SuspendObjectStream.
            exception_ignored: Exception types that should bypass TRY/CATCH handlers.
            extra_args: Additional positional arguments for dependency injection.
            extra_kwargs: Additional keyword arguments for dependency injection.
            addr_stack: Optional pre-initialized return address stack.
        """
        if isinstance(node_compose, SelfCompileInstruction):
            node_compose = node_compose.extract().render()
        self._graph = node_compose
        self._pointer = PointerVector()
        self._ava_args = (self, *extra_args)
        extra_kwargs = extra_kwargs or {}
        self._ava_kwargs = (extra_kwargs).copy()
        self._exc_ignored = (*exception_ignored, InterruptNotice, BreakLoop)
        object_io = object_io or SuspendObjectStream()
        self.object_io = cast(io_T, object_io)
        self._ret_addr_stack = addr_stack or Stack()
        self._jump_marked = False
        self._interpret_lock = aiologic.Lock()
        self._middleware = middleware

    def get_graph(self) -> NodeComposeRendered:
        """Return the compiled workflow graph being executed.

        Returns:
            The NodeComposeRendered instance representing the workflow graph.
        """
        return self._graph

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
        logger.info(f"Jumping to address {addr}")
        self._pointer.far_to(addr)

    @markup
    def jump_near(self, addr: int) -> None:
        """Jump to a relative address within the current scope.

        Args:
            addr: Relative address offset within the current container.
        """
        logger.info(f"Jumping near to address {addr}")
        self._pointer.near_to(addr)

    @markup
    def jump_offset(self, offset: int) -> None:
        """Jump by applying a relative offset to the current pointer.

        Args:
            offset: Integer offset to apply to the current pointer position.
        """
        logger.info(f"Jumping with offset {offset}")
        self._pointer.offset(offset)

    @markup
    def jump_far_ptr(self, offset: list[int]) -> None:
        """Jump using a multi-dimensional offset vector.

        Args:
            offset: Multi-dimensional offset vector to apply to the current pointer.
        """
        logger.info(f"Jumping far to pointer {offset}")
        self._pointer.far_to(offset)

    @markup
    def jump_offset_far(self, offset: list[int]) -> None:
        """Jump using a multi-dimensional offset vector from the current pointer.

        Args:
            offset: Multi-dimensional offset vector to apply to the current pointer.
        """
        logger.info(f"Jumping far with offset {offset}")
        self._pointer.offset_far(offset)

    @markup
    def jump_to_top(self, addr: int) -> None:
        """Jump to an absolute address at the top level of the workflow.

        Args:
            addr: Address index at the top level to jump to.
        """
        logger.info(f"Jumping far to top at {addr}")
        self._pointer.far_to([addr])

    @markup
    def jump_offset_top(self, offset: int) -> None:
        """Jump to the top level with a relative offset.

        Args:
            offset: Offset to apply when jumping to the top level.
        """
        logger.info(f"Jumping to top with offset {offset}")
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
        logger.info(f"Calling with offset {offset} at pointer {ptr}")
        return await self.call_sub(ptr, *ag, interrupt, **kw)

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
        logger.info(f"Calling with far offset {offset} at pointer {ptr}")
        return await self.call_sub(ptr, *ag, interrupt, **kw)

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
        logger.info(f"Calling near address {addr} at pointer {ptr}")
        return await self.call_sub(ptr, *ag, interrupt, **kw)

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
        logger.info(f"Calling subroutine at {addr}")
        try:
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
        try:
            session_args = list(self._ava_args)
            session_kwargs: dict[str, Any] = self._ava_kwargs
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
            self._ava_args = tuple(session_args)
            graph = self.get_graph()
            while True:
                await self.object_io._wait_for_continue(PC_CHECKPOINT)
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
            logger.debug("Cleaning up pointer stack...")
            self._ret_addr_stack.clear()
            self._pointer.clear()
            self._jump_marked = False

    @deprecated(
        "Method of `_advance_pointer` is now `advance_pointer`, this compile method will be removed in `v0.3.0`",
        category=DeprecationWarning,
    )
    @property
    def _advance_pointer(self):
        return self.advance_pointer

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
        if not pointer:
            logger.debug("Pointer is empty, cannot advance")
            return False

        logger.debug(f"Advancing pointer from {pointer}")
        graph: NodeComposeRendered = self.get_graph()
        current_container: BaseNode | NodeComposeRendered = graph
        for idx in pointer.base_addr[:-1]:
            if isinstance(current_container, NodeComposeRendered):
                current_container = current_container[idx]
            else:
                logger.debug(f"Failed to traverse to container at index {idx}")
                return False

        end_idx = pointer[-1]
        if not isinstance(current_container, NodeComposeRendered):
            logger.debug("Current container is not a NodeComposeRendered")
            return False

        current_node: BaseNode | NodeComposeRendered = current_container[end_idx]
        if isinstance(current_node, NodeComposeRendered) and current_node:
            pointer.append(0)
            logger.debug(f"Entered nested container, new pointer: {pointer}")
            return True

        next_idx = end_idx + 1
        if next_idx < len(current_container):
            # Check if the next node is a NodeComposeRendered that should be entered immediately
            next_node = current_container[next_idx]
            if isinstance(next_node, NodeComposeRendered) and next_node:
                pointer[-1] = next_idx
                pointer.append(0)
                logger.debug(
                    f"Advanced to and entered nested container, new pointer: {pointer}"
                )
            else:
                pointer[-1] = next_idx
                logger.debug(f"Advanced to next sibling node, new pointer: {pointer}")
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
                    logger.debug(
                        f"Failed to traverse to parent container at index {idx}"
                    )
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
                        logger.debug(
                            f"Backtracked and advanced to nested container, new pointer: {pointer}"
                        )
                    else:
                        pointer[-1] = current_parent_idx + 1
                        logger.debug(
                            f"Backtracked and advanced to next sibling, new pointer: {pointer}"
                        )
                    return True

        logger.debug("Failed to advance pointer through any path")
        return False

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

        addr_getter = addr_getter or self.find_addr
        node: BaseNode | NodeComposeRendered = addr_getter(self._pointer.base_addr)
        if isinstance(node, NodeComposeRendered):
            raise RuntimeError(
                f"Cannot call a NodeCompose in addr {self._pointer.base_addr}."
            )
        await self.object_io._wait_for_continue(node.tag)

        node._pre_check(self)

        ava_args = self._ava_args
        ava_args += extra_args
        if extra_kwargs:  # To avoid a copy cost.
            ava_kwargs = self._ava_kwargs.copy()
            ava_kwargs.update(extra_kwargs)
        else:
            ava_kwargs = self._ava_kwargs

        fun = node.func

        fail, kw_rsved, kw2rsev = MatcherFactory._resolve_dependencies(
            node.fun_sign, ava_args, ava_kwargs
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
        logger.debug(f"Running node {node.tag}:{node.func.__name__}")
        logger.debug(
            f"Address is {self._pointer}, Type of node is {node.__class__.__name__}"
        )
        if iscoroutinefunction(fun):
            return await fun(**kw_rsved)
        elif node.wrap_to_async:
            return await asyncio.to_thread(fun, **kw_rsved)
        else:
            return fun(**kw_rsved)
