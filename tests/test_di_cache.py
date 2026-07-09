"""Tests for v0.4.2 DI cache system: DICache, _fingerprint_args, conflict flags, etc.

Every test runs under a fresh ``_Flags()`` instance patched into
``amrita_sense._unsafe`` and ``amrita_sense.runtime.workflow``,
so no global flag state leaks between tests or downstream suites.
"""

from unittest.mock import patch

import pytest

import amrita_sense._unsafe
import amrita_sense.runtime.workflow
from amrita_sense._unsafe import _Flags
from amrita_sense.exceptions import DependsResolveFailed
from amrita_sense.hook.matcher import Depends
from amrita_sense.node.core import BaseNode, NodeCompose
from amrita_sense.node.wrapper import Node as NodeDecorator
from amrita_sense.runtime.deps import POINTER_DEPENDS
from amrita_sense.runtime.types import InterpreterContext
from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import DICache, PointerVector
from amrita_sense.utils import _fingerprint_args

FLAGS = amrita_sense._unsafe  # module ref; __flags__ looked up at runtime


@pytest.fixture(autouse=True)
def _isolate_flags():
    """Run every test with a pristine _Flags() instance."""
    fresh = _Flags()
    with (
        patch.object(amrita_sense._unsafe, "__flags__", fresh),
        patch.object(amrita_sense.runtime.workflow, "__flags__", fresh),
    ):
        yield


#  _fingerprint_args


class TestFingerprintArgs:
    def test_same_types_same_hash(self):
        assert _fingerprint_args((42, "hello"), {}) == _fingerprint_args(
            (99, "world"), {}
        )

    def test_different_order_same_hash(self):
        assert _fingerprint_args((1, "a"), {"x": 1, "y": 2}) == _fingerprint_args(
            (1, "a"), {"y": 3, "x": 4}
        )

    def test_different_types_different_hash(self):
        assert _fingerprint_args((1,), {}) != _fingerprint_args(("1",), {})

    def test_empty_args_returns_hash(self):
        assert isinstance(_fingerprint_args((), {}), int)

    def test_args_changed_different_hash(self):
        assert _fingerprint_args((1, 2), {"a": 1}) != _fingerprint_args((1,), {"a": 1})

    def test_custom_type_name_in_hash(self):
        class MyObj:
            pass

        assert _fingerprint_args((MyObj(),), {}) != _fingerprint_args((object(),), {})


#  DICache dataclass


class TestDICacheType:
    def test_dicache_initialization(self):
        c = DICache(args_hash=12345, hash_trustable=True)
        assert c.args_hash == 12345
        assert c.hash_trustable is True
        assert len(c.payload) == 0

    def test_dicache_payload_store_and_retrieve(self):
        c = DICache(args_hash=42, hash_trustable=True)
        c.payload[1] = {"x": 1}
        c.payload[2] = {"y": 2}
        assert c.payload[1] == {"x": 1}
        assert c.payload[2] == {"y": 2}

    def test_dicache_hash_trustable_default(self):
        assert DICache(args_hash=0, hash_trustable=False).hash_trustable is False

    def test_dicache_payload_is_lru(self):
        c = DICache(args_hash=0, hash_trustable=True)
        for i in range(2048):
            c.payload[i] = {"data": i}
        assert len(c.payload) <= 1024


#  DI cache on WorkflowInterpreter


class TestDICacheInitAndProperties:
    @pytest.mark.asyncio
    async def test_di_cache_initialized_on_construct(self):
        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render(), extra_args=(42,))
        assert isinstance(pc._di_cache, DICache)
        assert pc._di_cache.hash_trustable is True
        assert isinstance(pc._di_cache.args_hash, int)

    def test_args_hash_property(self):
        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render())
        assert isinstance(pc.args_hash, int)
        assert pc.args_hash == pc._di_cache.args_hash

    def test_args_hash_trustable_property(self):
        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render())
        assert pc.args_hash_trustable is True


#  rehash_args / hash_trustable


