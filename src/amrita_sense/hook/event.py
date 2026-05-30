from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Generic, TypeVar

from typing_extensions import Self

stringSub_T = TypeVar("stringSub_T", bound=str, covariant=True)


@dataclass
class BaseEvent(ABC, Generic[stringSub_T]):
    """All events must inherit from this class"""

    @abstractmethod
    def get_event_type(self) -> stringSub_T:
        raise NotImplementedError  # pragma: no cover

    @property
    @abstractmethod
    def event_type(self) -> stringSub_T: ...


@dataclass
class ConstructableEvent(BaseEvent):
    @classmethod
    @abstractmethod
    def constructor(cls, *args, **kwargs) -> Self | Awaitable[Self]: ...
