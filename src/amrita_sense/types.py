from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Generic, TypeVar

from typing_extensions import Self

T = TypeVar("T")


class Stack(Generic[T]):
    ovf: int
    _lk: threading.Lock
    stack: list[T]

    def __init__(self, ovf: int = 1024):
        self.stack = []
        self.ovf = ovf
        self._lk = threading.Lock()

    def __len__(self) -> int:
        return len(self.stack)

    def __repr__(self) -> str:
        return repr(self.stack)

    def __str__(self) -> str:
        return str(self.stack)

    def __bool__(self) -> bool:
        return bool(self.stack)

    def push(self, item):
        with self._lk:
            if len(self.stack) >= self.ovf:
                raise OverflowError("Stack overflow")
            self.stack.append(item)

    def pop(self) -> T:
        with self._lk:
            if not self.stack:
                raise IndexError("Stack is empty")
            return self.stack.pop()

    def clear(self):
        """Unsafe!! This action will clear the stack."""
        with self._lk:
            self.stack.clear()

    def resize(self, size: int):
        self.ovf = size


class PointerVector:
    base_addr: list[int]
    _lock: threading.Lock

    def __init__(self, base: list[int] | None = None):
        self.base_addr = base or [0]
        self._lock = threading.Lock()

    def offset(self, offset: int) -> Self:
        with self._lock:
            ptr: list[int] = self.base_addr
            ptr[-1] += offset
            return self

    def offset_far(self, offset: list[int]) -> Self:
        with self._lock:
            offset = offset.copy()
            ptr: list[int] = self.base_addr
            len_off: int = len(offset)
            len_ptr: int = len(ptr)
            len_diff: int = len_ptr - len_off
            if len_diff < 0:
                ptr.extend([0] * -len_diff)
            elif len_diff > 0:
                offset.extend([0] * len_diff)
            self.base_addr = [i[0] + i[1] for i in zip(ptr, offset)]
            return self

    def near_to(self, short_offset: int) -> Self:
        with self._lock:
            ptr: list[int] = self.base_addr
            ptr[-1] = short_offset
            return self

    def far_to(self, addr: list[int]) -> Self:
        with self._lock:
            self.base_addr.clear()
            self.base_addr.extend(addr)
            return self

    def pop(self) -> int:
        with self._lock:
            return self.base_addr.pop()

    def append(self, node_ip: int) -> None:
        with self._lock:
            self.base_addr.append(node_ip)

    def clear(self) -> None:
        with self._lock:
            self.base_addr.clear()

    def copy(self) -> PointerVector:
        return PointerVector(self.base_addr.copy())

    def __add__(self, other: PointerVector) -> PointerVector:
        return self.copy().offset_far(other.base_addr)

    def __sub__(self, other: PointerVector) -> PointerVector:
        return self.copy().offset_far([-i for i in other.base_addr])

    def __bool__(self) -> bool:
        return bool(self.base_addr)

    def __eq__(self, value: object) -> bool:
        with self._lock:
            if not isinstance(value, type(self)):
                return False
            return self.base_addr == value.base_addr

    def __hash__(self) -> int:
        return hash(tuple(self.base_addr))

    def __repr__(self) -> str:
        return f"PointerVector({self.base_addr})"

    def __getitem__(self, index: int) -> int:
        with self._lock:
            return self.base_addr[index]

    def __setitem__(self, index: int, value: int) -> None:
        with self._lock:
            self.base_addr[index] = value

    def __iter__(self) -> Iterator[int]:
        yield from self.base_addr

    def __delitem__(self, key):
        raise ValueError("Cannot delete items from PointerVector")
