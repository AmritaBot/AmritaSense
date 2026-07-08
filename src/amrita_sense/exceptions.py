class InterruptNotice(BaseException):
    """Exception raised to signal an interrupt in workflow execution.

    This exception is used to gracefully terminate workflow execution when an
    external interrupt is requested. It inherits from BaseException to avoid
    being caught by generic Exception handlers.

    Attributes:
        message: Optional message describing the interrupt reason.
    """

    def __init__(self, message: str | None = None):
        """Initialize InterruptNotice with an optional message.

        Args:
            message: Optional description of the interrupt reason.
        """
        self.message: str | None = message

    def __str__(self) -> str:
        return f"InterruptNotice {self.message or ''}"


class InterruptKeepContext(InterruptNotice):
    """Exception raised to signal an interrupt in workflow execution.

    This exception is used to gracefully terminate workflow execution, but keep the state of the workflow.

    Attributes:
        message: Optional message describing the interrupt reason.
    """


class NullPointerException(Exception):
    """Exception raised when a node cannot be found by its pointer address.

    This exception occurs during workflow execution when attempting to access
    a node at an invalid or non-existent address in the workflow graph.
    """


class BreakLoop(Exception):
    """Exception raised to break out of loop constructs.

    This exception is used internally by WHILE and DO-WHILE loop constructs
    to implement the 'break' functionality. When raised within a loop body,
    it causes the loop to terminate immediately and continue execution after
    the loop.
    """


class DependsException(Exception):
    """Base exception for dependency injection failures.

    This is the base class for all dependency injection related exceptions
    in the workflow engine. It is raised when dependency resolution or
    injection fails during node execution.
    """


class DependsResolveFailed(Exception):
    """Exception raised when dependency resolution fails.

    This exception occurs when the dependency injection system cannot resolve
    the required dependencies for a node function, typically due to missing
    or incompatible dependency providers.
    """


class DependsInjectFailed(Exception):
    """Exception raised when dependency injection fails.

    This exception occurs when the dependency injection system successfully
    resolves dependencies but fails to inject them into the target function,
    usually due to parameter mismatch or runtime errors during injection.
    """


class IllegalState(Exception):
    """Exception raised when an illegal state is encountered.

    This exception occurs when an operation is attempted in an invalid or
    illegal state, usually due to a missing or invalid dependency or resource.
    """
