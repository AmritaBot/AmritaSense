from __future__ import annotations

import builtins
import inspect
import typing
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as Field
from types import FrameType
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypedDict, TypeGuard, cast

from amrita_sense.exceptions import DependsDeclarationError

if TYPE_CHECKING:
    from .matcher import DependsFactory, Matcher


class _Empty:
    pass


EMPTY = _Empty()  # Empty marker


#: Protocol marker for dependency declarations; any object setting it to
#: ``True`` is treated as a dependency by DI.
DEPENDENCY_MARKER = "__amrita_sense_dependency__"


def is_dependency_marker(value: object) -> bool:
    """判断一个值是不是依赖声明。

    先看协议位，再回退到类型：包装器、代理或其它模块的等价标记，只要
    转发 ``__amrita_sense_dependency__ = True`` 就能被识别，不必恰好是
    ``DependsFactory`` 这一个类。类型回退保留给未声明协议位的老实现。
    """
    if getattr(value, DEPENDENCY_MARKER, False) is True:
        return True
    factory_cls = globals().get("DependsFactory")
    return isinstance(value, factory_cls) if factory_cls is not None else False


def is_depends_factory(value: object) -> TypeGuard["DependsFactory"]:
    """严格版判定：只认 DependsFactory 本身或其子类。

    声明期（``sign_func``）要把值写进 ``factory_map`` 并参与后续解析，
    这里必须保证类型契约，不能靠协议位把任意对象放进来；运行时参数才
    用 ``is_dependency_marker`` 的宽口径。
    """
    factory_cls = globals().get("DependsFactory")
    return factory_cls is not None and isinstance(value, factory_cls)


def _require_dependency_interface(value: Any) -> Any:
    """协议位命中但接口不全时立即报错，而不是等解析期才炸在属性访问上。"""
    missing = [
        name
        for name in ("cacheable", "generator_kind", "make_context_manager")
        if not hasattr(value, name)
    ]
    if missing:
        raise TypeError(
            f"Object marked with {DEPENDENCY_MARKER} is not a usable dependency: "
            f"missing {', '.join(missing)}"
        )
    return value


def collect_runtime_dependencies(
    args: Sequence[Any], kwargs: Mapping[str, Any]
) -> tuple[dict[int, Any], dict[str, Any]]:
    """一次扫描分出按位置与按关键字的运行时依赖。

    调用方原来先 ``any()`` 探一遍、再用两个推导式各扫一遍，同一批参数要
    过三遍；这里合成一次，同时让所有调用点共用同一套判定。
    """
    runtime_args = {
        i: _require_dependency_interface(v)
        for i, v in enumerate(args)
        if is_dependency_marker(v)
    }
    runtime_kwargs = {
        k: _require_dependency_interface(v)
        for k, v in kwargs.items()
        if is_dependency_marker(v)
    }
    return runtime_args, runtime_kwargs



class ParamDescriptor(TypedDict):
    type_hint: type | _Empty  # Type hint for the parameter, if available
    kind: Literal["required", "optional", "factory"]  # Parameter status marker
    default: (
        Any | _Empty
    )  # only when kind is "optional", this will have the default value; otherwise, it will be EMPTY


class DependencyMeta(TypedDict):
    params: dict[str, ParamDescriptor]  # arg name -> ParamDescriptor
    factory_map: dict[str, DependsFactory]  # Arg name -> DependsFactory


@dataclass
class FunctionData:
    function: Callable[..., Awaitable[Any]] = Field()
    signature: DependencyMeta = Field()
    frame: FrameType = Field()
    priority: int = Field()
    matcher: Matcher = Field()


def _func_name(func: Callable[..., Any]) -> str:
    return getattr(func, "__qualname__", None) or getattr(func, "__name__", repr(func))


def _is_annotated(anno: Any) -> bool:
    """Whether `anno` is an `Annotated[...]` alias.

    `typing.get_origin(Annotated[int, x])` returns `typing.Annotated` itself
    rather than `int`, so this is the reliable check; looking at `__origin__`
    directly is not.
    """
    return typing.get_origin(anno) is Annotated


