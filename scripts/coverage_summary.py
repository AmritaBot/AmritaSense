#!/usr/bin/env python3
"""Render a `coverage.xml` report as Markdown for `$GITHUB_STEP_SUMMARY`.

The XML writer is built into `coverage` itself, so this reads the report
`pytest --cov-report=xml` already produced instead of re-running coverage or
shelling out to a third-party action.

Usage:
    coverage_summary.py [coverage.xml] [--top N] [--min PERCENT]

Exit status is 0 unless `--min` is given and the total line rate is below it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree


def _pct(value: str | None) -> float:
    """`coverage.xml` stores rates as 0..1 fractions."""
    if value is None:
        return 0.0
    return float(value) * 100


def _collect(path: Path) -> tuple[dict[str, float], list[tuple[str, float, int]]]:
    root = ElementTree.parse(path).getroot()

    total = {
        "line": _pct(root.get("line-rate")),
        "branch": _pct(root.get("branch-rate")),
        "lines_covered": int(root.get("lines-covered", 0)),
        "lines_valid": int(root.get("lines-valid", 0)),
    }

    files: list[tuple[str, float, int]] = []
    for cls in root.iter("class"):
        filename = cls.get("filename") or cls.get("name") or "?"
        rate = _pct(cls.get("line-rate"))
        statements = len(cls.findall("./lines/line"))
        files.append((filename, rate, statements))

    files.sort(key=lambda item: (item[1], -item[2]))
    return total, files


def render(path: Path, top: int) -> str:
    total, files = _collect(path)

    lines = ["## Coverage", ""]
    lines.append(
        f"**Total: {total['line']:.2f}%** "
        f"({total['lines_covered']}/{total['lines_valid']} statements)"
        + (f" · branches {total['branch']:.2f}%" if total["branch"] else "")
    )
    lines.append("")

    if not files:
        lines.append("_No per-file coverage data in the report._")
        return "\n".join(lines)

    lines.append(
        f"Lowest-covered files (worst {min(top, len(files))} of {len(files)}):"
    )
    lines.append("")
    lines.append("| File | Coverage | Statements |")
    lines.append("|---|:---:|:---:|")
    for filename, rate, statements in files[:top]:
        lines.append(f"| `{filename}` | {rate:.1f}% | {statements} |")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report",
        nargs="?",
        default="coverage.xml",
        help="path to the coverage XML report (default coverage.xml)",
    )
    parser.add_argument(
        "--top", type=int, default=15, help="how many low-coverage files to list"
    )
    parser.add_argument(
        "--min",
        type=float,
        default=None,
        metavar="PERCENT",
        help="fail if total line coverage is below this percentage",
    )
    args = parser.parse_args(argv)

    path = Path(args.report)
    if not path.exists():
        print(f"Coverage report not found: {path}", file=sys.stderr)
        return 1

    total, _ = _collect(path)
    print(render(path, args.top))

    if args.min is not None and total["line"] < args.min:
        print(
            f"::error::Total coverage {total['line']:.2f}% "
            f"is below the required {args.min:.2f}%"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
