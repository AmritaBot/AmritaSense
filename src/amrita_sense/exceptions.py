class InterruptNotice(BaseException):
    def __init__(self, message: str | None = None):
        self.message: str | None = message

    def __str__(self) -> str:
        return f"InterruptNotice {self.message or ''}"


class NullPointerException(Exception):
    """Throwed when node is not found by pointer"""


class BreakLoop(Exception):
    """Throwed when break loop (in while or do-while clause)"""


class DependsInjectFailed(Exception):
    """Throwed when DI resolve failed."""
