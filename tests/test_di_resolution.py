"""Regression tests for the DI resolution defects fixed in 1.0.

Each test class maps to one defect:

* `TestOptionalParamsFromSessionKwargs` — the completeness check compared
  `f_kwargs` (which also holds optional params) against `required_params`,
  so any optional parameter satisfied by `session_kwargs` aborted resolution.
* `TestParameterisedGenericAnnotations` — `isinstance(value, list[int])`
  raises `TypeError`, which escaped as a crash instead of a resolution
  failure.
* `TestPep563Annotations` — string annotations were looked up in
  `func.__globals__` only, so builtins such as `int` never resolved.
* `TestAnnotatedDeclarations` — `Annotated` was not unwrapped, so the
  wrapper reached `isinstance` (crash) and `Depends` markers inside it were
  ignored.
"""

from __future__ import annotations

from typing import Annotated, Any, Generic, TypeVar

import pytest

from amrita_sense.exceptions import DependsDeclarationError
from amrita_sense.hook.fun_typing import (
    EMPTY,
    sign_func,
    type_matches,
    unwrap_annotated,
)
from amrita_sense.hook.matcher import Depends, DependsFactory, MatcherFactory

T = TypeVar("T")


# Module-level names, so PEP 563 annotations can resolve them.


class First: ...


class Second(First): ...


class Box(Generic[T]): ...


async def int_provider() -> int:
    return 7


async def first_provider() -> int:
    return 1


async def second_provider() -> int:
    return 2


async def box_provider() -> Box[int]:
    return Box()


def _resolve(func: Any, sargs: tuple = (), skwargs: dict | None = None):
    """Shortcut for `MatcherFactory._resolve_dependencies(sign_func(func), ...)`."""
    return MatcherFactory._resolve_dependencies(
        sign_func(func), sargs, skwargs if skwargs is not None else {}
    )


def _make_func(source: str) -> Any:
    """Build a function from source with PEP 563 active."""
    ns: dict[str, Any] = {}
    exec("from __future__ import annotations\n" + source, ns)
    return ns["target"]


class TestOptionalParamsFromSessionKwargs:
    def test_optional_param_supplied_as_kwarg(self):
        def target(a: int, b: str = "x") -> None: ...

        fail, kw, _ = _resolve(target, (1,), {"b": "hello"})
        assert fail is None
        assert kw == {"a": 1, "b": "hello"}

    def test_every_param_supplied_as_kwarg(self):
        def target(a: int, b: str = "x") -> None: ...

        fail, kw, _ = _resolve(target, (), {"a": 1, "b": "y"})
        assert fail is None
        assert kw == {"a": 1, "b": "y"}

    def test_optional_param_left_to_its_default(self):
        def target(a: int, b: str = "x") -> None: ...

        fail, kw, _ = _resolve(target, (1,), {})
        assert fail is None
        # `b` keeps its default; only injected values are returned.
        assert kw == {"a": 1}

    def test_missing_required_param_still_fails(self):
        def target(a: int, b: str = "x") -> None: ...

        fail, _, _ = _resolve(target, (), {})
        assert fail is not None

    def test_keyword_match_wins_over_type_traversal(self):
        def target(a: int) -> None: ...

        fail, kw, _ = _resolve(target, (7,), {"a": 42})
        assert fail is None
        assert kw == {"a": 42}

    def test_type_traversal_follows_positional_order(self):
        def target(a: First) -> None: ...

        one, two = First(), Second()
        fail, kw, _ = _resolve(target, (one, two), {})
        assert fail is None
        assert kw == {"a": one}


