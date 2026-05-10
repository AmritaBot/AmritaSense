from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from copy import deepcopy
from functools import wraps
from inspect import iscoroutinefunction
from typing import Any, TypeAlias

from amrita_core import SuspendObjectStream, logger
from amrita_core.hook.matcher import DependsFactory, MatcherFactory

from amrita_sense.exceptions import (
    DependsInjectFailed,
    DependsResolveFailed,
    InterruptNotice,
    NullPointerException,
)
from amrita_sense.node.core import BaseNode, NodeComposeRendered
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.types import PointerVector, Stack

PC_CHECKPOINT = (
    "WorkflowPC::each_node"  # When stop at this checkpoint, change address is allowed.
)


class WorkflowInterpreter:
    _graph: NodeComposeRendered
    _pointer: PointerVector
    _ava_args: tuple
    _ava_kwargs: dict[str, Any]
    _exc_ignored: tuple[type[BaseException], ...]
    object_io: SuspendObjectStream
    _ret_addr_stack: Stack[PointerVector]
    _jump_marked: bool

    def __init__(
        self,
        node_compose: NodeComposeRendered | SelfCompileInstruction,
        object_io: SuspendObjectStream | None = None,
        *,
        exception_ignored: tuple[type[BaseException], ...],
        extra_args: tuple,
        extra_kwargs: dict[str, Any],
        addr_stack: Stack[PointerVector] | None = None,
    ):
        if isinstance(node_compose, SelfCompileInstruction):
            node_compose = node_compose.extract().render()
        self._graph = node_compose
        self._pointer = PointerVector()
        self._ava_args = (self, *extra_args)
        self._ava_kwargs = deepcopy(extra_kwargs)
        self._exc_ignored = (*exception_ignored, InterruptNotice)
        self.object_io = object_io or SuspendObjectStream()
        self._ret_addr_stack = addr_stack or Stack()
        self._jump_marked = False

    def get_graph(self) -> NodeComposeRendered:
        return self._graph

    def find_addr_alias(self, alias: str) -> list[int]:
        if alias not in self._graph.alias2vector_map:
            raise NullPointerException(f"{alias} is not a valid alias")
        return self._graph.alias2vector_map[alias]

    def find_node_alias(self, alias: str) -> BaseNode | NodeComposeRendered:
        return self.find_addr(self.find_addr_alias(alias))

    @staticmethod
    def markup(fun: Callable[..., Any]):  # Used to mark a jump action
        @wraps(fun)
        def wrapper(*args, **kwargs):
            self: WorkflowInterpreter = args[0]
            if not self._jump_marked:
                self._jump_marked = True
                return fun(*args, **kwargs)

        return wrapper

    @markup
    def jump_to(self, addr: list[int]) -> None:
        if (self._find_addr_or_none(addr)) is None:
            raise NullPointerException(f"{addr} is not a valid address")
        logger.info(f"Jumping to address {addr}")
        self._pointer.far_to(addr)

    @markup
    def jump_near(self, addr: int) -> None:
        logger.info(f"Jumping near to address {addr}")
        self._pointer.near_to(addr)

    @markup
    def jump_offset(self, offset: int) -> None:
        logger.info(f"Jumping with offset {offset}")
        self._pointer.offset(offset)

    @markup
    def jump_far_ptr(self, offset: list[int]) -> None:
        logger.info(f"Jumping far to pointer {offset}")
        self._pointer.far_to(offset)

    @markup
    def jump_to_top(self, addr: int) -> None:
        logger.info(f"Jumping far to top at {addr}")
        self._pointer.far_to([addr])

    @markup
    def jump_offset_top(self, offset: int) -> None:
        logger.info(f"Jumping to top with offset {offset}")
        self._pointer.offset_far(
            [offset, -((self._pointer[1] if len(self._pointer) > 1 else 0) + 1)]
        )

    async def call_offset(self, offset: int, *ag, **kw) -> Any:
        ptr: PointerVector = self._pointer.copy().offset(offset)
        logger.info(f"Calling with offset {offset} at pointer {ptr}")
        return await self.call_sub(ptr, *ag, **kw)

    async def call_near(self, addr: int, *ag, **kw) -> Any:
        ptr: PointerVector = self._pointer.copy().near_to(addr)
        logger.info(f"Calling near address {addr} at pointer {ptr}")
        return await self.call_sub(ptr, *ag, **kw)

    async def call_sub(
        self, addr: PointerVector | list[int], /, *extra_arg, **extra_kwargs
    ) -> Any:
        pev: PointerVector = self._pointer
        self._ret_addr_stack.push(pev)
        self._pointer = addr if isinstance(addr, PointerVector) else PointerVector(addr)
        logger.info(f"Calling subroutine at {addr}")
        try:
            return await self._call(self.find_addr, *extra_arg, **extra_kwargs)
        finally:
            ptr = self._ret_addr_stack.pop()
            if not self._jump_marked:
                self._pointer = ptr

    async def run(self):
        async for _ in self.run_step_by():
            pass

    async def run_step_by(self) -> AsyncGenerator[Any, None]:
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
            while True:
                if not self._pointer:
                    if not self._graph:
                        break
                    self._pointer.append(0)
                await self.object_io._wait_for_continue(PC_CHECKPOINT)
                yield await self._call()
                if self._jump_marked:
                    self._jump_marked = False
                    continue

                if not self._advance_pointer():
                    break
        except InterruptNotice as e:
            logger.info(f"Interrupt notice at {self._pointer} :{e.message}")
            logger.debug("Cleaning up pointer stack...")
            self._ret_addr_stack.clear()
            self._pointer.clear()
            self._jump_marked = False

    def _advance_pointer(self) -> bool:
        if not self._pointer:
            logger.debug("Pointer is empty, cannot advance")
            return False

        pointer: PointerVector = self._pointer
        logger.debug(f"Advancing pointer from {pointer}")

        current_container: BaseNode | NodeComposeRendered = self._graph
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
        if isinstance(current_node, NodeComposeRendered) and current_node._graph:
            pointer.append(0)
            logger.debug(f"Entered nested container, new pointer: {pointer}")
            return True

        next_idx = end_idx + 1
        if next_idx < len(current_container._graph):
            # Check if the next node is a NodeComposeRendered that should be entered immediately
            next_node = current_container[next_idx]
            if isinstance(next_node, NodeComposeRendered) and next_node._graph:
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
            parent_container: BaseNode | NodeComposeRendered = self._graph
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
                if current_parent_idx + 1 < len(parent_container._graph):
                    next_parent_node = parent_container[current_parent_idx + 1]
                    if (
                        isinstance(next_parent_node, NodeComposeRendered)
                        and next_parent_node._graph
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
        graph: NodeComposeRendered = self._graph
        current_chunk: NodeComposeRendered | BaseNode = graph

        for i, chunk in enumerate(addr):
            if isinstance(current_chunk, NodeComposeRendered):
                if chunk >= len(current_chunk._graph):
                    return None
                current_chunk = current_chunk[chunk]
            else:
                # If we reach a BaseNode before consuming all address components, it's invalid
                if i < len(addr) - 1:
                    return None
                break

        return current_chunk

    def find_addr(self, addr: list[int]) -> BaseNode | NodeComposeRendered:
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

        addr_getter = addr_getter or self.find_addr
        node: BaseNode | NodeComposeRendered = addr_getter(self._pointer.base_addr)
        if isinstance(node, NodeComposeRendered):
            raise RuntimeError("Cannot call a NodeCompose.")
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

        success, args, kw_rsved, kw2rsev = MatcherFactory._resolve_dependencies(
            node.fun_sign, ava_args, ava_kwargs
        )
        if not success:
            raise DependsResolveFailed(
                f"Function {fun.__name__} in {node.tag} could not be resolved due to missing argument dependencies."
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
            return await fun(*args, **kw_rsved)
        elif node.wrap_to_async:
            return await asyncio.to_thread(fun, *args, **kw_rsved)
        else:
            return fun(*args, **kw_rsved)


WorkflowPC: TypeAlias = WorkflowInterpreter
