#!/usr/bin/env bash
# Use this script to run a benchmark.

set -euo pipefail

echo "========== 1. Init environment =========="
uv sync
echo "========== 2. Run benchmark =========="
uv run benchmark.py
echo "========== Done! =========="