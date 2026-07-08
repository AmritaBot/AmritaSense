import sys
from collections.abc import Callable
from types import FrameType
from typing import Any

from typing_extensions import Self

from amrita_sense._unsafe import __flags__
from amrita_sense.exceptions import IllegalState
from amrita_sense.hook.fun_typing import DependencyMeta
from amrita_sense.instructions.workfl_ctrl import NOP
from amrita_sense.node.core import BaseNode, Node, NodeCompose
from amrita_sense.node.self_compile import SelfCompileInstruction
from amrita_sense.runtime.workflow import WorkflowInterpreter


class TryNode(BaseNode):
    tag: str
    func: Callable[..., Any]
    wrap_to_async: bool
    address_able: bool
    fun_frame: FrameType
    fun_sign: DependencyMeta
    _do_node_addr: int
    _catch_addr_chain: list[tuple[type[BaseException], int]]
    _finally_addr: int | None
    _else_addr: int | None
    _escape_addr: int

    __slots__ = (
        "_catch_addr_chain",
        "_do_node_addr",
        "_else_addr",
        "_escape_addr",
        "_finally_addr",
        "address_able",
        "fun_frame",
        "fun_sign",
        "func",
        "tag",
        "wrap_to_async",
    )

    def __init__(
        self,
        do_addr: int,
        catch_lst: list[tuple[type[BaseException], int]],
        fin_addr: int | None,
        els_addr: int | None,
        escape_addr: int,
    ) -> None:
        self._do_node_addr = do_addr
        self._catch_addr_chain = catch_lst
        self._finally_addr = fin_addr
        self._else_addr = els_addr
        self._escape_addr = escape_addr
        self._init(
            self._worker, "TryNode::worker", address_able=False, wrap_to_async=False
        )

    async def _worker(self, pc: WorkflowInterpreter):
        try:
            await pc.call_near(self._do_node_addr)
        except BaseException as exc_val:
            exc_type, _, exc_tb = sys.exc_info()
            if not __flags__.DISABLE_EXC_IGNORED and isinstance(
                exc_val, pc._exc_ignored
            ):
                raise
            idx: int | None = None
            for exc, idx in self._catch_addr_chain:
                if isinstance(exc_val, exc):
                    break
            if idx is not None:
                await pc.call_near(
                    idx,
                    exc_type=exc_type,
                    exc_val=exc_val,
                    exc_tb=exc_tb,
                )
        else:
            if self._else_addr is not None:
                await pc.call_near(self._else_addr)
        finally:
            if self._finally_addr is not None:
                await pc.call_near(self._finally_addr)
        pc.jump_near(self._escape_addr)


class TryClause(SelfCompileInstruction):
    _do: Node
    _catch_then: list[tuple[type[BaseException], Node]]
    _then: Node | None = None
    _finally: Node | None = None

    def __init__(self, do: Node) -> None:
        self._do = do
        self._catch_then = []

    @property
    def CATCH(self) -> Callable[[type[BaseException], Node], Self]:
        if self._finally is not None:
            raise IllegalState("Cannot add catch after finally")

        def _inner(exc: type[BaseException], then: Node) -> Self:
            self._catch_then.append((exc, then))
            return self

        return _inner

    @property
    def FINALLY(self) -> Callable[[Node], Self]:
        def _inner(finally_node: Node) -> Self:
            if self._finally is not None:
                raise IllegalState("Cannot add finally after finally")
            self._finally = finally_node
            return self

        return _inner

    @property
    def THEN(self) -> Callable[[Node], Self]:
        def _inner(nd: Node):
            if self._then is not None:
                raise IllegalState("Cannot add THEN after THEN")
            self._then = nd
            return self

        return _inner

    def extract(self) -> NodeCompose:
        if not self._catch_then and not self._finally:
            raise IllegalState("Try Clause must have at least one catch or finally")
        cp: list[BaseNode] = [NOP, self._do]
        ctl: list[Node] = []
        catch_chain: list[tuple[type[BaseException], int]] = []
        or_len: int = len(cp)

        for idx, (exc, nd) in enumerate(self._catch_then):
            ctl.append(nd)
            catch_chain.append((exc, idx + or_len))
        cp.extend(ctl)
        del ctl

        then_addr = None
        finally_addr = None
        if self._then:
            cp += (self._then,)
            then_addr = len(cp) - 1
        if self._finally:
            cp += (self._finally,)
            finally_addr = len(cp) - 1
        cp.append(NOP)
        escape_addr = len(cp) - 1

        cp[0] = TryNode(1, catch_chain, finally_addr, then_addr, escape_addr)
        return NodeCompose(*cp)


def Try(node: Node) -> TryClause:
    """Try-Catch clause

    Args:
        node (Node): Node

    Returns:
        TryClause: Try clause

    Example:
        ```python
        Try(...).CATCH(exc,...).THEN(...).FINALLY(...)
        ```
    """
    return TryClause(node)
