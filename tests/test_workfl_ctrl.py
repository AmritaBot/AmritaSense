import pytest

from amrita_sense.exceptions import InterruptNotice
from amrita_sense.instructions.workfl_ctrl import INTERRUPT, NOP


class TestWorkflCtrlNodes:
    """Unit tests for workflow control nodes.

    These tests ensure the `NOP` and `INTERRUPT` node constants expose the
    expected attributes and runtime behavior. Tests use the Node wrapper API
    rather than assuming an `extract()` method exists.
    """

    def test_nop_is_node_and_callable(self):
        """`NOP` should be a node-like object and calling its underlying
        function returns None.
        """
        # NOP is a Node instance produced by the `Node` decorator
        assert hasattr(NOP, "func")
        assert hasattr(NOP, "address_able")

        # Underlying function should return None when executed.
        result = NOP()
        assert result is None

    def test_interrupt_raises_interrupt_notice(self):
        """Calling INTERRUPT should raise InterruptNotice immediately."""
        assert hasattr(INTERRUPT, "func")

        with pytest.raises(InterruptNotice):
            INTERRUPT()
