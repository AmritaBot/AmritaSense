"""Tests for the GDB-style disassembly view (`amrita_sense.debugger.code_disp`)."""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from typing import Any

import pytest
from colorama import Style

from amrita_sense import Node, WorkflowInterpreter
from amrita_sense.debugger import code_disp, dis, disassemble
from amrita_sense.debugger.code_disp import (
    DIS_ATTR,
    _walk,
    resolve_cmt,
    resolve_dis,
)
from amrita_sense.instructions import (
    ALIAS,
    CALL,
    GOTO,
    IF,
    NOP,
    PUSH_STACK,
    WHILE,
    Try,
)
from amrita_sense.node import DLLCompose
from amrita_sense.node.abc_base import AbstractCompose
from amrita_sense.node.core import BaseNode, NodeCompose


@Node("Alpha")
def alpha() -> None: ...


@Node("Beta")
def beta() -> None: ...


@Node("Gamma")
def gamma() -> None: ...


@Node(tag=None)
def untagged() -> None: ...


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture(autouse=True)
def _plain_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin colour off so text assertions do not depend on the test runner's tty."""
    monkeypatch.setattr(code_disp, "COLOR", False)


@pytest.fixture
def nested_inter() -> WorkflowInterpreter:
    """``alpha >> (beta >> gamma) >> NOP`` — a nested segment in the middle."""
    return WorkflowInterpreter((alpha >> (beta >> gamma) >> NOP).render())


@pytest.fixture
def dll_inter() -> WorkflowInterpreter:
    """A graph containing a DLL slot plus an alias."""
    dll = DLLCompose(beta.as_compose())
    cmp = (alpha >> dll >> ALIAS(gamma, "sym_g") >> NOP).render()
    return WorkflowInterpreter(cmp)


@pytest.fixture
def segmented_inter() -> WorkflowInterpreter:
    """A graph spanning three segments: root, a nested compose, and a DLL slot.

    ``alpha >> (beta >> gamma) >> dll >> ALIAS(gamma, "sym_g") >> NOP``
    """
    dll = DLLCompose(gamma.as_compose())
    cmp = (alpha >> (beta >> gamma) >> dll >> ALIAS(gamma, "sym_g") >> NOP).render()
    return WorkflowInterpreter(cmp)


#  magic attribute resolution


class TestMagicAttributes:
    def test_explicit_dis_wins(self) -> None:
        node = Node("tagged")(lambda: None)
        node.__sdb_dis__ = "CUSTOM"
        assert resolve_dis(node) == "CUSTOM"

    def test_explicit_cmt_wins(self) -> None:
        node = Node("tagged")(lambda: None)
        node.__sdb_cmt__ = "the comment"
        assert resolve_cmt(node) == "the comment"

    def test_cmt_defaults_to_tag(self) -> None:
        assert resolve_cmt(alpha) == "Alpha"

    def test_tag_decoration_is_stripped_for_display(self) -> None:
        node = Node("__MY_INSTR__")(lambda: None)
        assert resolve_dis(node) == "MY_INSTR"
        #  the comment keeps the raw tag, which is what break_at_tag matches
        assert resolve_cmt(node) == "__MY_INSTR__"

    def test_auto_tag_falls_back_to_function_name(self) -> None:
        assert resolve_dis(untagged) == "untagged"
        assert resolve_cmt(untagged).startswith("test_code_disp.py:")

    def test_explicit_tag_is_used_verbatim(self) -> None:
        assert resolve_dis(alpha) == "Alpha"

    def test_empty_string_is_treated_as_unset(self) -> None:
        node = Node("tagged")(lambda: None)
        node.__sdb_dis__ = ""
        assert resolve_dis(node) == "tagged"

    def test_magic_names_are_not_mangled(self) -> None:
        class Custom(BaseNode):
            __sdb_dis__ = "CLASS_LEVEL"
            __sdb_cmt__ = "class level"

            def __call__(self, *args: Any, **kwds: Any) -> Any: ...
            def _pre_check(self, pointer: Any) -> None: ...
            def _post_compile(self, compose: Any) -> None: ...

        node = Custom()
        assert resolve_dis(node) == "CLASS_LEVEL"
        assert resolve_cmt(node) == "class level"

    def test_builtin_mnemonics_are_annotated(self) -> None:
        assert resolve_dis(NOP) == "NOP"
        assert resolve_cmt(NOP) == "no operation"

    def test_goto_resolves_its_target_at_compile_time(self) -> None:
        cmp = (ALIAS(beta, "target") >> GOTO("target") >> NOP).render()
        listing = disassemble(WorkflowInterpreter(cmp), around=None)
        assert "JMP [0]" in listing
        assert "GOTO 'target'" in listing

    def test_call_alias_is_shown(self) -> None:
        listing = disassemble(
            WorkflowInterpreter((ALIAS(beta, "sym") >> NOP).render()), around=None
        )
        assert "ALIAS sym" in listing
        assert "alias for Beta" in listing


