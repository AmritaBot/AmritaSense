import asyncio
from typing import Any

import pytest

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.exceptions import GraphBuildError, NullPointerException
from amrita_sense.instructions import CALL, GOTO, NOP
from amrita_sense.instructions.alias import ALIAS
from amrita_sense.node import DLLCompose, NodeCompose
from amrita_sense.node.core import BaseNode


@pytest.fixture
def log():
    return []


def make_node(name: str, log: list):
    @Node()
    def node():
        log.append(name)

    return node


class ResolveOnCompile(BaseNode):
    """Node whose `_post_compile` resolves an alias through the host calculator."""

    def __init__(self, alias: str) -> None:
        self._alias = alias
        self._addr: list[int] = []
        self._init(self.__call__, tag=None, wrap_to_async=False, address_able=True)

    def __call__(self, *args: Any, **kwds: Any) -> Any: ...
    def _pre_check(self, pointer: Any) -> None: ...

    def _post_compile(self, compose: Any) -> None:
        self._addr = compose.calc.resolve_alias(self._alias)


def test_dll_initial_render(log):
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(b.as_compose())
    comp = a >> dll >> NOP
    r_comp = comp.render()
    asyncio.run(WorkflowInterpreter(r_comp).run())
    assert log == ["A", "B"]


def test_dll_apply_hot_patch(log):
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(b.as_compose())
    r_comp = (a >> dll >> NOP).render()
    asyncio.run(WorkflowInterpreter(r_comp).run())
    assert log == ["A", "B"]

    log.clear()
    # Rebase: recompile a new payload into the same slot.
    dll.apply(b >> a)  # type: ignore[reportArgumentType]
    asyncio.run(WorkflowInterpreter(r_comp).run())
    assert log == ["A", "B", "A"]


def test_dll_repeated_apply_keeps_working(log):
    a, b, c = make_node("A", log), make_node("B", log), make_node("C", log)
    dll = DLLCompose(b.as_compose())
    r_comp = (a >> dll >> NOP).render()
    asyncio.run(WorkflowInterpreter(r_comp).run())
    assert log == ["A", "B"]

    # A second and a third rebase on the same instance must keep working.
    for _ in range(2):
        log.clear()
        dll.apply(c.as_compose())
        asyncio.run(WorkflowInterpreter(r_comp).run())
        assert log == ["A", "C"]

    log.clear()
    dll.apply(b >> c)  # type: ignore[reportArgumentType]
    asyncio.run(WorkflowInterpreter(r_comp).run())
    assert log == ["A", "B", "C"]


def test_dll_constructor_rejects_bare_node(log):
    a = make_node("A", log)
    with pytest.raises(GraphBuildError):
        DLLCompose(a)  # type: ignore[reportArgumentType]


def test_dll_constructor_rejects_rendered_compose(log):
    a = make_node("A", log)
    rendered = (a >> a).render()
    with pytest.raises(GraphBuildError):
        DLLCompose(rendered)


def test_dll_rshift_extends_payload_and_chains(log):
    a, b, c = make_node("A", log), make_node("B", log), make_node("C", log)
    dll = DLLCompose(a.as_compose())
    # __rshift__ mutates the wrapped source compose and returns self.
    assert dll >> b.as_compose() is dll
    dll >> c.as_compose()  # type: ignore
    r_comp = (NOP >> dll >> NOP).render()
    asyncio.run(WorkflowInterpreter(r_comp).run())
    assert log == ["A", "B", "C"]


def test_dll_standalone_render_raises(log):
    a = make_node("A", log)
    dll = DLLCompose(a.as_compose())
    with pytest.raises(GraphBuildError):
        dll.render()


def test_dll_apply_before_render_raises(log):
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(a.as_compose())
    with pytest.raises(GraphBuildError):
        dll.apply(b.as_compose())


def test_dll_get_proxy_before_render_raises(log):
    a = make_node("A", log)
    dll = DLLCompose(a.as_compose())
    with pytest.raises(GraphBuildError):
        dll.get_proxy()


def test_dll_proxy_bound_once_per_instance(log):
    """A DLLCompose instance can only ever be bound to a single proxy."""
    a = make_node("A", log)
    dll = DLLCompose(a.as_compose())
    (NOP >> dll >> NOP).render()  # The first render binds the proxy.
    with pytest.raises(RuntimeError):
        (NOP >> dll >> NOP).render()  # Re-rendering the same instance fails.