class TestRehashArgs:
    @pytest.mark.asyncio
    async def test_rehash_args_same_hash_keeps_cache(self):
        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render(), extra_args=(42,))
        pc._di_cache.payload[1] = {"data": "cached"}
        pev = pc.args_hash
        pc.rehash_args()
        assert pc.args_hash == pev
        assert pc.args_hash_trustable is True
        assert pc._di_cache.payload[1] == {"data": "cached"}

    @pytest.mark.asyncio
    async def test_rehash_args_different_hash_clears_cache(self):
        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render(), extra_args=(42,))
        pc._di_cache.payload[1] = {"data": "cached"}
        pev = pc.args_hash
        pc._ava_args = (pc, "different_type")
        assert pc.args_hash_trustable is False
        pc.rehash_args()
        assert pc.args_hash_trustable is True
        assert pc.args_hash != pev
        assert len(pc._di_cache.payload) == 0

    @pytest.mark.asyncio
    async def test_ava_args_setter_marks_hash_untrustable(self):
        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render())
        assert pc.args_hash_trustable is True
        pc._ava_args = (pc, "new_value")
        assert pc.args_hash_trustable is False

    @pytest.mark.asyncio
    async def test_ava_kwargs_setter_marks_hash_untrustable(self):
        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render())
        assert pc.args_hash_trustable is True
        pc._ava_kwargs = {"key": "new_value"}
        assert pc.args_hash_trustable is False


#  _rslv_node


class TestRslvNode:
    @pytest.mark.asyncio
    async def test_rslv_node_resolves_simple_node(self):
        @NodeDecorator()
        def n():
            return "ok"

        pc = WorkflowInterpreter(NodeCompose(n).render())
        pc._pointer = PointerVector([0])
        nd = pc.find_addr([0])
        assert isinstance(nd, BaseNode)
        kw = await pc._rslv_node(nd, pc._ava_args, pc._ava_kwargs)
        assert isinstance(kw, dict)

    @pytest.mark.asyncio
    async def test_rslv_node_raise_depends_resolve_failed(self):
        @NodeDecorator()
        def n(needed: int):
            return needed

        pc = WorkflowInterpreter(NodeCompose(n).render())
        pc._pointer = PointerVector([0])
        nd = pc.find_addr([0])
        assert isinstance(nd, BaseNode)
        with pytest.raises(DependsResolveFailed):
            await pc._rslv_node(nd, pc._ava_args, pc._ava_kwargs)

    @pytest.mark.asyncio
    async def test_rslv_node_with_pointer_depends(self):
        @NodeDecorator()
        def n(pc: WorkflowInterpreter = Depends(POINTER_DEPENDS)):
            return pc.id

        pc = WorkflowInterpreter(NodeCompose(n).render())
        pc._pointer = PointerVector([0])
        nd = pc.find_addr([0])
        assert isinstance(nd, BaseNode)
        kw = await pc._rslv_node(nd, pc._ava_args, pc._ava_kwargs)
        assert kw["pc"] is pc


#  _refresh_di_cache_full


class TestRefreshDICacheFull:
    @pytest.mark.asyncio
    async def test_preload_cache_populates_cache(self):
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_CACHE = True
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_BATCH = 2

        @NodeDecorator()
        def n1():
            return 1

        @NodeDecorator()
        def n2():
            return 2

        pc = WorkflowInterpreter(NodeCompose(n1, n2).render())
        pc._pointer = PointerVector([0])
        assert len(pc._di_cache.payload) == 0
        await pc._refresh_di_cache_full()
        assert len(pc._di_cache.payload) >= 1

    @pytest.mark.asyncio
    async def test_preload_cache_rejects_untrustable_hash(self):
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_CACHE = True

        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render())
        pc._ava_args = (pc, "new")
        with pytest.raises(DependsResolveFailed, match="not trustable"):
            await pc._refresh_di_cache_full()

    @pytest.mark.asyncio
    async def test_preload_cache_with_small_batch(self):
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_CACHE = True
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_BATCH = 1

        @NodeDecorator()
        def n():
            return None

        pc = WorkflowInterpreter(NodeCompose(n, n, n, n, n).render())
        await pc._refresh_di_cache_full()
        assert len(pc._di_cache.payload) >= 1


