from types import TracebackType

import pytest

from amrita_sense import NodeCompose, WorkflowInterpreter
from amrita_sense.exceptions import IllegalState
from amrita_sense.instructions.try_catch import Try, TryNode
from amrita_sense.node.wrapper import Node as NodeDecorator


def _make_node(ret):
    @NodeDecorator()
    def fn():
        return ret

    return fn


def test_try_requires_catch_or_finally():
    """TryClause without catch or finally should raise on extract."""
    node = _make_node(1)
    tc = Try(node)
    with pytest.raises(IllegalState):
        tc.extract()


def test_try_full_chain_extract():
    """Try with catch/then/finally should produce a NodeCompose with TryNode."""
    do_node = _make_node("do")
    catch_node = _make_node("catch")
    then_node = _make_node("then")
    fin_node = _make_node("fin")

    tc = Try(do_node).CATCH(Exception, catch_node).THEN(then_node).FINALLY(fin_node)
    extracted = tc.extract()

    # First element should be a TryNode instance
    assert isinstance(extracted._graph[0], TryNode)  # type: ignore[reportAttributeAccessIssue]
    # Ensure the composed graph contains the provided nodes
    assert any(n is catch_node for n in extracted._graph)  # type: ignore[reportAttributeAccessIssue]
    assert any(n is then_node for n in extracted._graph)  # type: ignore[reportAttributeAccessIssue]
    assert any(n is fin_node for n in extracted._graph)  # type: ignore[reportAttributeAccessIssue]


class TestCatchMatching:
    """`CATCH` is type-matched; an unclaimed exception must keep propagating."""

    @pytest.mark.asyncio
    async def test_unmatched_exception_propagates(self):
        log: list[str] = []

        @NodeDecorator()
        def raises_key_error() -> None:
            log.append("body")
            raise KeyError("boom")

        @NodeDecorator()
        def handles_value_error() -> None:
            log.append("handled")

        comp = NodeCompose(Try(raises_key_error).CATCH(ValueError, handles_value_error))
        with pytest.raises(KeyError, match="boom"):
            await WorkflowInterpreter(comp.render()).run()
        assert log == ["body"]

    @pytest.mark.asyncio
    async def test_only_the_matching_handler_runs(self):
        log: list[str] = []

        @NodeDecorator()
        def raises_key_error() -> None:
            raise KeyError("boom")

        @NodeDecorator()
        def handles_value_error() -> None:
            log.append("value")

        @NodeDecorator()
        def handles_key_error() -> None:
            log.append("key")

        comp = NodeCompose(
            Try(raises_key_error)
            .CATCH(ValueError, handles_value_error)
            .CATCH(KeyError, handles_key_error)
        )
        await WorkflowInterpreter(comp.render()).run()
        assert log == ["key"]

    @pytest.mark.asyncio
    async def test_handler_receives_the_exception(self):
        seen: list[str] = []

        @NodeDecorator()
        def raises_value_error() -> None:
            raise ValueError("boom")

        @NodeDecorator()
        def handle(
            exc_type: type[BaseException],
            exc_val: BaseException,
            exc_tb: TracebackType,
        ) -> None:
            seen.append(f"{exc_type.__name__}:{exc_val}:{exc_tb is not None}")

        comp = NodeCompose(Try(raises_value_error).CATCH(ValueError, handle))
        await WorkflowInterpreter(comp.render()).run()
        assert seen == ["ValueError:boom:True"]