def test_dll_same_instance_twice_in_one_tree_raises(log):
    a = make_node("A", log)
    dll = DLLCompose(a.as_compose())
    comp = a >> dll >> dll
    with pytest.raises(RuntimeError):
        comp.render()


def test_dll_proxy_is_the_graph_slot(log):
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(b.as_compose())
    r_comp = (a >> dll >> NOP).render()
    # The proxy is placed at slot [1] and is what get_proxy() returns.
    assert r_comp[1] is dll.get_proxy()


def test_dll_proxy_exposes_no_calculator(log):
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(b.as_compose())
    (a >> dll >> NOP).render()
    with pytest.raises(AttributeError):
        dll.get_proxy().calc


def test_dll_proxy_read_dunders_forward_to_rendered_payload(log):
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(b.as_compose())
    (a >> dll >> NOP).render()
    proxy = dll.get_proxy()

    assert len(proxy) == 1
    assert bool(proxy) is True
    assert list(iter(proxy)) == [b]


def test_dll_proxy_children_swap_after_apply(log):
    a, b, c = make_node("A", log), make_node("B", log), make_node("C", log)
    dll = DLLCompose(b.as_compose())
    (a >> dll >> NOP).render()
    proxy = dll.get_proxy()

    assert proxy[0] is b
    dll.apply(c.as_compose())
    # The same proxy slot now forwards to the new payload.
    assert proxy[0] is c
    assert list(iter(proxy)) == [c]


def test_dll_apply_rejects_non_nodecompose_payload(log):
    a, b, c = make_node("A", log), make_node("B", log), make_node("C", log)
    dll = DLLCompose(b.as_compose())
    (a >> dll >> NOP).render()
    proxy = dll.get_proxy()

    # A bare node is not a source composition: apply() rejects it up front (mirroring __init__) instead of starting a rebuild.
    with pytest.raises(GraphBuildError):
        dll.apply(a)  # type: ignore[reportArgumentType]

    # Rejection happens before any mutation: the proxy still serves the previously applied payload.
    assert proxy[0] is b
    assert list(iter(proxy)) == [b]
    assert len(proxy) == 1
    assert bool(proxy) is True

    # And a subsequent valid rebase keeps working.
    dll.apply(c.as_compose())
    assert proxy[0] is c
    assert list(iter(proxy)) == [c]


def test_dll_empty_payload_renders_but_is_not_addressable(log):
    a = make_node("A", log)
    dll = DLLCompose(NodeCompose())
    r_comp = (a >> dll >> NOP).render()

    # Rendering succeeds and the proxy is empty...
    assert len(dll.get_proxy()) == 0

    # ...but the interpreter cannot find an address inside the empty slot.
    with pytest.raises(NullPointerException):
        asyncio.run(WorkflowInterpreter(r_comp).run())


def test_dll_alias_cleanup_and_reregister(log):
    """Alias symbols of the old payload are removed; the new payload can
    re-register the same names under the same slot prefix."""
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose((ALIAS(b, "dll_main")).as_compose())
    r_comp = (NOP >> dll >> NOP).render()

    # First build: dll_main lives at slot [1, 0].
    assert r_comp.alias2vector_map["dll_main"] == [1, 0]

    # Rebasing to alias-free content cleans up the old symbol.
    dll.apply(a.as_compose())
    assert "dll_main" not in r_comp.alias2vector_map

    # Rebasing back re-registers the symbol at the same slot.
    dll.apply((ALIAS(b, "dll_main")).as_compose())
    assert r_comp.alias2vector_map["dll_main"] == [1, 0]


#  post-compile hook collection: a DLL slot must not disturb the host graph's hook collector, which the host owns and runs once its own build finishes.


def test_dll_slot_keeps_hooks_collected_before_it(log):
    """A node before the slot still gets its `_post_compile` run."""
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(b.as_compose())
    r_comp = (ALIAS(a, "top") >> GOTO("top") >> dll >> NOP).render()
    assert r_comp[1]._node_addr == [0]  # type: ignore[attr-defined]