#  rebase_context invalidation


class TestRebaseContextDI:
    @pytest.mark.asyncio
    async def test_rebase_context_sets_hash_untrustable(self):
        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render())
        assert pc.args_hash_trustable is True
        ctx = InterpreterContext(
            ptr=PointerVector([0]),
            exception_ignored=(),
            s_args=(pc, 99),
            s_kwargs={"k": "v"},
        )
        pc.rebase_context(ctx)
        assert pc.args_hash_trustable is False


#  flag conflict detection


class TestConflictFlags:
    def test_workflow_di_no_cache_conflicts_with_preload(self):
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_CACHE = True
        with pytest.raises(RuntimeError, match="Conflicting flags"):
            FLAGS.__flags__.WORKFLOW_DI_NO_CACHE = True

    def test_preload_cache_conflicts_with_no_dependency_meta_cache(self):
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_CACHE = True
        with pytest.raises(RuntimeError, match="Conflicting flags"):
            FLAGS.__flags__.NO_DEPENDENCY_META_CACHE = True

    def test_writeable_flags_can_be_reassigned(self):
        FLAGS.__flags__.WORKFLOW_DI_NO_CACHE = False
        FLAGS.__flags__.WORKFLOW_DI_NO_CACHE = True
        FLAGS.__flags__.WORKFLOW_DI_NO_CACHE = False
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_BATCH = 5
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_BATCH = 20
        FLAGS.__flags__.WORKFLOW_DI_PRELOAD_BATCH = 10


#  DI cache in _call()


class TestDICacheInCall:
    @pytest.mark.asyncio
    async def test_call_populates_di_cache(self):
        @NodeDecorator()
        def n():
            return 42

        pc = WorkflowInterpreter(NodeCompose(n).render())
        pc._pointer = PointerVector([0])
        assert len(pc._di_cache.payload) == 0
        assert await pc._call() == 42
        assert len(pc._di_cache.payload) >= 1

    @pytest.mark.asyncio
    async def test_call_caches_resolved_kwargs(self):
        @NodeDecorator()
        def n():
            return "x"

        pc = WorkflowInterpreter(NodeCompose(n).render())
        pc._pointer = PointerVector([0])
        await pc._call()
        key = hash((hash(pc._pointer), pc.args_hash))
        cached = pc._di_cache.payload.get(key)
        assert cached is not None
        assert isinstance(cached, dict)

    @pytest.mark.asyncio
    async def test_call_caches_across_multiple_nodes(self):
        @NodeDecorator()
        def n1():
            return 1

        @NodeDecorator()
        def n2():
            return 2

        pc = WorkflowInterpreter(NodeCompose(n1, n2).render())
        pc._pointer = PointerVector([0])
        await pc._call()
        pc._pointer = PointerVector([1])
        await pc._call()
        assert len(pc._di_cache.payload) >= 2

    @pytest.mark.asyncio
    async def test_di_cache_persists_across_runs(self):
        @NodeDecorator()
        def n():
            return "persistent"

        pc = WorkflowInterpreter(NodeCompose(n).render())
        await pc.run()
        assert len(pc._di_cache.payload) >= 1


#  WORKFLOW_DI_NO_CACHE


class TestWorkflowDINoCache:
    @pytest.mark.asyncio
    async def test_no_cache_flag_disables_cache_write(self):
        FLAGS.__flags__.WORKFLOW_DI_NO_CACHE = True

        @NodeDecorator()
        def n():
            return 1

        pc = WorkflowInterpreter(NodeCompose(n).render())
        pc._pointer = PointerVector([0])
        await pc._call()
        assert len(pc._di_cache.payload) == 0
