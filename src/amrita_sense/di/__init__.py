"""Dependency lifecycle primitives.

Public surface of the `amrita_sense.di` package:

* `Scope` — how long a generator dependency's resource stays alive.
* `LifecycleScope` — an exit stack owning the resources of one scope.
* `DependencyCache` / `DependencyStore` — per-scope result registry with
  concurrent-resolution de-duplication.

See `scope.py` and `cache.py` for the upstream designs these are adapted from.
"""

from .cache import CacheState, DependencyCache, DependencyStore
from .scope import LifecycleScope, Scope, lift_sync_context

__all__ = [
    "CacheState",
    "DependencyCache",
    "DependencyStore",
    "LifecycleScope",
    "Scope",
    "lift_sync_context",
]
