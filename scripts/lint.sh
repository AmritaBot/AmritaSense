#!/usr/bin/env bash
# lint.sh — Run linters and type checker.
set -euo pipefail

echo "=== Pyright ==="
uv run pyright

echo ""
echo "=== Ruff check ==="
uv run ruff check .

echo ""
echo "=== Comment language ==="
uv run python scripts/check_comment_language.py

echo ""
echo "=== Ruff format check ==="
uv run ruff format --check .