def test_dll_slot_allows_hook_nodes_after_it(log):
    """A hook-bearing node after the slot must not break the build."""
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(b.as_compose())
    r_comp = (ALIAS(a, "top") >> dll >> GOTO("top")).render()
    assert r_comp[2]._node_addr == [0]  # type: ignore[attr-defined]


def test_dll_internal_hook_can_use_the_host_calculator(log):
    """A payload hook runs once the host calculator exists, so `calc` works."""
    a, b = make_node("A", log), make_node("B", log)
    probe = ResolveOnCompile("sym")
    dll = DLLCompose(NodeCompose(probe))
    (a >> dll >> NOP >> ALIAS(b, "sym")).render()
    assert probe._addr == [3]


def test_dll_internal_hook_sees_aliases_declared_later(log):
    """Payload hooks are deferred, so they can resolve aliases declared after
    the slot — a payload is compiled mid-walk, but hooks run at the end."""
    a, b = make_node("A", log), make_node("B", log)
    probe = ResolveOnCompile("late")
    dll = DLLCompose(NodeCompose(probe))
    (a >> dll >> NOP >> ALIAS(b, "late")).render()
    assert probe._addr == [3]


def test_multiple_dlls_each_keep_their_hooks(log):
    """Two slots must not clobber each other's hooks."""
    a, b = make_node("A", log), make_node("B", log)
    first, second = ResolveOnCompile("sym"), ResolveOnCompile("sym")
    d1, d2 = DLLCompose(NodeCompose(first)), DLLCompose(NodeCompose(second))
    (a >> d1 >> d2 >> ALIAS(b, "sym")).render()
    assert first._addr == [3]
    assert second._addr == [3]


def test_apply_still_reruns_payload_hooks(log):
    """Rebasing recompiles the payload, so its hooks run again immediately."""
    a, b = make_node("A", log), make_node("B", log)
    probe = ResolveOnCompile("x")
    dll = DLLCompose(NodeCompose(ALIAS(a, "x"), probe))
    (b >> dll >> NOP).render()
    assert probe._addr == [1, 0]

    dll.apply(NodeCompose(probe, ALIAS(b, "x")))
    assert probe._addr == [1, 1]


def test_host_hook_collector_is_restored(log):
    """The host keeps its collector after a slot is built."""
    a, b = make_node("A", log), make_node("B", log)
    dll = DLLCompose(b.as_compose())
    r_comp = (a >> dll >> NOP).render()
    assert r_comp._collected_hooks is not None


def test_goto_across_a_dll_slot_skips_the_payload(log):
    """Runtime: a jump resolved across a slot lands on the alias target."""
    a = make_node("A", log)
    payload = make_node("payload", log)
    target = make_node("target", log)
    dll = DLLCompose(payload.as_compose())

    r_comp = (a >> GOTO("tgt") >> dll >> NOP >> ALIAS(target, "tgt")).render()
    asyncio.run(WorkflowInterpreter(r_comp).run())
    assert log == ["A", "target"]


def test_call_across_a_dll_slot_reaches_the_target(log):
    """Runtime: a call resolved across a slot reaches the alias target."""
    a = make_node("A", log)
    payload = make_node("payload", log)
    target = make_node("target", log)
    dll = DLLCompose(payload.as_compose())

    r_comp = (a >> CALL("tgt") >> dll >> NOP >> ALIAS(target, "tgt")).render()
    asyncio.run(WorkflowInterpreter(r_comp).run())
    #  CALL reaches the target, returns, then the walk reaches the DLL payload and finally the ALIAS node, which runs the aliased target once more.
    assert log == ["A", "target", "payload", "target"]


def test_dll_alias_prefix_kept_inside_bubble_across_apply(log):
    a, b, c = make_node("A", log), make_node("B", log), make_node("C", log)
    dll = DLLCompose((ALIAS(b, "dll_main")).as_compose())
    # The DLL sits inside a bubble at top-level slot [1], i.e. path [1, 1].
    r_comp = (a >> (NOP >> dll >> NOP) >> c).render()

    assert r_comp.alias2vector_map["dll_main"] == [1, 1, 0]

    dll.apply((ALIAS(c, "dll_main")).as_compose())
    # Rebasing keeps the same prefix even when nested inside a bubble.
    assert r_comp.alias2vector_map["dll_main"] == [1, 1, 0]

    asyncio.run(WorkflowInterpreter(r_comp).run())
    assert log == ["A", "C", "C"]
