"""GDB-style disassembly view for the AmritaSense debugger.

A rendered workflow graph *is* an address-mapped instruction sequence:
``[1, 0]`` is an address and `AbstractCompose.advance` is the program
counter.  A trace can therefore be rendered like a GDB listing::

    segment [root]:
      [0] Alpha            ; Alpha
      [1] *segment [1]
    =>[2] JMP [3]          ; NodeSuspend::_jump
      [3] NOP              ; NOP

    segment [1]:
      [1,0] Beta           ; Beta
      [1,1] Gamma          ; Gamma

Nested containers are printed as their own ``segment`` block, so deep
graphs stay flat instead of growing an indentation tree.

Two *soft-constraint magic attributes* let a node describe its own line.
Both are read as plain values at disassembly time — the input is an
already compiled graph, so operands such as a jump target are resolved:

``__sdb_dis__``
    Mnemonic text printed in the instruction column.  Falls back to the
    node tag, or to the wrapped function name for auto-generated tags.
``__sdb_cmt__``
    When not ``None``, overrides the comment printed after ``;``.

Both names accept three declaration forms, all resolved through a plain
`getattr`:

* a **class attribute** — a fixed mnemonic shared by every instance;
* a **`@property`** — a value computed from instance state, which stays
  correct across recompiles with no assignment step (a read-only property
  intentionally rejects `self.__sdb_dis__ = ...`);
* an **instance attribute** — for factory-created instructions whose operand
  only exists inside a closure (`PUSH_STACK`, `INTERRUPT_INTO`, …), and for
  module-level node singletons such as `NOP`.

Neither name is subject to name mangling (two trailing underscores), so
``self.__sdb_dis__ = ...`` inside a class body is safe.

Operand notation: an operand read through `PointerVector.near_to` is a
**slot index inside the current segment** and is written ``#N``; one read
through `PointerVector.offset` is a **delta inside the current segment**
and is written ``+N``.  A node never knows its own address, so no mnemonic
can print a full address for a segment-relative target.

The listing is colourised through colorama when stdout is a terminal (see
`COLOR`).  Colour is applied *after* column padding, so it never shifts the
instruction column, and piping the output yields plain text.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from colorama import Fore, Style, just_fix_windows_console

from amrita_sense.instructions.enum import AUTO_PREFIX
from amrita_sense.node.abc_base import AbstractCompose
from amrita_sense.node.core import BaseNode, NodeComposeRendered

if TYPE_CHECKING:
    from amrita_sense.runtime.workflow import WorkflowInterpreter


DIS_ATTR = "__sdb_dis__"
"""Magic attribute holding the mnemonic shown for a node."""

CMT_ATTR = "__sdb_cmt__"
"""Magic attribute overriding the comment shown after ``;``."""

AUTO_DIS: bool = True
"""Whether `step` / `cont` print the disassembly automatically."""

DEFAULT_WINDOW: int = 5
"""Instructions shown before and after the program counter."""

_ARROW = "=>"
_PAD = "  "
_SEP = "; "

_TAG_DECORATION = re.compile(r"^__([A-Z0-9_]+)__$")
"""Matches the ``__NAME__`` tag convention used by `BuiltinTags`."""


#  colour


COLOR: bool | None = None
"""Whether the listing is rendered with ANSI colour.