#  declaration forms


class _DynamicNode(BaseNode):
    """Mnemonic derived from mutable instance state through a property."""

    def __init__(self, target: int = 1) -> None:
        self._target = target
        self._init(self.__call__, tag="dyn", wrap_to_async=False, address_able=True)

    @property
    def __sdb_dis__(self) -> str:
        return f"DYN #{self._target}"

    def __call__(self, *args: Any, **kwds: Any) -> Any: ...
    def _pre_check(self, pointer: Any) -> None: ...
    def _post_compile(self, compose: Any) -> None: ...


class _AliasNode(BaseNode):
    """Mnemonic derived from an alias resolved while compiling."""

    def __init__(self, alias: str) -> None:
        self._alias = alias
        self._addr: list[int] = []
        self._init(self.__call__, tag=None, wrap_to_async=False, address_able=True)

    @property
    def __sdb_dis__(self) -> str:
        return f"RESOLVED {self._addr or '?'}"

    def __call__(self, *args: Any, **kwds: Any) -> Any: ...
    def _pre_check(self, pointer: Any) -> None: ...
    def _post_compile(self, compose: Any) -> None:
        #  the symbol table is filled before hooks run, and it lives on the top graph even when this node sits inside a DLL slot
        self._addr = compose.alias2vector_map[self._alias]


class TestDeclarationForms:
    def test_property_tracks_mutable_state(self) -> None:
        """A property re-reads state, so no re-assignment step is needed."""
        node = _DynamicNode(1)
        assert resolve_dis(node) == "DYN #1"
        node._target = 7
        assert resolve_dis(node) == "DYN #7"

    def test_property_node_still_falls_back_for_the_comment(self) -> None:
        assert resolve_cmt(_DynamicNode()) == "dyn"

    def test_read_only_property_rejects_instance_assignment(self) -> None:
        """A property is a data descriptor: the instance form is unavailable."""
        node = _DynamicNode()
        with pytest.raises(AttributeError):
            setattr(node, DIS_ATTR, "nope")

    def test_property_picks_up_a_dll_rebase(self) -> None:
        """A rebase re-runs `_post_compile`, and the property follows along."""
        node = _AliasNode("x")
        dll = DLLCompose(NodeCompose(ALIAS(alpha, "x"), node))
        inter = WorkflowInterpreter((beta >> dll >> NOP).render())
        assert "RESOLVED [1, 0]" in disassemble(inter, around=None)

        dll.apply(NodeCompose(node, ALIAS(gamma, "x")))
        assert "RESOLVED [1, 1]" in disassemble(inter, around=None)

    def test_closure_factory_node_uses_an_instance_attribute(self) -> None:
        """`PUSH_STACK` is built by a factory, so its operand lives on the instance."""
        cmp = (ALIAS(alpha, "sym") >> PUSH_STACK("sym") >> NOP).render()
        listing = disassemble(WorkflowInterpreter(cmp), around=None)
        assert "PUSH [0]" in listing

    def test_unresolved_operand_renders_as_unknown(self) -> None:
        """Before compilation the operand is unknown, and says so."""
        assert resolve_dis(GOTO("sym")) == "JMP ?"
        assert resolve_dis(CALL("sym")) == "CALL sym -> ?"


