from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Generic, TypeVar

from typing_extensions import Self

T = TypeVar("T")


class Stack(Generic[T]):
    """Thread-safe generic stack implementation with overflow protection.

    This stack provides thread-safe push and pop operations with configurable
    overflow limits. It is used in the workflow engine to manage return address
    stacks and other LIFO data structures.

    Attributes:
        ovf: Maximum capacity of the stack before overflow occurs.
        _lk: Thread lock for ensuring thread-safe operations.
        stack: Internal list storing the stack elements.
    """

    ovf: int
    _lk: threading.Lock
    stack: list[T]

    def __init__(self, ovf: int = 1024):
        """Initialize a new thread-safe stack with optional overflow limit.

        Args:
            ovf: Maximum number of elements the stack can hold. Defaults to 1024.
        """
        self.stack = []
        self.ovf = ovf
        self._lk = threading.Lock()

    def __len__(self) -> int:
        """Return the current number of elements in the stack.

        Returns:
            The number of elements currently in the stack.
        """
        return len(self.stack)

    def __repr__(self) -> str:
        """Return a string representation of the stack.

        Returns:
            String representation of the internal stack list.
        """
        return repr(self.stack)

    def __str__(self) -> str:
        """Return a human-readable string representation of the stack.

        Returns:
            String representation of the internal stack list.
        """
        return str(self.stack)

    def __bool__(self) -> bool:
        """Return True if the stack contains elements, False otherwise.

        Returns:
            Boolean indicating whether the stack is non-empty.
        """
        return bool(self.stack)

    def push(self, item):
        """Push an item onto the stack.

        Args:
            item: The item to add to the top of the stack.

        Raises:
            OverflowError: If the stack would exceed its maximum capacity.
        """
        with self._lk:
            if len(self.stack) >= self.ovf:
                raise OverflowError("Stack overflow")
            self.stack.append(item)

    def pop(self) -> T:
        """Remove and return the top item from the stack.

        Returns:
            The item that was at the top of the stack.

        Raises:
            IndexError: If the stack is empty.
        """
        with self._lk:
            if not self.stack:
                raise IndexError("Stack is empty")
            return self.stack.pop()

    def clear(self):
        """Remove all items from the stack.

        Warning:
            This operation is unsafe in multi-threaded contexts as it bypasses
            normal stack discipline and may interfere with ongoing operations.
        """
        with self._lk:
            self.stack.clear()

    def resize(self, size: int):
        """Change the maximum capacity of the stack.

        Args:
            size: New maximum capacity for the stack.
        """
        self.ovf = size