class TestParameterisedGenericAnnotations:
    def test_list_of_int_does_not_crash(self):
        def target(items: list[int]) -> None: ...

        fail, kw, _ = _resolve(target, ([1, 2],), {})
        assert fail is None
        assert kw == {"items": [1, 2]}

    def test_dict_of_str_int_does_not_crash(self):
        def target(mapping: dict[str, int]) -> None: ...

        fail, kw, _ = _resolve(target, ({"a": 1},), {})
        assert fail is None
        assert kw == {"mapping": {"a": 1}}

    def test_subscripted_generic_annotation_reports_failure(self):
        def target(box: Box[int]) -> None: ...

        # A `str` is not a `Box`, so this must be an ordinary resolution failure rather than a `TypeError`.
        fail, _, _ = _resolve(target, ("nope",), {})
        assert fail is not None

    def test_any_annotation_does_not_crash(self):
        def target(value: Any) -> None: ...

        fail, _, _ = _resolve(target, (object(),), {})
        assert fail is not None

    def test_union_annotation_still_matches(self):
        def target(value: int | None) -> None: ...

        fail, kw, _ = _resolve(target, (5,), {})
        assert fail is None
        assert kw == {"value": 5}

    def test_type_matches_helper(self):
        assert type_matches([1], list[int]) is True
        assert type_matches("x", list[int]) is False
        assert type_matches(1, Any) is False
        assert type_matches(1, EMPTY) is False
        assert type_matches(1, int) is True


class TestPep563Annotations:
    def test_builtin_annotations_resolve(self):
        target = _make_func("def target(a: int, b: str = 'x') -> None: ...")

        fail, kw, _ = _resolve(target, (1,), {"b": "hello"})
        assert fail is None
        assert kw == {"a": 1, "b": "hello"}

    def test_collection_annotations_resolve(self):
        target = _make_func("def target(items: list[int]) -> None: ...")

        fail, kw, _ = _resolve(target, ([1],), {})
        assert fail is None
        assert kw == {"items": [1]}

    def test_unresolvable_name_becomes_missed_annotation(self):
        target = _make_func("def target(a: Missing) -> None: ...")

        fail, _, _ = _resolve(target, (1,), {})
        assert fail is not None
        assert fail.name == "MISSED_ANNOTATION"

    def test_one_bad_annotation_does_not_blank_the_others(self):
        target = _make_func("def target(a: int, b: Missing, c: str = 'x') -> None: ...")
        meta = sign_func(target)

        # `a` and `c` still resolve; only `b` degrades to EMPTY.
        assert meta["params"]["a"]["type_hint"] is int
        assert meta["params"]["b"]["type_hint"] is EMPTY
        assert meta["params"]["c"]["type_hint"] is str


class TestAnnotatedDeclarations:
    def test_annotated_wrapper_is_stripped(self):
        assert unwrap_annotated(Annotated[int, "meta"]) is int
        assert unwrap_annotated(int) is int

    def test_annotated_param_uses_underlying_type(self):
        def target(value: Annotated[int, "meta"]) -> None: ...

        fail, kw, _ = _resolve(target, (1,), {})
        assert fail is None
        assert kw == {"value": 1}

    def test_annotated_param_ignores_unrelated_metadata(self):
        def target(value: Annotated[str, "doc", 42]) -> None: ...

        fail, kw, _ = _resolve(target, ("s",), {})
        assert fail is None
        assert kw == {"value": "s"}

    def test_depends_inside_annotated_is_a_factory(self):
        def target(value: Annotated[int, Depends(int_provider)]) -> None: ...

        meta = sign_func(target)
        assert meta["params"]["value"]["kind"] == "factory"
        assert isinstance(meta["factory_map"]["value"], DependsFactory)

    def test_depends_in_annotated_is_not_type_matched(self):
        def target(box: Box[int] = Depends(box_provider)) -> None: ...

        # A factory parameter must never reach `isinstance`; this mirrors the `WorkflowInterpreter[SuspendObjectStream] = Depends(...)` shape used by downstream projects.
        fail, _, dkw = _resolve(target, (), {})
        assert fail is None
        assert "box" in dkw

    def test_last_depends_marker_wins(self):
        def target(
            value: Annotated[int, Depends(first_provider), Depends(second_provider)],
        ) -> None: ...

        meta = sign_func(target)
        assert meta["factory_map"]["value"]._depency_func is second_provider

    def test_depends_in_annotation_and_default_conflicts(self):
        def target(
            value: Annotated[int, Depends(int_provider)] = Depends(int_provider),
        ): ...

        with pytest.raises(DependsDeclarationError) as excinfo:
            sign_func(target)

        # The message must name the offending parameter.
        assert "value" in str(excinfo.value)
