#!/usr/bin/env bash
# test.sh — Run unit tests without coverage.
set -euo pipefail

echo "=== Running unit tests ==="
uv run pytest tests/ -v
