"""Switches that control low-level framework behaviour.

Flags in this module alter how the core engine operates — they are **not**
meant for runtime tuning during development.  Toggling them in production
may lead to undefined behaviour, subtle data corruption, or silent failures.

.. warning::

    These flags are internal implementation details and are **not** covered
    by Semantic Versioning (SemVer) compatibility guarantees.  Review every
    flag's semantics carefully before flipping it.  In production environments
    they should be left at their defaults.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


@dataclass
class _Flags:
    FORCE_NOT_WRAP_TO_ASYNC: bool = field(default=False)
    """Disable `wrap_to_async` in node behavior, force all synchronous nodes to be synchronous"""
    DISABLE_EXC_IGNORED: bool = field(default=False)
    """Disable `exc_ignored` in built-in instructions and matcher system"""
    ALLOW_CALL_NODECOMPOSE: bool = field(default=False)
    """Ignore the case that `NodeCompose` is called directly by `_call()`"""
    NO_DEPENDENCY_META_CACHE: bool = field(default=False)
    """Ignore the case that `DependencyMeta` is cached, resolve it in each call"""
    NO_SHARED_MIDDLEWARE: bool = field(default=False)
    """Ignore the case that `middleware` is shared between `WorkflowInterpreter`, set it to None."""
    _modified_flags: set = field(default_factory=set)

    if not TYPE_CHECKING:

        def __setattr__(self, key: str, value: bool) -> None:

            if not key.isupper():
                super().__setattr__(key, value)
                return

            if hasattr(self, "_modified_flags"):
                if key in self._modified_flags:
                    raise RuntimeError(f"{key} is modified")
                super().__setattr__(key, value)
                self._modified_flags.add(key)
            else:
                super().__setattr__(key, value)


__flags__ = _Flags()

__all__: list[str] = ["__flags__"]