class PointerVector:
    """Thread-safe multi-dimensional pointer vector for workflow navigation.

    This class represents a multi-dimensional address vector used to navigate
    through nested workflow structures. It provides various methods for
    arithmetic operations, offset calculations, and address manipulation.

    Attributes:
        base_addr: List of integers representing the current address coordinates.
        _lock: Thread lock for ensuring thread-safe operations.
    """

    base_addr: list[int]
    _lock: threading.Lock

    def __init__(self, base: list[int] | None = None):
        """Initialize a new pointer vector with optional initial address.

        Args:
            base: Initial address coordinates. Defaults to [0] if not provided.
        """
        self.base_addr = base or [0]
        self._lock = threading.Lock()

    def offset(self, offset: int) -> Self:
        """Apply a relative offset to the last dimension of the address.

        Args:
            offset: Integer offset to add to the last coordinate.

        Returns:
            Self reference for method chaining.
        """
        with self._lock:
            ptr: list[int] = self.base_addr
            ptr[-1] += offset
            return self

    def offset_far(self, offset: list[int]) -> Self:
        """Apply a multi-dimensional offset vector to the current address.

        This method performs element-wise addition of the offset vector to the
        current address, handling dimension mismatches by padding with zeros.

        Args:
            offset: Multi-dimensional offset vector to apply.

        Returns:
            Self reference for method chaining.
        """
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
            self.base_addr.clear()
            for a, b in zip(ptr, offset):
                v = a + b
                if v < 0:
                    break
                self.base_addr.append(v)

            return self

    def near_to(self, short_offset: int) -> Self:
        """Set the last dimension of the address to an absolute value.

        Args:
            short_offset: Absolute value to set for the last coordinate.

        Returns:
            Self reference for method chaining.
        """
        with self._lock:
            ptr: list[int] = self.base_addr
            ptr[-1] = short_offset
            return self

    def far_to(self, addr: list[int]) -> Self:
        """Set the entire address to a new absolute address vector.

        Args:
            addr: New absolute address vector to replace the current address.

        Returns:
            Self reference for method chaining.
        """
        with self._lock:
            self.base_addr.clear()
            self.base_addr.extend(addr)
            return self

    def pop(self) -> int:
        """Remove and return the last coordinate from the address.

        Returns:
            The last coordinate that was removed from the address vector.
        """
        with self._lock:
            return self.base_addr.pop()

    def append(self, node_ip: int) -> None:
        """Append a new coordinate to the end of the address vector.

        Args:
            node_ip: Coordinate value to append to the address.
        """
        with self._lock:
            self.base_addr.append(node_ip)

    def clear(self) -> None:
        """Remove all coordinates from the address vector."""
        with self._lock:
            self.base_addr.clear()

    def copy(self) -> PointerVector:
        """Create a deep copy of the current pointer vector.

        Returns:
            A new PointerVector instance with the same address coordinates.
        """
        return PointerVector(self.base_addr.copy())

    def __add__(self, other: PointerVector) -> PointerVector:
        """Add two pointer vectors using offset_far operation.

        Args:
            other: Another PointerVector to add to this one.

        Returns:
            A new PointerVector representing the sum of both vectors.
        """
        return self.copy().offset_far(other.base_addr)

    def __sub__(self, other: PointerVector) -> PointerVector:
        """Subtract one pointer vector from another.

        Args:
            other: Another PointerVector to subtract from this one.

        Returns:
            A new PointerVector representing the difference between vectors.
        """
        return self.copy().offset_far([-i for i in other.base_addr])

    def __bool__(self) -> bool:
        """Return True if the address vector contains coordinates, False otherwise.

        Returns:
            Boolean indicating whether the address vector is non-empty.
        """
        return bool(self.base_addr)

    def __eq__(self, value: object) -> bool:
        """Compare two pointer vectors for equality.

        Args:
            value: Another object to compare with this pointer vector.

        Returns:
            True if both vectors have identical address coordinates, False otherwise.
        """
        with self._lock:
            if not isinstance(value, type(self)):
                return False
            return self.base_addr == value.base_addr

    def __hash__(self) -> int:
        """Return hash value based on the address coordinates.

        Returns:
            Hash value computed from the tuple of address coordinates.
        """
        return hash(tuple(self.base_addr))

    def __repr__(self) -> str:
        """Return a string representation of the pointer vector.

        Returns:
            String representation showing the address coordinates.
        """
        return f"PointerVector({self.base_addr})"

    def __getitem__(self, index: int) -> int:
        """Get the coordinate at the specified index.

        Args:
            index: Index of the coordinate to retrieve.

        Returns:
            The coordinate value at the specified index.
        """
        with self._lock:
            return self.base_addr[index]

    def __setitem__(self, index: int, value: int) -> None:
        """Set the coordinate at the specified index.

        Args:
            index: Index of the coordinate to modify.
            value: New value to set at the specified index.
        """
        with self._lock:
            self.base_addr[index] = value

    def __iter__(self) -> Iterator[int]:
        """Return an iterator over the address coordinates.

        Yields:
            Each coordinate in the address vector sequentially.
        """
        yield from self.base_addr

    def __len__(self) -> int:
        """Return the number of coordinates in the address vector.

        Returns:
            The length of the address coordinate list.
        """
        return len(self.base_addr)

    def __delitem__(self, key):
        """Prevent deletion of individual coordinates from the pointer vector.

        Raises:
            ValueError: Always raised as deletion is not supported.
        """
        raise ValueError("Cannot delete items from PointerVector")