def unwrap_annotated(anno: Any) -> Any:
    """Strip the `Annotated` wrapper and keep the underlying type.

    Required because `isinstance(value, Annotated[int, ...])` raises
    `TypeError`, so the wrapper has to be gone before type-based matching.
    `typing` flattens nested `Annotated` itself, so one unwrap is enough.
    """
    if _is_annotated(anno):
        return typing.get_args(anno)[0]
    return anno


def _extract_depends(anno: Any) -> DependsFactory | None:
    """Pull a `Depends(...)` marker out of an `Annotated` annotation.

    Follows FastAPI's `analyze_param`: when several markers are present the
    last one wins.
    """
    if not _is_annotated(anno):
        return None
    for meta in reversed(typing.get_args(anno)[1:]):
        if is_dependency_marker(meta):
            return cast(DependsFactory, meta)
    return None


def type_matches(value: Any, hint: Any) -> bool:
    """`isinstance` that tolerates annotations `isinstance` rejects.

    `isinstance([], list[int])` and `isinstance(1, Any)` raise `TypeError`.
    Subscripted generics fall back to their origin, so `list[int]` behaves
    like `list`; anything still unusable simply does not match, which
    surfaces as an ordinary resolution failure instead of a crash.
    """
    if hint is EMPTY:
        return False
    try:
        return isinstance(value, hint)
    except TypeError:
        origin = typing.get_origin(hint)
        if origin is None:
            return False
        try:
            return isinstance(value, origin)
        except TypeError:
            return False


def _resolve_annotations(func: Callable[..., Any]) -> dict[str, Any]:
    """Return `{parameter_name: annotation}` with PEP 563 strings evaluated.

    Fast path: when no annotation is a string (`from __future__ import
    annotations` is not in effect for this function) the raw
    `__annotations__` mapping is returned as-is, skipping a full
    `get_type_hints` evaluation.

    Slow path: `typing.get_type_hints(..., include_extras=True)` — the
    `include_extras` flag matters, because without it `Annotated` metadata
    is stripped.  If that raises, every annotation is evaluated on its own
    so a single unresolvable name cannot blank out the other parameters;
    ones that still fail become `EMPTY` and surface as `MISSED_ANNOTATION`
    at resolution time.
    """
    raw: dict[str, Any] = dict(getattr(func, "__annotations__", None) or {})
    if not any(isinstance(v, str) for v in raw.values()):
        return raw
    try:
        return typing.get_type_hints(func, include_extras=True)
    except Exception:
        globalns = getattr(func, "__globals__", {})
        localns = {**vars(builtins), **globalns}
        resolved: dict[str, Any] = {}
        for name, value in raw.items():
            if not isinstance(value, str):
                resolved[name] = value
                continue
            try:
                resolved[name] = eval(value, globalns, localns)
            except Exception:
                resolved[name] = EMPTY
        return resolved


def sign_func(func: Callable[..., Any]):
    signature = inspect.signature(func)
    params = signature.parameters
    annotations = _resolve_annotations(func)
    types: dict[str, ParamDescriptor] = {}
    factories: dict[str, DependsFactory] = {}
    for name, prm in params.items():
        kind: Literal["required", "optional", "factory"] = "required"
        default = prm.default if prm.default != inspect.Parameter.empty else EMPTY
        anno = annotations.get(name, EMPTY)
        if anno is inspect.Parameter.empty:
            anno = EMPTY
        anno = unwrap_annotated(anno)
        declared = _extract_depends(annotations.get(name, EMPTY))
        if is_depends_factory(default):
            if declared is not None:
                raise DependsDeclarationError(
                    f"Parameter {name!r} of {_func_name(func)} declares `Depends` "
                    "in both its annotation and its default value; pick one."
                )
            kind = "factory"
            factories[name] = default
            default = None
        elif declared is not None:
            kind = "factory"
            factories[name] = declared
            default = None
        elif default is not EMPTY:
            kind = "optional"

        types[name] = ParamDescriptor(type_hint=anno, kind=kind, default=default)
    return DependencyMeta(params=types, factory_map=factories)


__all__ = [
    "DependencyMeta",
    "FunctionData",
    "ParamDescriptor",
    "sign_func",
    "type_matches",
    "unwrap_annotated",
]