#  control-flow operand notation


class TestOperandNotation:
    def test_if_shows_both_branches(self) -> None:
        @Node("Cond")
        def cond() -> bool:
            return True

        cmp = (IF(cond, beta) >> NOP).render()
        listing = disassemble(WorkflowInterpreter(cmp), around=None)
        assert "JMPIF then=#" in listing
        assert "else=+" in listing

    def test_while_shows_checkup_and_exit(self) -> None:
        @Node("Cond")
        def cond() -> bool:
            return False

        cmp = (WHILE(cond).ACTION(beta) >> NOP).render()
        listing = disassemble(WorkflowInterpreter(cmp), around=None)
        assert "WHILE checkup=#" in listing
        assert "WHILE.CHECK back=#" in listing

    def test_try_shows_handlers_and_escape_points(self) -> None:
        clause = Try(beta).CATCH(ValueError, alpha).FINALLY(gamma)
        cmp = NodeCompose(clause).render()
        listing = disassemble(WorkflowInterpreter(cmp), around=None)
        assert "TRY catch=ValueError#" in listing
        assert "finally=#" in listing
        assert "escape=#" in listing

    def test_slot_notation_is_segment_relative(self) -> None:
        """A `#N` operand is a slot in the node's own segment, never an address."""

        @Node("Cond")
        def cond() -> bool:
            return True

        cmp = (IF(cond, beta) >> NOP).render()
        listing = disassemble(WorkflowInterpreter(cmp), around=None)
        line = next(line for line in listing.splitlines() if "JMPIF" in line)
        assert "then=#3" in line
        #  the segment holding the JMPIF is [1], so [1, 3] is its absolute target
        assert "[1, 3]" not in line


#  listing structure


