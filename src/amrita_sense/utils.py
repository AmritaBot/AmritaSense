from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Generic, TypeVar

T = TypeVar("T")


class TimeInsighter:
    """Context manager for measuring execution time of code blocks.

    This class provides both synchronous and asynchronous context manager
    interfaces to measure the time taken for code execution. It records
    start time, end time, and calculates the duration difference.

    Attributes:
        t_beg: Start time of the measured operation.
        t_end: End time of the measured operation.
        t_diff: Time difference (duration) between start and end times.
    """

    t_beg: datetime
    t_end: datetime
    t_diff: timedelta

    def __enter__(self):
        """Enter the runtime measurement context.

        Records the current time as the start time for measurement.

        Returns:
            The TimeInsighter instance itself for method chaining.
        """
        self.t_beg = datetime.now()
        return self

    def __exit__(self, exc_type, exc, tb):
        """Exit the runtime measurement context.

        Records the current time as the end time and calculates the duration.

        Args:
            exc_type: Exception type if an exception occurred, None otherwise.
            exc: Exception instance if an exception occurred, None otherwise.
            tb: Traceback if an exception occurred, None otherwise.
        """
        self.t_end = datetime.now()
        self.t_diff = self.t_end - self.t_beg

    async def __aenter__(self):
        """Enter the async runtime measurement context.

        Provides asynchronous support by delegating to the synchronous __enter__.

        Returns:
            The TimeInsighter instance itself for method chaining.
        """
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb):
        """Exit the async runtime measurement context.

        Provides asynchronous support by delegating to the synchronous __exit__.

        Args:
            exc_type: Exception type if an exception occurred, None otherwise.
            exc: Exception instance if an exception occurred, None otherwise.
            tb: Traceback if an exception occurred, None otherwise.
        """
        return self.__exit__(exc_type, exc, tb)


class Ref(Generic[T]):
    value: T

    def __init__(self, value: T) -> None:
        self.value = value


def search_exceptions(
    seq: Sequence[BaseException | list | None],
) -> list[BaseException]:
    sequ: list[BaseException] = []
    for exc in seq:
        if isinstance(exc, BaseException):
            sequ.append(exc)
        elif isinstance(exc, list):
            sequ.extend(search_exceptions(exc))
    return sequ
