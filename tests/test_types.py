import pytest

from amrita_sense.types import PointerVector, Stack


class TestStack:
    """Test cases for the Stack class."""

    def test_stack_initialization(self):
        """Test that stack initializes correctly with default capacity."""
        stack = Stack()
        assert bool(stack) is False  # Empty stack is falsy
        assert stack.ovf == 1024

    def test_stack_custom_capacity(self):
        """Test that stack respects custom capacity setting."""
        stack = Stack(ovf=10)
        assert stack.ovf == 10

    def test_stack_push_pop(self):
        """Test basic push and pop operations."""
        stack = Stack()
        stack.push(1)
        stack.push(2)
        stack.push(3)

        assert bool(stack) is True  # Non-empty stack is truthy
        assert stack.pop() == 3
        assert stack.pop() == 2
        assert stack.pop() == 1
        assert bool(stack) is False

    def test_stack_pop_empty(self):
        """Test that pop on empty stack raises IndexError."""
        stack = Stack()
        with pytest.raises(IndexError, match="Stack is empty"):
            stack.pop()

    def test_stack_overflow(self):
        """Test that stack overflow raises OverflowError."""
        stack = Stack(ovf=3)
        stack.push(1)
        stack.push(2)
        stack.push(3)

        with pytest.raises(OverflowError, match="Stack overflow"):
            stack.push(4)

    def test_stack_clear(self):
        """Test that clear operation works correctly."""
        stack = Stack()
        stack.push(1)
        stack.push(2)
        stack.clear()
        assert bool(stack) is False

    def test_stack_len(self):
        """Test stack length property."""
        stack = Stack()
        assert len(stack) == 0
        stack.push(1)
        assert len(stack) == 1
        stack.push(2)
        assert len(stack) == 2
        stack.pop()
        assert len(stack) == 1


class TestPointerVector:
    """Test cases for the PointerVector class."""

    def test_pointer_vector_initialization(self):
        """Test that PointerVector initializes correctly."""
        pv = PointerVector([0, 1, 2])
        assert pv.base_addr == [0, 1, 2]

        # Test default initialization
        pv_default = PointerVector()
        assert pv_default.base_addr == [0]

    def test_pointer_vector_offset(self):
        """Test PointerVector offset method."""
        pv = PointerVector([1, 2, 3])
        result = pv.offset(2)
        assert result is pv  # Method chaining returns self
        assert pv.base_addr == [1, 2, 5]  # Last element + 2

    def test_pointer_vector_near_to(self):
        """Test PointerVector near_to method."""
        pv = PointerVector([1, 2, 3])
        result = pv.near_to(10)
        assert result is pv
        assert pv.base_addr == [1, 2, 10]  # Last element set to 10

    def test_pointer_vector_copy(self):
        """Test PointerVector copy method."""
        pv = PointerVector([1, 2, 3])
        copied = pv.copy()
        assert copied.base_addr == [1, 2, 3]
        assert copied is not pv  # Should be a different object
        # Modify original should not affect copy
        pv.base_addr[0] = 99
        assert copied.base_addr == [1, 2, 3]
