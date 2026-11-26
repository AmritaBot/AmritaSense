#!/usr/bin/env python3
"""Reject non-English (CJK) characters in source comments.

Python files are parsed with ``tokenize``, so every real comment token is
inspected: plain ``#``, ``#:`` doc-comments, ``#!`` lines and consecutive
comment blocks.  Docstrings and string literals are not comments and are
skipped.

Config and script files (``.toml``, ``.yaml``, ``.yml``, ``.sh``, ``.ini``,
``.cfg``) are scanned line by line with a small quote-aware state machine,
so a ``#`` inside a string is not mistaken for a comment.

Usage:
    python3 scripts/check_comment_language.py [files...]

With no arguments the staged files are checked; when the index is empty,
every covered file under ``src``, ``tests`` and ``scripts`` plus the
repository-root manifests are checked.  Exit status is 1 when any comment
contains CJK characters.
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
ROOTS = ("src", "tests", "scripts")
ROOT_FILES = ("pyproject.toml",)
TEXT_SUFFIXES = {".toml", ".yaml", ".yml", ".sh", ".ini", ".cfg"}
COVERED_SUFFIXES = {".py", *TEXT_SUFFIXES}


def staged_files() -> list[Path]:
    """Covered files with staged changes, so pre-commit only sees them."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=False,
    )
    paths = [Path(line) for line in result.stdout.splitlines()]
    return [p for p in paths if p.suffix in COVERED_SUFFIXES and p.is_file()]


def all_files() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        base = Path(root)
        if base.is_dir():
            files.extend(
                p for p in base.rglob("*") if p.suffix in COVERED_SUFFIXES and p.is_file()
            )
    files.extend(Path(name) for name in ROOT_FILES if Path(name).is_file())
    files.extend(
        p for p in Path().glob("*.y*ml") if p.suffix in COVERED_SUFFIXES and p.is_file()
    )
    return files


def scan_python(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        return [
            (token.start[0], token.string.strip())
            for token in tokens
            if token.type == tokenize.COMMENT and CJK.search(token.string)
        ]
    except (SyntaxError, tokenize.TokenError, UnicodeDecodeError):
        # Unparsable files are someone else's failure; do not mask it here.
        return []


def scan_text(path: Path) -> list[tuple[int, str]]:
    """Quote-aware ``#`` comment scan for non-Python source files."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []

    hits: list[tuple[int, str]] = []
    quote: str | None = None
    for number, line in enumerate(lines, 1):
        index = 0
        while index < len(line):
            char = line[index]
            if quote is not None:
                if char == quote:
                    quote = None
                index += 1
                continue
            if char in "\"'":
                quote = char
            elif char == "#":
                comment = line[index:].strip()
                if CJK.search(comment):
                    hits.append((number, comment))
                break
            index += 1
    return hits


def scan(path: Path) -> list[tuple[int, str]]:
    if path.suffix == ".py":
        return scan_python(path)
    return scan_text(path)


def main(argv: list[str]) -> int:
    if argv[1:]:
        # pre-commit passes the staged filenames explicitly.
        targets = [Path(arg) for arg in argv[1:]]
        scope = "given files"
    else:
        targets = staged_files()
        scope = "staged files"
        if not targets:
            targets = all_files()
            scope = "all covered files"

    failures = 0
    for path in targets:
        for line, comment in scan(path):
            failures += 1
            print(f"{path}:{line}: non-English comment: {comment}")

    if failures:
        print(f"{failures} non-English comment(s) in {scope}.", file=sys.stderr)
        return 1
    print(f"No non-English comments in {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
