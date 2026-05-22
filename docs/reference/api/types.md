# Type System

AmritaSense uses a small set of custom runtime types to represent workflow addresses and execution stacks. The most important types are `PointerVector` and `Stack`.

## PointerVector

`PointerVector` represents a multi-dimensional address in a workflow graph. It is the interpreter's program counter and supports nested workflows by storing a list of indices for each level of nesting.

Key operations:

- `offset(offset: int)`: Add a relative value to the last dimension.
- `near_to(short_offset: int)`: Replace the last dimension with an absolute value.
- `far_to(addr: list[int])`: Replace the entire address vector.
- `offset_far(offset: list[int])`: Apply a multi-dimensional offset.
- `append(node_ip: int)`: Enter a nested container by appending a new coordinate.
- `pop()`: Exit a nested level.
- `copy()`: Create a deep copy of the pointer vector.

`PointerVector` supports addition and subtraction with other `PointerVector` instances, making it easier to compute target addresses and relative offsets.

## Stack

`Stack` is a thread-safe generic LIFO stack used for return address management and other runtime stacks.

Key operations:

- `push(item)`: Push an item to the stack.
- `pop()`: Pop the top item from the stack.
- `clear()`: Remove all items from the stack.
- `resize(size: int)`: Change the maximum capacity.

The stack is protected by a lock and raises `OverflowError` if capacity is exceeded.