class TestListing:
    def test_root_segment_header(self, nested_inter: WorkflowInterpreter) -> None:
        listing = disassemble(nested_inter, around=None)
        assert listing.startswith("segment [root]:")

    def test_nested_container_is_a_reference_line(
        self, nested_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(nested_inter, around=None)
        assert "  [1] *segment [1]" in listing
        assert "segment [1]:" in listing

    def test_nested_body_lives_in_its_own_block(
        self, nested_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(nested_inter, around=None)
        assert "[1, 0] Beta" in listing
        assert "[1, 1] Gamma" in listing

    def test_pc_arrow_marks_the_current_line(
        self, nested_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(nested_inter, around=None)
        assert "=>[0] Alpha" in listing

    def test_pc_under_a_segment_marks_the_reference_line(
        self, nested_inter: WorkflowInterpreter
    ) -> None:
        nested_inter._pointer.far_to([1, 0])
        listing = disassemble(nested_inter, around=None)
        assert "=>[1] *segment [1]" in listing
        assert "=>[1, 0] Beta" in listing

    def test_alias_is_shown_next_to_the_address(
        self, dll_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(dll_inter, around=None)
        assert "(sym_g)" in listing

    def test_dll_slot_shows_its_concrete_container_class(
        self, dll_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(dll_inter, around=None)
        assert "segment [1] <DLLComposeProxy>:" in listing

    def test_single_node_graph_renders_one_line(self) -> None:
        inter = WorkflowInterpreter(NodeCompose(NOP).render())
        assert disassemble(inter, around=None) == (
            "segment [root]:\n=>[0] NOP; no operation"
        )

    def test_dis_prints(self, nested_inter: WorkflowInterpreter, capsys) -> None:
        dis(nested_inter, around=None)
        assert "segment [root]:" in capsys.readouterr().out


#  multiple segments in one graph


class TestMultiSegment:
    """One graph can span several segments: root, a nested compose, and a DLL slot."""

    def test_each_segment_gets_its_own_block(
        self, segmented_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(segmented_inter, around=None)
        assert listing.startswith("segment [root]:")
        assert "\nsegment [1]:\n" in listing
        assert "\nsegment [2] <DLLComposeProxy>:\n" in listing

    def test_container_slots_are_reference_lines(
        self, segmented_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(segmented_inter, around=None)
        refs = [" ".join(ln.split()) for ln in listing.splitlines() if "*segment" in ln]
        assert refs == ["[1] *segment [1]", "[2] *segment [2]"]

    def test_nested_and_dll_bodies_stay_in_their_own_segments(
        self, segmented_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(segmented_inter, around=None)
        assert "[1, 0] Beta" in listing
        assert "[1, 1] Gamma" in listing
        assert "[2, 0] Gamma" in listing

    def test_blocks_appear_in_address_order(
        self, segmented_inter: WorkflowInterpreter
    ) -> None:
        listing = disassemble(segmented_inter, around=None)
        assert listing.index("segment [root]:") < listing.index("\nsegment [1]:")
        assert listing.index("\nsegment [1]:") < listing.index("\nsegment [2] <")

    def test_full_listing_matches_the_documented_format(
        self, segmented_inter: WorkflowInterpreter
    ) -> None:
        expected = (
            "segment [root]:\n"
            "=>[0]         Alpha; Alpha\n"
            "  [1]         *segment [1]\n"
            "  [2]         *segment [2]\n"
            "  [3] (sym_g) ALIAS sym_g; alias for Gamma\n"
            "  [4]         NOP; no operation\n"
            "\n"
            "segment [1]:\n"
            "  [1, 0] Beta; Beta\n"
            "  [1, 1] Gamma; Gamma\n"
            "\n"
            "segment [2] <DLLComposeProxy>:\n"
            "  [2, 0] Gamma; Gamma"
        )
        assert disassemble(segmented_inter, around=None) == expected

    def test_window_spans_two_segments_when_pc_is_inside_a_nested_one(
        self, segmented_inter: WorkflowInterpreter
    ) -> None:
        segmented_inter._pointer.far_to([1, 0])
        listing = disassemble(segmented_inter, around=1)
        headers = [ln for ln in listing.splitlines() if ln.startswith("segment ")]
        assert headers == ["segment [root]:", "segment [1]:"]
        assert "=>[1, 0] Beta; Beta" in listing


#  window mode


class TestWindow:
    def test_window_limits_lines(self, nested_inter: WorkflowInterpreter) -> None:
        nested_inter._pointer.far_to([1, 0])
        full = disassemble(nested_inter, around=None)
        window = disassemble(nested_inter, around=1)
        assert len(window.splitlines()) < len(full.splitlines())

    def test_window_follows_execution_order(self) -> None:
        """The window must interleave nested bodies where the pointer visits them."""
        cmp = (alpha >> (beta >> gamma) >> NOP).render()
        inter = WorkflowInterpreter(cmp)
        inter._pointer.far_to([1, 0])
        lines = disassemble(inter, around=1).splitlines()
        order = [line for line in lines if ";" in line]
        assert "Alpha" in order[0]
        assert "[1, 0] Beta" in order[1]
        assert "[1, 1] Gamma" in order[2]

    def test_window_marks_the_program_counter(
        self, nested_inter: WorkflowInterpreter
    ) -> None:
        nested_inter._pointer.far_to([1, 1])
        assert "=>[1, 1] Gamma" in disassemble(nested_inter, around=1)

    def test_window_after_the_last_node_shows_end_marker(
        self, nested_inter: WorkflowInterpreter
    ) -> None:
        nested_inter._pointer.base_addr = []
        listing = disassemble(nested_inter, around=1)
        assert "=> <end of workflow>" in listing

    def test_window_elides_the_head_when_offscreen(self) -> None:
        cmp = (alpha >> beta >> gamma >> NOP).render()
        inter = WorkflowInterpreter(cmp)
        inter._pointer.far_to([3])
        assert "..." in disassemble(inter, around=1)


#  contract safety (custom / unbuilt rendered graphs)


class _Unreadable(AbstractCompose[Any]):
    """Container that refuses to be read, like an unbuilt DLL proxy."""

    @property
    def calc(self) -> Any:
        raise AttributeError("no calculator")

    def __init__(self) -> None: ...
    def __getitem__(self, key: int) -> Any:
        raise IndexError(key)

    def __iter__(self) -> Iterator[Any]:
        raise RuntimeError("not built yet")

    def __bool__(self) -> bool:
        return True

    def __len__(self) -> int:
        return 0

    def _build(
        self, current_path: list[int] | None = None, top: Any = None
    ) -> None: ...


class TestContractSafety:
    def test_unbuilt_container_does_not_abort_the_listing(self) -> None:
        class Fake(AbstractCompose[Any]):
            def __init__(self) -> None:
                self._items = [NOP, _Unreadable()]

            @property
            def calc(self) -> Any:
                raise AttributeError("no calculator")

            def __getitem__(self, key: int) -> Any:
                return self._items[key]

            def __iter__(self) -> Iterator[Any]:
                return iter(self._items)

            def __bool__(self) -> bool:
                return True

            def __len__(self) -> int:
                return len(self._items)

            def _build(
                self, current_path: list[int] | None = None, top: Any = None
            ) -> None: ...

        walk = _walk(Fake())
        assert len(walk.blocks) == 2
        assert walk.blocks[1].readable is False

    def test_missing_symbol_table_degrades_to_plain_addresses(self) -> None:
        class Fake(AbstractCompose[Any]):
            def __init__(self) -> None:
                self._items = [alpha, beta]

            @property
            def calc(self) -> Any:
                raise AttributeError("no calculator")

            def __getitem__(self, key: int) -> Any:
                return self._items[key]

            def __iter__(self) -> Iterator[Any]:
                return iter(self._items)

            def __bool__(self) -> bool:
                return True

            def __len__(self) -> int:
                return len(self._items)

            def _build(
                self, current_path: list[int] | None = None, top: Any = None
            ) -> None: ...

        walk = _walk(Fake())
        assert [addr for addr, _ in walk.leaves] == [[0], [1]]

    def test_unbuilt_dll_proxy_is_listed_without_raising(self) -> None:
        proxy = DLLCompose(beta.as_compose()).get_builder()(
            DLLCompose(beta.as_compose())
        )
        walk = _walk(proxy)
        assert walk.blocks[0].readable is False
        assert walk.leaves == []


#  step / cont integration


class TestStepIntegration:
    def test_step_prints_the_disassembly(
        self, nested_inter: WorkflowInterpreter, capsys
    ) -> None:
        from amrita_sense.debugger import step

        step(nested_inter)
        out = capsys.readouterr().out
        assert "segment [root]:" in out
        assert "=>[1, 0] Beta" in out

    def test_auto_dis_can_be_disabled(
        self, nested_inter: WorkflowInterpreter, capsys, monkeypatch
    ) -> None:
        from amrita_sense.debugger import step

        monkeypatch.setattr(code_disp, "AUTO_DIS", False)
        step(nested_inter)
        assert capsys.readouterr().out == ""

    def test_step_over_prints_only_once(self, capsys) -> None:
        from amrita_sense.debugger import step_over

        @Node("Caller")
        async def caller(pc: WorkflowInterpreter) -> None:
            await pc.call_near(1)

        inter = WorkflowInterpreter((caller >> beta).render())
        step_over(inter)
        out = capsys.readouterr().out
        assert out.count("segment [root]:") == 1

    def test_cont_prints_at_the_end_of_the_workflow(self, capsys) -> None:
        from amrita_sense.debugger import cont

        inter = WorkflowInterpreter((alpha >> beta).render())
        cont(inter)
        out = capsys.readouterr().out
        assert "=> <end of workflow>" in out


#  colour


class TestColor:
    def test_plain_listing_has_no_escapes(
        self, nested_inter: WorkflowInterpreter
    ) -> None:
        assert "\x1b[" not in disassemble(nested_inter, around=None)

    def test_color_can_be_forced_on(
        self, nested_inter: WorkflowInterpreter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(code_disp, "COLOR", True)
        assert "\x1b[" in disassemble(nested_inter, around=None)

    def test_color_preserves_column_alignment(
        self, nested_inter: WorkflowInterpreter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Padding is measured on plain text, so colour cannot shift the body."""
        plain = disassemble(nested_inter, around=None)
        monkeypatch.setattr(code_disp, "COLOR", True)
        colored = disassemble(nested_inter, around=None)
        assert colored != plain
        assert _ANSI.sub("", colored) == plain

    def test_pc_arrow_is_painted(
        self, nested_inter: WorkflowInterpreter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(code_disp, "COLOR", True)
        listing = disassemble(nested_inter, around=None)
        line = next(line for line in listing.splitlines() if "Alpha" in line)
        assert line.startswith(f"{code_disp.C_PC}=>{Style.RESET_ALL}")

    def test_address_is_painted(
        self, nested_inter: WorkflowInterpreter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(code_disp, "COLOR", True)
        listing = disassemble(nested_inter, around=None)
        assert f"{code_disp.C_ADDR}[0]{Style.RESET_ALL}" in listing

    def test_mnemonic_and_operand_use_different_styles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        @Node("Cond")
        def cond() -> bool:
            return True

        inter = WorkflowInterpreter((IF(cond, beta) >> NOP).render())
        monkeypatch.setattr(code_disp, "COLOR", True)
        line = next(
            line
            for line in disassemble(inter, around=None).splitlines()
            if "JMPIF" in line
        )
        assert f"{code_disp.C_MNEMONIC}JMPIF{Style.RESET_ALL}" in line
        assert f"{code_disp.C_OPERAND}then=#3" in line

    def test_alias_is_painted(
        self, dll_inter: WorkflowInterpreter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(code_disp, "COLOR", True)
        listing = disassemble(dll_inter, around=None)
        assert f"{code_disp.C_ALIAS}(sym_g){Style.RESET_ALL}" in listing

    def test_container_class_annotation_is_painted(
        self, dll_inter: WorkflowInterpreter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(code_disp, "COLOR", True)
        listing = disassemble(dll_inter, around=None)
        assert f"{code_disp.C_CLASS}<DLLComposeProxy>{Style.RESET_ALL}" in listing

    def test_segment_keyword_is_painted(
        self, nested_inter: WorkflowInterpreter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(code_disp, "COLOR", True)
        listing = disassemble(nested_inter, around=None)
        assert f"{code_disp.C_SEGMENT}segment{Style.RESET_ALL}" in listing

    def test_auto_detection_follows_stdout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Tty:
            def isatty(self) -> bool:
                return True

        monkeypatch.setattr(code_disp, "COLOR", None)
        monkeypatch.setattr(code_disp.sys, "stdout", _Tty())
        assert code_disp._color_enabled() is True

        monkeypatch.setattr(code_disp.sys, "stdout", io.StringIO())
        assert code_disp._color_enabled() is False

    def test_explicit_false_wins_over_a_tty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Tty:
            def isatty(self) -> bool:
                return True

        monkeypatch.setattr(code_disp, "COLOR", False)
        monkeypatch.setattr(code_disp.sys, "stdout", _Tty())
        assert code_disp._color_enabled() is False
