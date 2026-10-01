#!/usr/bin/env python3
"""Render the coverage data as Markdown for `$GITHUB_STEP_SUMMARY`.

Reads the `.coverage` data file that `pytest --cov` already wrote, through the
`coverage` API rather than re-parsing the XML export: same numbers, no extra
dependency beyond the `coverage` that `pytest-cov` already pulls in, and no XML
parser to point at untrusted input.

Usage:
    coverage_summary.py [.coverage] [--top N] [--min PERCENT]

Exit status is 0 unless `--min` is given and total line coverage is below it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from coverage import Coverage


def _relative(filename: str) -> str:
    """Prefer a repository-relative path; fall back to the absolute one."""
    try:
        return os.path.relpath(filename)
    except ValueError:  # pragma: no cover - only reachable across Windows drives
        return filename


def _collect(
    data_file: Path,
) -> tuple[dict[str, float], list[tuple[str, float, int, int]]]:
    """Return (totals, per-file rows) from a coverage data file."""
    cov = Coverage(data_file=str(data_file))
    cov.load()
    data = cov.get_data()

    total_statements = 0
    total_missing = 0
    files: list[tuple[str, float, int, int]] = []

    for filename in sorted(data.measured_files()):
        try:
            _, statements, _, missing, _ = cov.analysis2(filename)
        except Exception:
            # Files without readable source (compiled extensions, generated
            # modules) cannot be analysed; skipping them is not fatal.
            continue
        covered = len(statements) - len(missing)
        total_statements += len(statements)
        total_missing += len(missing)
        rate = 100.0 * covered / len(statements) if statements else 100.0
        files.append((_relative(filename), rate, len(statements), len(missing)))

    files.sort(key=lambda item: (item[1], -item[2]))
    totals = {
        "rate": (
            100.0 * (total_statements - total_missing) / total_statements
            if total_statements
            else 0.0
        ),
        "covered": total_statements - total_missing,
        "statements": total_statements,
    }
    return totals, files


def render(data_file: Path, top: int) -> str:
    totals, files = _collect(data_file)

    lines = ["## Coverage", ""]
    lines.append(
        f"**Total: {totals['rate']:.2f}%** "
        f"({totals['covered']}/{totals['statements']} statements)"
    )
    lines.append("")

    if not files:
        lines.append("_No per-file coverage data recorded._")
        return "\n".join(lines)

    shown = min(top, len(files))
    lines.append(f"Lowest-covered files (worst {shown} of {len(files)}):")
    lines.append("")
    lines.append("| File | Coverage | Missing |")
    lines.append("|---|:---:|:---:|")
    for filename, rate, statements, missing in files[:top]:
        lines.append(f"| `{filename}` | {rate:.1f}% | {missing}/{statements} |")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "data_file",
        nargs="?",
        default=".coverage",
        help="coverage data file written by pytest-cov (default .coverage)",
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

    if args.top < 1:
        parser.error("--top must be at least 1")

    path = Path(args.data_file)
    if not path.exists():
        print(f"Coverage data file not found: {path}", file=sys.stderr)
        return 1

    totals, _ = _collect(path)
    print(render(path, args.top))

    if args.min is not None and totals["rate"] < args.min:
        print(
            f"::error::Total coverage {totals['rate']:.2f}% "
            f"is below the required {args.min:.2f}%"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
