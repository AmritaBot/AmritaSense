"""Protocol-based dependency markers and runtime dependency collection."""

import pytest

from amrita_sense.hook.fun_typing import (
    DEPENDENCY_MARKER,
    collect_runtime_dependencies,
    is_dependency_marker,
)
from amrita_sense.hook.matcher import DependsFactory


def provider() -> int:
    return 1


class Wrapped:
    """Forwards the marker and the resolution interface; not a DependsFactory."""

    __amrita_sense_dependency__ = True

    def __init__(self, inner: DependsFactory) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class FakeMarker:
    """Only the marker, no resolution interface; rejected during collection."""

    __amrita_sense_dependency__ = True


class TestIsDependencyMarker:
    def test_depends_factory(self):
        assert is_dependency_marker(DependsFactory(provider)) is True

    def test_wrapper_forwarding_marker(self):
        assert is_dependency_marker(Wrapped(DependsFactory(provider))) is True

    def test_plain_values(self):
        for value in (1, "x", None, provider, [1, 2], {"k": "v"}):
            assert is_dependency_marker(value) is False

    def test_marker_constant_name(self):
        assert DEPENDENCY_MARKER == "__amrita_sense_dependency__"


class TestCollectRuntimeDependencies:
    def test_splits_positional_and_keyword(self):
        dep_a = DependsFactory(provider)
        dep_b = DependsFactory(provider)
        runtime_args, runtime_kwargs = collect_runtime_dependencies(
            (dep_a, "plain"), {"b": dep_b, "c": 3}
        )
        assert runtime_args == {0: dep_a}
        assert runtime_kwargs == {"b": dep_b}

    def test_empty(self):
        assert collect_runtime_dependencies((), {}) == ({}, {})

    def test_no_dependency_at_all(self):
        assert collect_runtime_dependencies((1, "x"), {"k": 2}) == ({}, {})

    def test_rejects_marker_without_interface(self):
        with pytest.raises(TypeError, match="is not a usable dependency"):
            collect_runtime_dependencies((FakeMarker(),), {})
