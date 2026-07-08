from dataclasses import dataclass, field
from typing import Any

from amrita_sense.types import PointerVector, Stack


@dataclass
class IntpreterContext:
    ptr: PointerVector
    exception_ignored: tuple[
        type[BaseException], ...
    ]  # A snapshot of the exception ignored
    s_args: tuple | None = field(default=None)
    s_kwargs: dict[str, Any] | None = field(default=None)
    extra: dict[str, Any] = field(default_factory=dict)
    stack: Stack[PointerVector] | None = field(default=None)
    exception: Exception | None = field(default=None)
