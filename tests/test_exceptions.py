from amrita_sense.exceptions import (
    BreakLoop,
    DependsException,
    DependsInjectFailed,
    DependsResolveFailed,
    InterruptNotice,
    NullPointerException,
)


class TestExceptions:
    """Test cases for AmritaSense exception hierarchy."""

    def test_interrupt_notice_inheritance(self):
        """Test that InterruptNotice inherits from BaseException."""
        exc = InterruptNotice("test message")
        assert isinstance(exc, BaseException)
        assert not isinstance(exc, Exception)
        assert str(exc) == "InterruptNotice test message"

    def test_interrupt_notice_no_message(self):
        """Test InterruptNotice with no message."""
        exc = InterruptNotice()
        assert str(exc) == "InterruptNotice "

    def test_null_pointer_exception(self):
        """Test NullPointerException basic functionality."""
        exc = NullPointerException()
        assert isinstance(exc, Exception)

    def test_break_loop_exception(self):
        """Test BreakLoop exception."""
        exc = BreakLoop()
        assert isinstance(exc, Exception)

    def test_depends_exception_hierarchy(self):
        """Test DependsException inheritance hierarchy."""
        base_exc = DependsException()
        resolve_exc = DependsResolveFailed()
        inject_exc = DependsInjectFailed()

        # All should inherit from their respective bases
        assert isinstance(resolve_exc, DependsResolveFailed)
        assert isinstance(inject_exc, DependsInjectFailed)
        assert isinstance(base_exc, DependsException)

        # DependsException should inherit from Exception
        assert isinstance(base_exc, Exception)