``None`` (the default) auto-detects: colour is used only when
`sys.stdout` is a terminal, so piping a listing to a file or a pager
naturally yields plain text.  Set to `True` / `False` to force it.
"""

C_PC = Style.BRIGHT + Fore.GREEN
"""Program-counter arrow (``=>``)."""

C_ADDR = Fore.CYAN
"""Instruction addresses."""

C_ALIAS = Fore.GREEN
"""Symbol names shown next to an address."""

C_MNEMONIC = Style.BRIGHT
"""The mnemonic itself."""

C_OPERAND = Fore.YELLOW
"""The operand part, i.e. everything after the mnemonic."""

C_COMMENT = Style.DIM
"""The ``;`` separator and the comment after it."""

C_SEGMENT = Style.BRIGHT + Fore.MAGENTA
"""The ``segment`` keyword."""

C_REF = Fore.CYAN
"""``*segment [n]`` reference lines."""

C_CLASS = Fore.BLUE
"""The container class annotation on a segment header."""

C_NOTE = Fore.YELLOW
"""Elision and end-of-workflow markers."""

C_ANOMALY = Fore.RED
"""Opaque entries and unreadable containers."""

_ansi_ready = False


def _stdout_is_tty() -> bool:
    """Report whether the listing is being written to a terminal."""
    stream = sys.stdout
    return stream is not None and stream.isatty()


def _color_enabled() -> bool:
    """Resolve `COLOR` against the current stdout."""
    global _ansi_ready
    if COLOR is False:
        return False
    if COLOR is None and not _stdout_is_tty():
        return False
    if not _ansi_ready:
        #  Enable ANSI processing once on Windows consoles; no-op elsewhere.
        _ansi_ready = True
        just_fix_windows_console()
    return True


def _paint(text: str, *styles: str) -> str:
    """Wrap *text* in *styles* when colour is enabled, else return it as is."""
    if not styles or not _color_enabled():
        return text
    return f"{''.join(styles)}{text}{Style.RESET_ALL}"


#  magic attribute resolution


def _str_attr(node: BaseNode, name: str) -> str | None:
    """Read *name* off *node*, keeping it only when it is a non-empty str."""
    value = getattr(node, name, None)
    if isinstance(value, str) and value:
        return value
    return None


def resolve_dis(node: BaseNode) -> str:
    """Return the mnemonic displayed for *node*.

    Resolution order:

    1. `__sdb_dis__`
    2. an explicit tag, with a ``__NAME__`` decoration stripped
    3. the wrapped function name (auto-generated tags such as
       ``NodeSuspend::_no_operation`` are not meant for display)
    """
    if (explicit := _str_attr(node, DIS_ATTR)) is not None:
        return explicit
    tag = node.tag
    if tag.startswith(AUTO_PREFIX):
        return node.func.__name__.lstrip("_") or tag
    if (decorated := _TAG_DECORATION.match(tag)) is not None:
        return decorated.group(1)
    return tag


def resolve_cmt(node: BaseNode) -> str:
    """Return the comment displayed after ``;`` for *node*.

    Resolution order: `__sdb_cmt__` → explicit `tag` → source location of
    the wrapped function (auto-generated tags such as
    ``NodeSuspend::_no_operation`` are not meant for display).
    """
    if (explicit := _str_attr(node, CMT_ATTR)) is not None:
        return explicit
    tag = node.tag
    if tag.startswith(AUTO_PREFIX):
        return _source_loc(node.func)
    return tag


def _source_loc(func: object) -> str:
    """Describe where *func* was defined, as ``file:line``.

    Falls back to the qualified name for callables without a code object
    (bound methods, `functools.partial`, C callables, …).
    """
    code = getattr(func, "__code__", None)
    if code is None:
        return getattr(func, "__qualname__", None) or getattr(func, "__name__", "?")
    filename = os.path.basename(code.co_filename) or code.co_filename
    return f"{filename}:{code.co_firstlineno}"


#  graph flattening


@dataclass
class _Entry:
    addr: list[int]
    kind: Literal["leaf", "ref", "opaque"]
    node: BaseNode | None = None
    child: int | None = None


@dataclass
class _Block:
    """One ``segment``: a container plus its direct entries."""

    addr: list[int]
    kind: str
    entries: list[_Entry] = field(default_factory=list)
    readable: bool = True


@dataclass
class _Walk:
    blocks: list[_Block]
    leaves: list[tuple[list[int], int]]
    """Every leaf as ``(address, owning block index)`` in execution order."""


def _walk(graph: AbstractCompose) -> _Walk:
    """Flatten *graph* into segment blocks plus the execution-order leaves.

    Containers are detected through the `AbstractCompose` **contract**, not
    a concrete class: a `DLLComposeProxy` is a rendered graph too, and the
    compose-contracts chapter explicitly allows custom rendered graphs.  A
    container that refuses to be read (an unbuilt proxy raises
    `NullPointerException`) is kept as an unreadable block instead of
    aborting the whole listing.
    """
    blocks: list[_Block] = []

    def build(container: AbstractCompose, addr: list[int]) -> int:
        index = len(blocks)
        block = _Block(addr=addr, kind=type(container).__name__)
        blocks.append(block)
        try:
            items = list(container)
        except Exception:
            block.readable = False
            return index
        pending: list[tuple[_Entry, AbstractCompose]] = []
        for offset, item in enumerate(items):
            item_addr = [*addr, offset]
            if isinstance(item, BaseNode):
                block.entries.append(_Entry(addr=item_addr, kind="leaf", node=item))
            elif isinstance(item, AbstractCompose):
                entry = _Entry(addr=item_addr, kind="ref")
                block.entries.append(entry)
                pending.append((entry, item))
            else:
                block.entries.append(_Entry(addr=item_addr, kind="opaque"))
        for entry, child in pending:
            entry.child = build(child, entry.addr)
        return index

    build(graph, [])

    #  Execution order is pointer order: the pointer descends into a container the moment it reaches it (what `advance()` does), so scanning a block instead would emit the parent's siblings before the nested body.
    leaves: list[tuple[list[int], int]] = []

    def order(block_index: int) -> None:
        for entry in blocks[block_index].entries:
            if entry.kind == "leaf":
                leaves.append((entry.addr, block_index))
            elif entry.child is not None:
                order(entry.child)

    order(0)
    return _Walk(blocks=blocks, leaves=leaves)


def _alias_map(graph: AbstractCompose) -> dict[tuple[int, ...], str]:
    """Build a reverse ``address → alias`` map.

    The symbol table is *not* part of the `AbstractCompose` contract, so a
    mock or a custom rendered graph may not have one — the view degrades to
    plain addresses instead of failing.
    """
    mapping = getattr(graph, "alias2vector_map", None)
    if not isinstance(mapping, dict):
        return {}
    reverse: dict[tuple[int, ...], str] = {}
    for name, addr in mapping.items():
        reverse.setdefault(tuple(addr), name)
    return reverse


#  rendering


def _fmt_addr(addr: list[int], aliases: dict[tuple[int, ...], str]) -> str:
    text = "[" + ", ".join(map(str, addr)) + "]"
    if (name := aliases.get(tuple(addr))) is not None:
        text += f" ({name})"
    return text


def _addr_cell(addr: list[int], aliases: dict[tuple[int, ...], str], width: int) -> str:
    """Render the address column padded to *width*.

    The padding is measured on the *plain* text and applied after the
    colour codes, so enabling colour cannot shift the instruction column.
    """
    plain = _fmt_addr(addr, aliases)
    pad = " " * (width - len(plain))
    if not _color_enabled():
        return plain + pad
    text = _paint("[" + ", ".join(map(str, addr)) + "]", C_ADDR)
    if (name := aliases.get(tuple(addr))) is not None:
        text += " " + _paint(f"({name})", C_ALIAS)
    return text + pad


def _body_cell(node: BaseNode) -> str:
    """Render the mnemonic and comment of a leaf line."""
    mnemonic = resolve_dis(node)
    comment = resolve_cmt(node)
    if not _color_enabled():
        return f"{mnemonic}{_SEP}{comment}"
    head, _, operand = mnemonic.partition(" ")
    text = _paint(head, C_MNEMONIC)
    if operand:
        text += " " + _paint(operand, C_OPERAND)
    return f"{text}{_paint(_SEP, C_COMMENT)}{_paint(comment, C_COMMENT)}"


def _segment_line(block: _Block, aliases: dict[tuple[int, ...], str]) -> str:
    """Render a ``segment <title>:`` header."""
    label = "[root]" if not block.addr else _fmt_addr(block.addr, aliases)
    parts = [_paint(label, C_ADDR if block.addr else C_MNEMONIC)]
    if block.kind != NodeComposeRendered.__name__:
        parts.append(_paint(f"<{block.kind}>", C_CLASS))
    if not block.readable:
        parts.append(_paint("(unreadable)", C_ANOMALY))
    return f"{_paint('segment', C_SEGMENT)} {' '.join(parts)}:"


def _render_entry(
    entry: _Entry,
    *,
    current: bool,
    width: int,
    aliases: dict[tuple[int, ...], str],
) -> str:
    marker = _paint(_ARROW, C_PC) if current else _PAD
    addr = _addr_cell(entry.addr, aliases, width)
    if entry.kind == "leaf" and entry.node is not None:
        body = _body_cell(entry.node)
    elif entry.kind == "ref":
        body = _paint(f"*segment {_fmt_addr(entry.addr, {})}", C_REF)
    else:
        body = _paint("<opaque>", C_ANOMALY)
    return f"{marker}{addr} {body}"


def _width(entries: list[_Entry], aliases: dict[tuple[int, ...], str]) -> int:
    return max((len(_fmt_addr(e.addr, aliases)) for e in entries), default=0)


def _is_under(pc: list[int], addr: list[int]) -> bool:
    return len(addr) < len(pc) and pc[: len(addr)] == addr


def _render_blocks(
    walk: _Walk, aliases: dict[tuple[int, ...], str], pc: list[int]
) -> list[str]:
    lines: list[str] = []
    for block in walk.blocks:
        if lines:
            lines.append("")
        lines.append(_segment_line(block, aliases))
        if not block.readable:
            lines.append(_paint(f"{_PAD}<unbuilt container>", C_ANOMALY))
            continue
        width = _width(block.entries, aliases)
        for entry in block.entries:
            current = entry.addr == pc or (
                entry.kind == "ref" and _is_under(pc, entry.addr)
            )
            lines.append(
                _render_entry(entry, current=current, width=width, aliases=aliases)
            )
    return lines


def _render_window(
    walk: _Walk,
    aliases: dict[tuple[int, ...], str],
    pc: list[int],
    around: int,
) -> list[str]:
    index: int | None = None
    for position, (addr, _) in enumerate(walk.leaves):
        if addr == pc:
            index = position
            break
    finished = index is None
    if index is None:
        index = len(walk.leaves)

    lo = max(0, index - around)
    hi = min(len(walk.leaves), index + around + 1)
    window = [
        (next(e for e in walk.blocks[b].entries if e.addr == addr), b)
        for addr, b in walk.leaves[lo:hi]
    ]
    width = max((len(_fmt_addr(e.addr, aliases)) for e, _ in window), default=0)

    lines: list[str] = []
    owner: int | None = None
    for entry, block_index in window:
        if block_index != owner:
            if lines:
                lines.append("")
            lines.append(_segment_line(walk.blocks[block_index], aliases))
            owner = block_index
        lines.append(
            _render_entry(
                entry,
                current=entry.addr == pc,
                width=width,
                aliases=aliases,
            )
        )
    if lo > 0:
        lines.insert(0, _paint(f"{_PAD}...", C_COMMENT))
    if finished:
        lines.append(_paint(f"{_ARROW} <end of workflow>", C_NOTE))
    return lines


#  public API


def disassemble(inter: WorkflowInterpreter, *, around: int | None = None) -> str:
    """Return the disassembly of *inter*'s graph as text.

    Args:
        inter: The interpreter whose graph is rendered.
        around: When ``None`` (default) the whole graph is printed segment
            by segment; when an int, only that many instructions before and
            after the program counter are shown.

    Returns:
        The rendered listing, one instruction per line.  ANSI colour codes
        are included when `COLOR` resolves to true.
    """
    graph = inter.get_graph()
    if not graph:
        return "(empty graph)"

    walk = _walk(graph)
    aliases = _alias_map(graph)
    pc = list(inter._pointer.base_addr) if inter._pointer else []
    if not walk.leaves:
        return "(empty graph)"
    if around is None:
        return "\n".join(_render_blocks(walk, aliases, pc))
    return "\n".join(_render_window(walk, aliases, pc, around))


def dis(inter: WorkflowInterpreter, *, around: int | None = DEFAULT_WINDOW) -> None:
    """Print the disassembly of *inter*'s graph.

    Args:
        inter: The interpreter whose graph is rendered.
        around: Number of instructions shown before and after the program
            counter; ``None`` prints the whole graph.
    """
    print(disassemble(inter, around=around))
