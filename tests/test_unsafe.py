"""Tests for _unsafe.py — __flags__ lock-once semantics."""

import pytest

from amrita_sense._unsafe import __flags__


def test_flag_set_once_succeeds():
    assert __flags__.NO_DEPENDENCY_META_CACHE is False
    __flags__.NO_DEPENDENCY_META_CACHE = True
    assert __flags__.NO_DEPENDENCY_META_CACHE is True


def test_flag_set_twice_raises():
    with pytest.raises(RuntimeError, match="NO_DEPENDENCY_META_CACHE is modified"):
        __flags__.NO_DEPENDENCY_META_CACHE = False


def test_non_flag_attr_no_lock():
    # _modified_flags is a real field; lowercase attrs pass the guard
    assert isinstance(__flags__._modified_flags, set)
    # Non-flag attrs can be assigned freely (they don't go through __setattr__ guard)
    setattr(__flags__, "_pvt", 1)
    setattr(__flags__, "_pvt", 2)
    assert getattr(__flags__, "_pvt") == 2


@pytest.mark.asyncio
async def test_disable_exc_ignored():
    from amrita_sense import ALIAS, NOP
    from amrita_sense.node.wrapper import Node
    from amrita_sense.runtime.workflow import WorkflowInterpreter

    __flags__.DISABLE_EXC_IGNORED = True

    @Node()
    async def n() -> None:
        pass

    pc = WorkflowInterpreter((n >> ALIAS(NOP, "done")).render())
    assert pc._exc_ignored == ()
