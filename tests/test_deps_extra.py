import pytest

from amrita_sense.runtime.deps import ADDR, FAR_OFFSET, NEAR_OFFSET, POINTER_DEPENDS
from amrita_sense.types import PointerVector


class _FakePointer:
    def __init__(self, pointer, alias_map):
        self._pointer = PointerVector(pointer)
        self._alias_map = alias_map

    def find_addr_alias(self, name):
        return self._alias_map[name]


def test_pointer_depends_returns_same():
    pc = object()
    assert POINTER_DEPENDS(pc) is pc


def test_addr_returns_pointervector():
    pc = _FakePointer([1, 2], {"t": [1, 2]})
    addr = ADDR("t")(pc)
    assert isinstance(addr, PointerVector)
    assert addr == PointerVector([1, 2])


def test_far_offset_computation():
    pc = _FakePointer([3, 4], {"t": [1, 1]})
    res = FAR_OFFSET("t")(pc)
    assert isinstance(res, PointerVector)
    assert res == PointerVector([2, 3])


def test_near_offset_same_level():
    pc = _FakePointer([1, 5], {"t": [1, 2]})
    # When the target alias is at the same nesting level, the near offset
    # should return the last dimension difference without raising.
    assert NEAR_OFFSET("t")(pc) == 3


def test_near_offset_different_level_raises():
    pc = _FakePointer([2, 5], {"t": [1, 2, 0]})
    # A far offset in the higher dimensions is considered invalid for NEAR_OFFSET.
    with pytest.raises(RuntimeError):
        NEAR_OFFSET("t")(pc)
